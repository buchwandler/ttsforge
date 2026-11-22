from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydantic")

from ttsforge.application import AudiobookRequest, InputOverrides, InputValidationError
from ttsforge.application.events import ApplicationEvent
from ttsforge.application.models import ConversionResultView, ProjectPaths
from ttsforge.server.models import AudiobookRequestModel
from ttsforge.server.worker import run_worker


class FakeCoordinator:
    def __init__(self) -> None:
        self.request: AudiobookRequest | None = None
        self.overrides: InputOverrides | None = None

    def prepare(self, request: AudiobookRequest, overrides: InputOverrides):
        self.request = request
        self.overrides = overrides
        print("preparation diagnostic")
        return SimpleNamespace(
            preparation=SimpleNamespace(
                paths=ProjectPaths.for_root(Path("/books/project.ttsforge"))
            ),
            resolved=SimpleNamespace(request=request),
        )

    def execute(self, prepared, *, on_progress=None) -> ConversionResultView:
        del prepared
        print("execution diagnostic")
        assert on_progress is not None
        on_progress(
            ApplicationEvent(
                stage="render",
                kind="stage.progress",
                current=1,
                total=2,
                details={"chapter_number": 3},
            )
        )
        return ConversionResultView(
            output=Path("/books/book.m4b"),
            workspace=Path("/books/project.ttsforge"),
            workspace_mode="modern",
            executed_stages=("render", "export"),
            reused_stages=("convert",),
        )


def _payload(*, debug: bool = False) -> str:
    request = AudiobookRequestModel(
        source="~/books/book.epub",
        engine="kokoro",
        target="target-a",
        voice="voice-a",
        engine_options={"seed": 42, "extra": {"values": [True, None]}},
    )
    return json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "explicit_fields": ["source", "engine", "voice"],
            "debug": debug,
        }
    )


def test_worker_converts_request_and_keeps_stdout_protocol_only() -> None:
    coordinator = FakeCoordinator()
    protocol = io.StringIO()
    diagnostics = io.StringIO()

    result_code = run_worker(
        _payload(),
        protocol,
        diagnostics,
        service_factory=lambda: SimpleNamespace(conversion=coordinator),
    )
    messages = [json.loads(line) for line in protocol.getvalue().splitlines()]

    assert result_code == 0
    assert [message["type"] for message in messages] == [
        "job.state",
        "job.prepared",
        "job.state",
        "workflow.event",
        "job.result",
    ]
    assert messages[0]["state"] == "preparing"
    assert messages[1]["project"] == "/books/project.ttsforge"
    assert messages[3]["event"]["details"] == {"chapter_number": 3}
    assert messages[4]["result"]["output"] == "/books/book.m4b"
    assert coordinator.request is not None
    assert coordinator.request.source == Path.home() / "books" / "book.epub"
    assert coordinator.request.engine_options["extra"] == {"values": [True, None]}
    assert coordinator.overrides == InputOverrides(
        frozenset({"source", "engine", "voice"})
    )
    assert "preparation diagnostic" in diagnostics.getvalue()
    assert "execution diagnostic" in diagnostics.getvalue()
    assert "diagnostic" not in protocol.getvalue()


def test_worker_emits_structured_application_failures_without_tracebacks() -> None:
    class FailingCoordinator:
        def prepare(self, request, overrides):
            raise InputValidationError("The selected source is not a supported book.")

    protocol = io.StringIO()
    diagnostics = io.StringIO()
    result_code = run_worker(
        _payload(),
        protocol,
        diagnostics,
        service_factory=lambda: SimpleNamespace(conversion=FailingCoordinator()),
    )
    messages = [json.loads(line) for line in protocol.getvalue().splitlines()]

    assert result_code == 1
    assert messages[-1]["type"] == "job.error"
    assert messages[-1]["error"]["type"] == "InputValidationError"
    assert messages[-1]["error"]["message"] == (
        "The selected source is not a supported book."
    )
    assert "Traceback" not in diagnostics.getvalue()


def test_worker_debug_traceback_stays_on_diagnostics_stream() -> None:
    class UnexpectedCoordinator:
        def prepare(self, request, overrides):
            raise RuntimeError("private worker detail")

    protocol = io.StringIO()
    diagnostics = io.StringIO()
    result_code = run_worker(
        _payload(debug=True),
        protocol,
        diagnostics,
        service_factory=lambda: SimpleNamespace(conversion=UnexpectedCoordinator()),
    )
    messages = [json.loads(line) for line in protocol.getvalue().splitlines()]

    assert result_code == 1
    assert messages[-1]["error"]["message"] == "An unexpected error occurred."
    assert "private worker detail" not in protocol.getvalue()
    assert "Traceback" in diagnostics.getvalue()
    assert "private worker detail" in diagnostics.getvalue()


def test_worker_process_reserves_stdout_for_protocol() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ttsforge.server.worker"],
        input="{}",
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    messages = [json.loads(line) for line in result.stdout.splitlines()]

    assert result.returncode == 1
    assert [message["type"] for message in messages] == ["job.state", "job.error"]
    assert "Conversion worker failed: ValidationError" in result.stderr
