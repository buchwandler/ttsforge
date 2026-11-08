from __future__ import annotations

import json
import subprocess
import sys

from ttsforge.application.events import ApplicationEvent, ProgressState


def test_normalized_workflow_event_serializes_and_reduces() -> None:
    event = ApplicationEvent(
        stage="render",
        kind="stage.progress",
        message="Rendering chapter",
        package="voicerender",
        selector="chapter-1",
        current=2,
        total=4,
        elapsed_seconds=1.5,
        details={"attempt": 1},
    )
    state = ProgressState()
    state.reduce(event)

    payload = json.loads(json.dumps(event.to_dict()))
    assert payload["stage"] == "render"
    assert payload["package"] == "voicerender"
    assert payload["selector"] == "chapter-1"
    assert payload["current"] == 2
    assert state.current == 2
    assert state.total == 4
    assert state.completed is False


def test_stage_completion_updates_progress_state() -> None:
    state = ProgressState()
    state.reduce(
        ApplicationEvent(
            stage="export",
            kind="stage.completed",
            message="M4B written",
            current=1,
            total=1,
        )
    )

    assert state.stage == "export"
    assert state.message == "M4B written"
    assert state.completed is True


def test_application_import_does_not_load_frontend_or_readio_dependencies() -> None:
    script = """
import sys
import ttsforge.application

forbidden = {"rich", "typer", "readio", "PySide6", "PyQt6", "tkinter"}
loaded = {name.partition(".")[0] for name in sys.modules}
assert not loaded.intersection(forbidden)
"""
    subprocess.run([sys.executable, "-c", script], check=True)
