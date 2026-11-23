"""Persistent job records and ordered event history for Studio workers."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from ..application.serialization import JsonValue


@dataclass(frozen=True, slots=True)
class StoredJob:
    id: str
    state: str
    request_json: str
    explicit_fields_json: str
    project: str | None
    narration_id: str | None
    output: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    progress_json: str | None
    result_json: str | None
    error_json: str | None
    cancellation_requested: bool
    event_sequence: int
    queue_order: int = 0
    retry_of: str | None = None


@dataclass(frozen=True, slots=True)
class StoredJobEvent:
    sequence: int
    timestamp: str
    event: dict[str, JsonValue]


class JobStore(Protocol):
    def create_job(self, job: StoredJob, event: StoredJobEvent) -> StoredJob: ...

    def update_job(self, job: StoredJob) -> None: ...

    def append_event(
        self, job: StoredJob, event: StoredJobEvent, *, limit: int
    ) -> None: ...

    def get_job(self, job_id: str) -> StoredJob | None: ...

    def list_jobs(self) -> tuple[StoredJob, ...]: ...

    def list_events(
        self, job_id: str, *, after: int = 0
    ) -> tuple[StoredJobEvent, ...]: ...

    def pending_jobs(self) -> tuple[StoredJob, ...]: ...

    def delete_jobs(self, job_ids: tuple[str, ...]) -> None: ...

    def close(self) -> None: ...


class SqliteJobStore:
    """Store job state and event history in one SQLite database."""

    def __init__(self, path: Path | str) -> None:
        if str(path) == ":memory:":
            database = ":memory:"
        else:
            database_path = Path(path).expanduser()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            database = str(database_path)
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                request_json TEXT NOT NULL,
                explicit_fields_json TEXT NOT NULL,
                project TEXT,
                narration_id TEXT,
                output TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                progress_json TEXT,
                result_json TEXT,
                error_json TEXT,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                event_sequence INTEGER NOT NULL DEFAULT 0,
                queue_order INTEGER NOT NULL UNIQUE,
                retry_of TEXT
            );
            CREATE TABLE IF NOT EXISTS job_queue_sequence (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                next_order INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO job_queue_sequence (singleton, next_order)
                SELECT 1, COALESCE(MAX(queue_order), 0) + 1 FROM jobs;
            CREATE INDEX IF NOT EXISTS jobs_queue_order_idx
                ON jobs(state, queue_order);
            CREATE TABLE IF NOT EXISTS job_events (
                job_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_json TEXT NOT NULL,
                PRIMARY KEY (job_id, sequence),
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            """
        )
        self._connection.commit()

    def create_job(self, job: StoredJob, event: StoredJobEvent) -> StoredJob:
        with self._transaction() as connection:
            queue_order = connection.execute(
                "SELECT next_order FROM job_queue_sequence WHERE singleton = 1"
            ).fetchone()[0]
            connection.execute(
                "UPDATE job_queue_sequence SET next_order = ? WHERE singleton = 1",
                (queue_order + 1,),
            )
            stored = replace(
                job, queue_order=queue_order, event_sequence=event.sequence
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    id, state, request_json, explicit_fields_json, project,
                    narration_id, output, created_at, started_at, finished_at,
                    progress_json, result_json, error_json, cancellation_requested,
                    event_sequence, queue_order, retry_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _job_values(stored),
            )
            connection.execute(
                "INSERT INTO job_events (job_id, sequence, timestamp, event_json) "
                "VALUES (?, ?, ?, ?)",
                (job.id, event.sequence, event.timestamp, _json(event.event)),
            )
        return stored

    def update_job(self, job: StoredJob) -> None:
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET
                    state = ?, project = ?, narration_id = ?, output = ?,
                    started_at = ?, finished_at = ?, progress_json = ?,
                    result_json = ?, error_json = ?, cancellation_requested = ?,
                    event_sequence = ?, retry_of = ?
                WHERE id = ?
                """,
                (
                    job.state,
                    job.project,
                    job.narration_id,
                    job.output,
                    job.started_at,
                    job.finished_at,
                    job.progress_json,
                    job.result_json,
                    job.error_json,
                    int(job.cancellation_requested),
                    job.event_sequence,
                    job.retry_of,
                    job.id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown job id: {job.id}")

    def append_event(
        self, job: StoredJob, event: StoredJobEvent, *, limit: int
    ) -> None:
        if limit < 1:
            raise ValueError("Event history limit must be positive.")
        with self._transaction() as connection:
            self._update_job_row(connection, job)
            connection.execute(
                "INSERT INTO job_events (job_id, sequence, timestamp, event_json) "
                "VALUES (?, ?, ?, ?)",
                (job.id, event.sequence, event.timestamp, _json(event.event)),
            )
            first_kept = max(1, event.sequence - limit + 1)
            connection.execute(
                "DELETE FROM job_events WHERE job_id = ? AND sequence < ?",
                (job.id, first_kept),
            )

    def get_job(self, job_id: str) -> StoredJob | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return None if row is None else _stored_job(row)

    def list_jobs(self) -> tuple[StoredJob, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs ORDER BY queue_order"
            ).fetchall()
        return tuple(_stored_job(row) for row in rows)

    def list_events(self, job_id: str, *, after: int = 0) -> tuple[StoredJobEvent, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT sequence, timestamp, event_json FROM job_events
                WHERE job_id = ? AND sequence > ? ORDER BY sequence
                """,
                (job_id, after),
            ).fetchall()
        return tuple(_stored_event(row) for row in rows)

    def pending_jobs(self) -> tuple[StoredJob, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs WHERE state = 'queued' ORDER BY queue_order"
            ).fetchall()
        return tuple(_stored_job(row) for row in rows)

    def delete_jobs(self, job_ids: tuple[str, ...]) -> None:
        if not job_ids:
            return
        placeholders = ", ".join("?" for _ in job_ids)
        with self._transaction() as connection:
            connection.execute(
                f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids
            )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def _update_job_row(self, connection: sqlite3.Connection, job: StoredJob) -> None:
        cursor = connection.execute(
            """
            UPDATE jobs SET
                state = ?, project = ?, narration_id = ?, output = ?,
                started_at = ?, finished_at = ?, progress_json = ?,
                result_json = ?, error_json = ?, cancellation_requested = ?,
                event_sequence = ?, retry_of = ?
            WHERE id = ?
            """,
            (
                job.state,
                job.project,
                job.narration_id,
                job.output,
                job.started_at,
                job.finished_at,
                job.progress_json,
                job.result_json,
                job.error_json,
                int(job.cancellation_requested),
                job.event_sequence,
                job.retry_of,
                job.id,
            ),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown job id: {job.id}")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise RuntimeError("Job store is closed.")
        self._lock.acquire()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()
        finally:
            self._lock.release()


def _job_values(job: StoredJob) -> tuple[object, ...]:
    return (
        job.id,
        job.state,
        job.request_json,
        job.explicit_fields_json,
        job.project,
        job.narration_id,
        job.output,
        job.created_at,
        job.started_at,
        job.finished_at,
        job.progress_json,
        job.result_json,
        job.error_json,
        int(job.cancellation_requested),
        job.event_sequence,
        job.queue_order,
        job.retry_of,
    )


def _stored_job(row: sqlite3.Row) -> StoredJob:
    return StoredJob(
        id=row["id"],
        state=row["state"],
        request_json=row["request_json"],
        explicit_fields_json=row["explicit_fields_json"],
        project=row["project"],
        narration_id=row["narration_id"],
        output=row["output"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        progress_json=row["progress_json"],
        result_json=row["result_json"],
        error_json=row["error_json"],
        cancellation_requested=bool(row["cancellation_requested"]),
        event_sequence=row["event_sequence"],
        queue_order=row["queue_order"],
        retry_of=row["retry_of"],
    )


def _stored_event(row: sqlite3.Row) -> StoredJobEvent:
    value = json.loads(row["event_json"])
    if not isinstance(value, dict):
        raise ValueError("Stored job event must be a JSON object.")
    return StoredJobEvent(
        sequence=row["sequence"],
        timestamp=row["timestamp"],
        event=value,
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
