"""Progress rendering tests for normalized Readio workflow events."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from ttsforge.application.events import ApplicationEvent, ProgressState
from ttsforge.application.models import BookChapterView
from ttsforge.cli.progress import _ChapterProgressContext
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
    assert "Selection chapter-2: 2/3 (66%)" in rendered
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


def test_progress_state_preserves_explicit_chapter_and_ignores_counters() -> None:
    state = ProgressState()
    state.reduce(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            current=6,
            total=100,
            details={"chapter_id": "c6"},
        )
    )
    state.reduce(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            current=7,
            total=100,
        )
    )

    assert state.chapter_id == "c6"
    assert state.chapter_number is None
    assert state.chapter_title is None

    state.reduce(
        ApplicationEvent(
            stage="export",
            kind="stage.started",
        )
    )
    assert state.chapter_id is None


def test_chapter_context_resolves_source_id_and_selected_position() -> None:
    chapters = tuple(
        BookChapterView(number, f"Chapter {number}", f"c{number}")
        for number in range(1, 18)
    )
    context = _ChapterProgressContext(chapters, "5-17")
    state = ProgressState()
    state.reduce(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            details={"chapter_id": "c10"},
        )
    )

    chapter = context.resolve(state)

    assert chapter is not None
    assert chapter.number == 10
    assert chapter.title == "Chapter 10"
    assert chapter.position == 6
    assert chapter.total == 13


def test_chapter_context_prefers_source_id_then_number_then_event_title() -> None:
    chapters = tuple(
        BookChapterView(number, f"Chapter {number}", f"c{number}")
        for number in range(1, 18)
    )
    context = _ChapterProgressContext(chapters, "5-17")
    state = ProgressState()
    state.reduce(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            details={
                "chapter_id": "c10",
                "chapter_number": 11,
                "chapter_title": "Event title",
            },
        )
    )

    chapter = context.resolve(state)
    assert chapter is not None
    assert (chapter.number, chapter.title) == (10, "Chapter 10")

    state.reduce(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            details={"chapter_number": 20, "chapter_title": "Event title"},
        )
    )
    chapter = context.resolve(state)
    assert chapter is not None
    assert (chapter.number, chapter.title) == (20, "Event title")
    assert chapter.position is None
    assert chapter.total is None


def test_live_renderer_tracks_workflow_and_stage_clocks() -> None:
    now = [100.0]
    output = StringIO()
    progress = LiveReadioProgress(
        Console(file=output, force_terminal=False, width=120),
        clock=lambda: now[0],
    )
    progress(ApplicationEvent(stage="render", kind="stage.started"))

    now[0] = 110.0
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            current=25,
            total=100,
            elapsed_seconds=900.0,
        )
    )
    assert progress.elapsed_seconds == 10.0
    assert progress._has_stage_eta() is True
    task = progress._progress.tasks[0]
    assert (task.completed, task.total) == (25, 100)

    now[0] = 150.0
    progress(ApplicationEvent(stage="compose", kind="stage.started"))
    assert progress._workflow_started_at == 100.0
    assert progress._stage_started_at == 150.0
    assert progress._has_stage_eta() is False

    now[0] = 170.0
    progress.close(success=True)
    assert progress.elapsed_seconds == 70.0
    assert progress.state.completed is True
    task = progress._progress.tasks[0]
    assert (task.completed, task.total) == (1, 1)
    assert "Elapsed" in output.getvalue()
    assert "Stage time" in output.getvalue()


def test_live_renderer_completes_known_and_indeterminate_stages() -> None:
    progress = LiveReadioProgress(
        Console(file=StringIO(), force_terminal=False),
        clock=lambda: 100.0,
    )
    progress(ApplicationEvent(stage="render", kind="stage.started"))
    task = progress._progress.tasks[0]
    assert task.total is None
    assert task.completed == 0

    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            current=50,
            total=100,
        )
    )
    progress(ApplicationEvent(stage="render", kind="stage.completed"))
    assert (task.completed, task.total) == (100, 100)
    assert progress._has_stage_eta() is False
    progress.close()

    indeterminate = LiveReadioProgress(
        Console(file=StringIO(), force_terminal=False),
        clock=lambda: 100.0,
    )
    indeterminate(ApplicationEvent(stage="compile", kind="stage.started"))
    indeterminate(ApplicationEvent(stage="compile", kind="stage.completed"))
    task = indeterminate._progress.tasks[0]
    assert (task.completed, task.total) == (1, 1)
    indeterminate.close()


def test_reused_stage_completes_without_eta() -> None:
    output = StringIO()
    progress = LiveReadioProgress(
        Console(file=output, force_terminal=False),
        clock=lambda: 100.0,
    )
    progress(
        ApplicationEvent(
            stage="export",
            kind="stage.reused",
            message="output checksum matches cache",
        )
    )

    task = progress._progress.tasks[0]
    assert (task.completed, task.total) == (1, 1)
    assert progress.state.reused is True
    assert progress._has_stage_eta() is False
    progress.close()
    assert "cached · output checksum matches cache" in output.getvalue()


def test_failed_live_close_does_not_force_stage_completion() -> None:
    progress = LiveReadioProgress(
        Console(file=StringIO(), force_terminal=False),
        clock=lambda: 100.0,
    )
    progress(ApplicationEvent(stage="render", kind="stage.started"))
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            current=25,
            total=100,
        )
    )

    progress.close(success=False)

    task = progress._progress.tasks[0]
    assert (task.completed, task.total) == (25, 100)
    assert progress.state.completed is False


def test_line_renderer_throttles_progress_to_ten_percent_buckets() -> None:
    output = StringIO()
    progress = LineReadioProgress(Console(file=output, force_terminal=False))
    progress(ApplicationEvent(stage="render", kind="stage.started"))
    for current in range(100):
        progress(
            ApplicationEvent(
                stage="render",
                kind="stage.progress",
                current=current,
                total=100,
            )
        )
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.completed",
            current=100,
            total=100,
        )
    )

    lines = output.getvalue().splitlines()
    assert len(lines) == 12
    assert "0/100 (0%)" in lines[1]
    assert "90/100 (90%)" in lines[-2]
    assert "100/100 (100%)" in lines[-1]


def test_line_renderer_emits_chapter_changes_between_progress_buckets() -> None:
    chapters = tuple(
        BookChapterView(number, f"Chapter {number}", f"c{number}")
        for number in range(1, 18)
    )
    output = StringIO()
    progress = LineReadioProgress(
        Console(file=output, force_terminal=False),
        chapters=chapters,
        selected_chapters="5-17",
    )
    progress(
        ApplicationEvent(
            stage="render",
            kind="stage.started",
            selector="5-17",
        )
    )
    for current, chapter_id in ((1, "c10"), (2, "c11"), (3, "c11")):
        progress(
            ApplicationEvent(
                stage="render",
                kind="stage.progress",
                selector="5-17",
                current=current,
                total=100,
                details={"chapter_id": chapter_id} if current < 3 else {},
            )
        )

    lines = output.getvalue().splitlines()
    assert len(lines) == 3
    assert "Selection 5-17" in lines[0]
    assert "Chapter 6/13 · 10 · Chapter 10" in lines[1]
    assert "Chapter 7/13 · 11 · Chapter 11" in lines[2]


def test_line_renderer_elapsed_time_uses_its_monotonic_clock() -> None:
    now = [100.0]
    progress = LineReadioProgress(
        Console(file=StringIO(), force_terminal=False),
        clock=lambda: now[0],
    )
    progress(ApplicationEvent(stage="render", kind="stage.started"))

    now[0] = 130.0
    assert progress.elapsed_seconds == 30.0
    now[0] = 165.0
    progress.close(success=True)
    assert progress.elapsed_seconds == 65.0
