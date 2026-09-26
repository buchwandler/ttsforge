"""Presentation tests for Readio's public progress events."""

from __future__ import annotations

from io import StringIO

from readio.api import ReadioEvent
from rich.console import Console

from ttsforge.progress import RichReadioProgress


def test_events_render_phases_counters_and_only_one_completion_line() -> None:
    output = StringIO()
    progress = RichReadioProgress(Console(file=output, force_terminal=False))

    events = [
        ReadioEvent(kind="operation.started", operation="projects.build"),
        ReadioEvent(
            kind="stage.started",
            operation="projects.build",
            stage="synthesis",
        ),
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            completed=2,
            total=5,
        ),
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            completed=2,
            total=5,
        ),
        ReadioEvent(kind="operation.completed", operation="projects.build"),
        ReadioEvent(kind="operation.completed", operation="projects.build"),
    ]
    for event in events:
        progress(event)

    rendered = output.getvalue()
    assert "Building audiobook" in rendered
    assert "Synthesizing" in rendered
    assert "Synthesizing: 2/5" in rendered
    assert rendered.count("Done") == 1


def test_audio_duration_events_use_readio_counters() -> None:
    output = StringIO()
    progress = RichReadioProgress(Console(file=output, force_terminal=False))

    progress(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="composition",
            audio_seconds=12.5,
            total_audio_seconds=42.0,
        )
    )

    assert "Composing audiobook: 12.5/42.0 seconds" in output.getvalue()


def test_json_mode_suppresses_human_progress() -> None:
    output = StringIO()
    progress = RichReadioProgress(
        Console(file=output, force_terminal=False), json_mode=True
    )

    progress(ReadioEvent(kind="operation.started", operation="projects.build"))
    progress(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            completed=1,
            total=3,
        )
    )

    assert output.getvalue() == ""
