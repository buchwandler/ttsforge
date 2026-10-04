from __future__ import annotations

import json
import subprocess
import sys

from ttsforge.application.events import ApplicationEvent, ProgressState


def test_application_events_serialize_and_reduce_without_frontend_types() -> None:
    event = ApplicationEvent(
        kind="progress",
        operation="projects.build",
        stage="synthesis",
        progress_kind="unit.completed",
        completed=1,
        total=1,
        scope_id="chapter-1",
        unit_id="unit-1",
    )
    state = ProgressState()
    state.set_chapters(("chapter-1", "chapter-2"))
    state.reduce(event)

    assert json.loads(json.dumps(event.to_dict()))["scope_id"] == "chapter-1"
    assert state.current_scope_id == "chapter-1"
    assert state.scopes["chapter-1"].current_unit_id == "unit-1"
    assert state.completed_chapters == 1


def test_cache_event_reduces_cached_and_missing_chapters() -> None:
    state = ProgressState()
    state.set_chapters(("cached", "rendered"))
    state.reduce(
        ApplicationEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            progress_kind="phase",
            message="Synthesis cache scanned",
            details={
                "reused": 2,
                "missing": 1,
                "per_scope": {
                    "cached": {"required": 2, "reused": 2, "rendered": 0},
                    "rendered": {"required": 1, "reused": 0, "rendered": 1},
                },
            },
        )
    )

    assert state.cache_reused == 2
    assert state.cache_missing == 1
    assert state.completed_chapters == 1


def test_application_import_does_not_load_frontend_or_readio_dependencies() -> None:
    script = """
import sys
import ttsforge.application

forbidden = {"rich", "typer", "readio", "PySide6", "PyQt6", "tkinter"}
loaded = {name.partition(".")[0] for name in sys.modules}
assert not loaded.intersection(forbidden)
"""
    subprocess.run([sys.executable, "-c", script], check=True)
