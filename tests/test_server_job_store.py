from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ttsforge.server.job_store import SqliteJobStore, StoredJob, StoredJobEvent


def _job(job_id: str) -> StoredJob:
    return StoredJob(
        id=job_id,
        state="queued",
        request_json="{}",
        explicit_fields_json="[]",
        project=None,
        narration_id=None,
        output=None,
        created_at="2026-11-22T12:00:00+00:00",
        started_at=None,
        finished_at=None,
        progress_json=None,
        result_json=None,
        error_json=None,
        cancellation_requested=False,
        event_sequence=0,
    )


def _event(sequence: int, state: str) -> StoredJobEvent:
    return StoredJobEvent(
        sequence=sequence,
        timestamp=f"2026-11-22T12:00:0{sequence}+00:00",
        event={"type": "job.state", "state": state},
    )


def test_sqlite_job_store_persists_fifo_jobs_and_bounded_events(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    store = SqliteJobStore(database)
    first = store.create_job(_job("first"), _event(1, "queued"))
    second = store.create_job(_job("second"), _event(1, "queued"))

    running = replace(first, state="running", event_sequence=2)
    store.append_event(running, _event(2, "running"), limit=2)
    completed = replace(running, state="completed", event_sequence=3)
    store.append_event(completed, _event(3, "completed"), limit=2)
    store.update_job(replace(second, cancellation_requested=True))
    store.close()

    reopened = SqliteJobStore(database)
    jobs = reopened.list_jobs()
    assert [job.id for job in jobs] == ["first", "second"]
    assert [(job.id, job.queue_order) for job in jobs] == [("first", 1), ("second", 2)]
    assert jobs[0].state == "completed"
    assert jobs[1].cancellation_requested is True
    assert [event.sequence for event in reopened.list_events("first")] == [2, 3]
    assert [job.id for job in reopened.pending_jobs()] == ["second"]

    reopened.delete_jobs(("first",))
    assert reopened.get_job("first") is None
    assert reopened.list_events("first") == ()
    third = reopened.create_job(_job("third"), _event(1, "queued"))
    assert third.queue_order == 3
    reopened.close()
