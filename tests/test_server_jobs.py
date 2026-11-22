from __future__ import annotations

import sys
import time
from pathlib import Path

from ttsforge.application.models import (
    AudiobookRequest,
    ConversionResultView,
    InputOverrides,
)
from ttsforge.server.jobs import JobManager, JobState

_SUCCESS_WORKER = r"""
import json
import sys
payload = json.loads(sys.stdin.read())
assert payload["debug"] is False
sys.stderr.write("worker diagnostic\n")
messages = [
    {"type": "job.state", "state": "preparing"},
    {
        "type": "job.prepared",
        "project": "/books/book.ttsforge",
        "output": "/books/book.m4b",
    },
    {"type": "job.state", "state": "running"},
    {"type": "workflow.event", "event": {
        "stage": "render", "kind": "stage.progress", "package": "voicerender",
        "selector": "5-7", "current": 2, "total": 3,
        "elapsed_seconds": 4.5,
        "details": {"chapter_number": 6, "chapter_title": "Chapter six"}
    }},
    {"type": "job.result", "result": {
        "output": "/books/book.m4b", "workspace": "/books/book.ttsforge",
        "workspace_mode": "modern", "executed_stages": ["render", "export"],
        "reused_stages": ["convert"], "warnings": [], "variant": None
    }}
]
for message in messages:
    print(json.dumps(message), flush=True)
"""


def _request(tmp_path: Path) -> AudiobookRequest:
    return AudiobookRequest(source=tmp_path / "book.epub")


def _manager(
    worker_script: str,
    *,
    event_history_limit: int = 1000,
    max_terminal_jobs: int = 100,
    max_active_jobs: int = 1,
) -> JobManager:
    return JobManager(
        event_history_limit=event_history_limit,
        max_terminal_jobs=max_terminal_jobs,
        max_active_jobs=max_active_jobs,
        cancel_grace_seconds=0.2,
        worker_command=(sys.executable, "-u", "-c", worker_script),
    )


