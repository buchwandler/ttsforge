"""Progress rendering tests for normalized Readio workflow events."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from ttsforge.application.events import ApplicationEvent
from ttsforge.progress import (
    LineReadioProgress,
    LiveReadioProgress,
    NullReadioProgress,
    RichReadioProgress,
)


def test_line_renderer_shows_stage_selector_progress_and_completion() -> None:
    output = StringIO()
    progress = LineReadioProgress(Console(file=output, force_terminal=False))
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            package="voicerender",
            selector="chapter-2",
            current=2,
            total=3,
        )
    )
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.completed",
            message="Chapter rendered",
            package="voicerender",
            selector="chapter-2",
            current=3,
            total=3,
        )
    )

    rendered = output.getvalue()
    assert "Rendering speech · chapter-2: 2/3" in rendered
    assert "Chapter rendered" in rendered
    assert progress.state.completed is True
    progress.close()


def test_unknown_workflow_event_is_rendered_without_provider_assumptions() -> None:
    output = StringIO()
    progress = LineReadioProgress(Console(file=output, force_terminal=False))

    progress(ApplicationEvent(stage="future_stage", kind="future.event"))

    assert "Future stage: future.event" in output.getvalue()


def test_live_renderer_handles_completion_and_closes() -> None:
    output = StringIO()
    progress = LiveReadioProgress(Console(file=output, force_terminal=False, width=100))
    progress(
        ApplicationEvent(
            stage="export",
            kind="stage.started",
            message="Writing M4B",
        )
    )
    progress(
        ApplicationEvent(
            stage="export",
            kind="stage.completed",
            message="M4B written",
            current=1,
            total=1,
            elapsed_seconds=2.5,
        )
    )
    progress.close()

    assert "Writing M4B" in output.getvalue()
    assert "M4B written" in output.getvalue()


def test_json_progress_sinks_are_silent() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    event = ApplicationEvent(stage="render", kind="stage.started")
    NullReadioProgress()(event)
    RichReadioProgress(console, json_mode=True)(event)

    assert output.getvalue() == ""
