from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient

from ttsforge.server.app import create_app
from ttsforge.server.jobs import JobManager

_FIXTURE = Path(__file__).parent / "fixtures" / "studio_job_contract.json"
_AUTH_HEADERS = {"Authorization": "Bearer job-test-token"}


_BLOCKING_WORKER = r"""
import json, sys, time
payload = json.loads(sys.stdin.read())
assert payload["request"]["source"].endswith("book.epub")
messages = [
    {"type": "job.state", "state": "preparing"},
    {
        "type": "job.prepared",
        "project": "/books/book.ttsforge",
        "output": "/books/book.m4b",
    },
    {"type": "job.state", "state": "running"},
    {"type": "workflow.event", "event": {
        "stage": "render", "kind": "stage.progress", "current": 1, "total": 2,
        "elapsed_seconds": 2.5, "details": {"chapter_number": 5}
    }}
]
for message in messages:
    print(json.dumps(message), flush=True)
time.sleep(30)
"""


_SUCCESS_WORKER = r"""
import json, sys
json.loads(sys.stdin.read())
messages = [
    {"type": "job.state", "state": "running"},
    {"type": "job.result", "result": {
        "output": "/books/book.m4b", "workspace": "/books/book.ttsforge",
        "workspace_mode": "modern", "executed_stages": ["render", "export"],
        "reused_stages": ["convert"], "warnings": ["used cached cover"],
        "variant": "kokoro-target-voice"
    }}
]
for message in messages:
    print(json.dumps(message), flush=True)
"""


def _app(
    tmp_path: Path,
    script: str,
    *,
    event_history_limit: int = 1000,
    max_terminal_jobs: int = 100,
    max_active_jobs: int = 1,
) -> tuple[object, JobManager]:
    manager = JobManager(
        event_history_limit=event_history_limit,
        max_terminal_jobs=max_terminal_jobs,
        max_active_jobs=max_active_jobs,
        cancel_grace_seconds=0.2,
        worker_command=(sys.executable, "-u", "-c", script),
    )
    app = create_app(
        token="job-test-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(audiobook=None, catalog=None, conversion=None),
        job_manager=manager,
    )
    return app, manager


def _submission(source: Path) -> dict[str, object]:
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    submission = contract["submission"]
    submission["request"]["source"] = str(source)
    return submission


def _wait_for_progress(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=_AUTH_HEADERS)
        payload = response.json()
        if payload["progress"] is not None:
            return payload
        time.sleep(0.01)
    raise AssertionError("Job did not publish a progress event.")


def _wait_for_state(client: TestClient, job_id: str, state: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}", headers=_AUTH_HEADERS).json()
        if payload["state"] == state:
            return payload
        if payload["state"] in {"failed", "cancelled"}:
            break
        time.sleep(0.01)
    raise AssertionError(f"Job did not reach {state}.")


def test_job_api_create_poll_events_cancel_and_golden_contract(
    tmp_path: Path,
) -> None:
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    app, _ = _app(tmp_path, _BLOCKING_WORKER, event_history_limit=3)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/jobs",
            headers=_AUTH_HEADERS,
            json=_submission(tmp_path / "book.epub"),
        )
        job_id = created.json()["id"]
        assert uuid.UUID(job_id)
        assert created.status_code == 202
        assert created.json()["state"] == contract["created"]["state"]

        status = _wait_for_progress(client, job_id)
        assert set(contract["status_required_fields"]) <= status.keys()
        assert status["state"] == "running"
        assert status["project"] == "/books/book.ttsforge"
        assert status["output"] == "/books/book.m4b"
        assert status["progress"]["stage"] == "render"
        assert status["progress"]["details"]["chapter_number"] == 5

        events = client.get(
            f"/api/v1/jobs/{job_id}/events?after=0", headers=_AUTH_HEADERS
        ).json()
        assert set(contract["event_page_required_fields"]) <= events.keys()
        assert events["next"] == status["event_sequence"]
        assert events["first"] > 1
        assert events["truncated"] is True
        assert events["events"]
        assert set(contract["event_required_fields"]) <= events["events"][-1].keys()
        assert [item["seq"] for item in events["events"]] == sorted(
            item["seq"] for item in events["events"]
        )

        cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=_AUTH_HEADERS)
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "cancelled"
        after_cancel = client.get(
            f"/api/v1/jobs/{job_id}/events?after={events['next']}",
            headers=_AUTH_HEADERS,
        ).json()
        assert after_cancel["events"][-1]["event"] == {
            "type": "job.state",
            "state": "cancelled",
        }
        assert (
            client.get("/api/v1/jobs/missing", headers=_AUTH_HEADERS).status_code == 404
        )
        assert (
            client.post(
                "/api/v1/jobs/missing/cancel", headers=_AUTH_HEADERS
            ).status_code
            == 404
        )


def test_job_listing_filters_and_paginates_without_event_histories(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _SUCCESS_WORKER)

    with TestClient(app) as client:
        submitted_ids = []
        for index in range(3):
            created = client.post(
                "/api/v1/jobs",
                headers=_AUTH_HEADERS,
                json=_submission(tmp_path / f"book-{index}.epub"),
            )
            submitted_ids.append(created.json()["id"])
            _wait_for_state(client, submitted_ids[-1], "completed")

        latest = client.get(
            "/api/v1/jobs?limit=2&state=completed", headers=_AUTH_HEADERS
        ).json()["jobs"]
        older = client.get(
            "/api/v1/jobs",
            params={"limit": 2, "state": "completed", "before": latest[-1]["id"]},
            headers=_AUTH_HEADERS,
        ).json()["jobs"]
        failed = client.get("/api/v1/jobs?state=failed", headers=_AUTH_HEADERS).json()[
            "jobs"
        ]

    assert [job["id"] for job in latest] == submitted_ids[-2:][::-1]
    assert [job["id"] for job in older] == [submitted_ids[0]]
    assert not failed
    assert set(latest[0]) == {
        "id",
        "state",
        "created_at",
        "started_at",
        "finished_at",
        "project",
        "output",
        "event_sequence",
    }


def test_job_status_serializes_successful_conversion_result(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, _SUCCESS_WORKER)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/jobs",
            headers=_AUTH_HEADERS,
            json=_submission(tmp_path / "book.epub"),
        )
        job_id = created.json()["id"]
        status = _wait_for_state(client, job_id, "completed")

    assert status["result"] == {
        "output": "/books/book.m4b",
        "workspace": "/books/book.ttsforge",
        "workspace_mode": "modern",
        "executed_stages": ["render", "export"],
        "reused_stages": ["convert"],
        "warnings": ["used cached cover"],
        "variant": "kokoro-target-voice",
    }
    assert status["error"] is None
    assert status["finished_at"] is not None


def test_job_submission_rejects_invalid_explicit_fields_before_queueing(
    tmp_path: Path,
) -> None:
    app, manager = _app(tmp_path, _SUCCESS_WORKER)
    submission = _submission(tmp_path / "book.epub")
    submission["explicit_fields"].append("unknown")

    with TestClient(app) as client:
        response = client.post("/api/v1/jobs", headers=_AUTH_HEADERS, json=submission)

    assert response.status_code == 400
    assert manager._jobs == {}