def _wait_for_state(
    manager: JobManager, job_id: str, state: JobState, timeout: float = 5.0
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.get(job_id)
        if record.state is state:
            return record
        if record.state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
            break
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not reach state {state.value}.")


def test_worker_lifecycle_progress_and_bounded_event_sequence(tmp_path: Path) -> None:
    manager = _manager(_SUCCESS_WORKER, event_history_limit=3)
    try:
        submitted = manager.submit(
            _request(tmp_path), InputOverrides(frozenset({"source", "voice"}))
        )
        record = _wait_for_state(manager, submitted.id, JobState.COMPLETED)
        page = manager.events(submitted.id)
        later = manager.events(submitted.id, after=record.event_sequence - 1)

        assert submitted.state is JobState.QUEUED
        assert record.started_at is not None
        assert record.finished_at is not None
        assert record.project == Path("/books/book.ttsforge")
        assert record.output == Path("/books/book.m4b")
        assert record.progress is not None
        assert record.progress.current == 2
        assert record.progress.details["chapter_title"] == "Chapter six"
        assert record.result == ConversionResultView(
            output=Path("/books/book.m4b"),
            workspace=Path("/books/book.ttsforge"),
            workspace_mode="modern",
            executed_stages=("render", "export"),
            reused_stages=("convert",),
        )
        assert record.error is None
        assert [event.sequence for event in page.events] == [
            record.event_sequence - 2,
            record.event_sequence - 1,
            record.event_sequence,
        ]
        assert page.next == record.event_sequence
        assert page.first == record.event_sequence - 2
        assert page.truncated is True
        assert later.first == page.first
        assert later.truncated is False
        assert [event.sequence for event in later.events] == [record.event_sequence]
    finally:
        manager.shutdown()


def test_terminal_job_retention_and_list_pagination_preserve_active_jobs(
    tmp_path: Path,
) -> None:
    script = r"""
import json, sys, time
payload = json.loads(sys.stdin.read())
messages = [
    {"type": "job.state", "state": "preparing"},
    {"type": "job.prepared", "project": "/projects/job", "output": "/out.m4b"},
    {"type": "job.state", "state": "running"},
]
for message in messages:
    print(json.dumps(message), flush=True)
if payload["request"]["source"].endswith("active.epub"):
    time.sleep(30)
else:
    print(json.dumps({"type": "job.result", "result": {
        "output": "/out.m4b", "workspace": "/projects/job",
        "workspace_mode": "modern", "executed_stages": [],
        "reused_stages": [], "warnings": [], "variant": None
    }}), flush=True)
"""
    manager = _manager(script, max_terminal_jobs=2, max_active_jobs=2)
    try:
        active = manager.submit(AudiobookRequest(source=tmp_path / "active.epub"))
        _wait_for_state(manager, active.id, JobState.RUNNING)
        completed = []
        for index in range(4):
            record = manager.submit(
                AudiobookRequest(source=tmp_path / f"complete-{index}.epub")
            )
            completed.append(record.id)
            _wait_for_state(manager, record.id, JobState.COMPLETED)

        listed = manager.list_jobs(state=JobState.COMPLETED, limit=10)
        older_page = manager.list_jobs(
            state=JobState.COMPLETED, limit=1, before=listed[0].id
        )
        all_jobs = manager.list_jobs(limit=10)

        assert [record.id for record in listed] == completed[-2:][::-1]
        assert [record.id for record in older_page] == [listed[1].id]
        assert active.id in {record.id for record in all_jobs}
        assert len(listed) == 2
        assert manager.get(active.id).state is JobState.RUNNING
    finally:
        manager.shutdown()


def test_worker_structured_error_is_preserved(tmp_path: Path) -> None:
    script = r"""
import json, sys
json.loads(sys.stdin.read())
print(json.dumps({"type": "job.error", "error": {
    "type": "WorkflowFailureError", "message": "Render failed",
    "category": "render", "stage": "render", "package": "voicerender",
    "code": "render_failed", "details": {"retryable": False}
}}), flush=True)
sys.exit(1)
"""
    manager = _manager(script)
    try:
        submitted = manager.submit(_request(tmp_path))
        record = _wait_for_state(manager, submitted.id, JobState.FAILED)

        assert record.error is not None
        assert record.error.type == "WorkflowFailureError"
        assert record.error.category == "render"
        assert record.error.stage == "render"
        assert record.error.details == {"retryable": False}
        assert record.result is None
    finally:
        manager.shutdown()


def test_malformed_stdout_fails_job_with_a_structured_protocol_error(
    tmp_path: Path,
) -> None:
    script = "import sys; sys.stdin.read(); print('not-json', flush=True)"
    manager = _manager(script)
    try:
        submitted = manager.submit(_request(tmp_path))
        record = _wait_for_state(manager, submitted.id, JobState.FAILED)

        assert record.error is not None
        assert record.error.type == "WorkerProtocolError"
        assert record.error.code == "worker_protocol_error"
        assert "not-json" not in record.error.message
    finally:
        manager.shutdown()


def test_cancel_terminates_running_worker_and_queued_jobs_do_not_start(
    tmp_path: Path,
) -> None:
    script = r"""
import json, sys, time
json.loads(sys.stdin.read())
print(json.dumps({"type": "job.state", "state": "running"}), flush=True)
time.sleep(30)
"""
    manager = _manager(script)
    try:
        running = manager.submit(_request(tmp_path))
        _wait_for_state(manager, running.id, JobState.RUNNING)
        queued = manager.submit(_request(tmp_path))
        queued_record = manager.cancel(queued.id)
        running_record = manager.cancel(running.id)

        assert queued_record.state is JobState.CANCELLED
        assert running_record.state in {JobState.RUNNING, JobState.CANCELLED}
        cancelled = _wait_for_state(manager, running.id, JobState.CANCELLED)
        assert cancelled.finished_at is not None
        assert manager.get(queued.id).started_at is None
        assert manager.get(running.id).state is JobState.CANCELLED
    finally:
        manager.shutdown()


def test_shutdown_cancels_active_worker_and_preserves_server_process(
    tmp_path: Path,
) -> None:
    script = r"""
import json, sys, time
json.loads(sys.stdin.read())
print(json.dumps({"type": "job.state", "state": "running"}), flush=True)
time.sleep(30)
"""
    manager = _manager(script)
    submitted = manager.submit(_request(tmp_path))
    _wait_for_state(manager, submitted.id, JobState.RUNNING)

    manager.shutdown()

    assert manager.get(submitted.id).state is JobState.CANCELLED
    assert manager._scheduler.is_alive() is False
