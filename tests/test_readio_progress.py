"""Scoped reducer and terminal rendering tests for public Readio progress."""

from __future__ import annotations

from io import StringIO

from readio.api import AudiobookProjectChapter
from rich.console import Console

from ttsforge.application.events import ApplicationEvent as ReadioEvent
from ttsforge.progress import (
    LineReadioProgress,
    LiveReadioProgress,
    NullReadioProgress,
    ReadioProgressState,
)


def _chapters() -> tuple[AudiobookProjectChapter, ...]:
    return (
        AudiobookProjectChapter(1, "scope-1", "First", 0),
        AudiobookProjectChapter(2, "scope-2", "Second", 0),
    )


def _scope_ids() -> tuple[str, ...]:
    return tuple(chapter.scope_id for chapter in _chapters())


def _segment_event(
    kind: str,
    scope: str,
    *,
    completed: int,
    total: int,
    segment: str,
) -> ReadioEvent:
    return ReadioEvent(
        kind="progress",
        operation="projects.build",
        stage="synthesis",
        progress_kind=kind,  # type: ignore[arg-type]
        completed=completed,
        total=total,
        scope_id=scope,
        segment_id=segment,
    )


def test_scope_counters_are_isolated_and_overall_progress_never_regresses() -> None:
    state = ReadioProgressState()
    state.set_chapters(_scope_ids())
    state.reduce(
        _segment_event("segment.started", "scope-1", completed=0, total=2, segment="a")
    )
    state.reduce(
        _segment_event(
            "segment.completed", "scope-1", completed=1, total=2, segment="a"
        )
    )
    state.reduce(
        _segment_event("segment.started", "scope-2", completed=0, total=5, segment="b")
    )
    state.reduce(
        _segment_event(
            "segment.completed", "scope-2", completed=1, total=5, segment="b"
        )
    )

    assert state.scopes["scope-1"].completed == 1
    assert state.scopes["scope-1"].total == 2
    assert state.scopes["scope-2"].completed == 1
    assert state.scopes["scope-2"].total == 5
    assert state.completed_chapters == 0

    state.reduce(
        _segment_event(
            "segment.completed", "scope-1", completed=2, total=2, segment="c"
        )
    )
    assert state.completed_chapters == 1
    assert state.scopes["scope-2"].completed == 1

    state.reduce(
        _segment_event(
            "segment.completed", "scope-2", completed=5, total=5, segment="z"
        )
    )
    assert state.completed_chapters == 2


def test_phase_and_cache_events_update_status_and_fully_cached_scopes() -> None:
    state = ReadioProgressState()
    state.set_chapters(_scope_ids())
    state.reduce(
        ReadioEvent(
            kind="stage.started",
            operation="projects.build",
            stage="synthesis",
        )
    )
    state.reduce(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            progress_kind="phase",
            message="Synthesis cache scanned",
            details={
                "reused": 4,
                "missing": 3,
                "per_scope": {
                    "scope-1": {"required": 4, "reused": 4, "rendered": 0},
                    "scope-2": {"required": 3, "reused": 0, "rendered": 3},
                },
            },
        )
    )

    assert state.phase_message == "Synthesis cache scanned"
    assert state.cache_reused == 4
    assert state.cache_missing == 3
    assert state.scopes["scope-1"].finished is True
    assert state.scopes["scope-2"].finished is False
    assert state.scopes["scope-2"].total == 3
    assert state.completed_chapters == 1


def test_unknown_scope_is_safe_and_does_not_change_selected_chapter_total() -> None:
    state = ReadioProgressState()
    state.set_chapters(_scope_ids())
    state.reduce(
        _segment_event(
            "segment.completed", "future-scope", completed=1, total=1, segment="x"
        )
    )

    assert state.current_scope_id == "future-scope"
    assert state.scopes["future-scope"].finished is True
    assert state.completed_chapters == 0


def test_unit_progress_tracks_current_unit_and_completes_scope() -> None:
    state = ReadioProgressState()
    state.set_chapters(_scope_ids())
    state.reduce(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            progress_kind="unit.started",
            completed=0,
            total=1,
            scope_id="scope-1",
            unit_id="unit-1",
        )
    )
    state.reduce(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            progress_kind="unit.completed",
            completed=1,
            total=1,
            scope_id="scope-1",
            unit_id="unit-1",
        )
    )

    assert state.scopes["scope-1"].current_unit_id == "unit-1"
    assert state.scopes["scope-1"].finished is True
    assert state.completed_chapters == 1


def test_line_renderer_prints_milestones_and_chapter_completion_not_each_segment() -> (
    None
):
    output = StringIO()
    progress = LineReadioProgress(Console(file=output, force_terminal=False))
    progress.set_chapters(_chapters())
    progress(ReadioEvent(kind="operation.started", operation="projects.build"))
    progress(
        ReadioEvent(
            kind="stage.started",
            operation="projects.build",
            stage="synthesis",
        )
    )
    progress(
        ReadioEvent(
            kind="progress",
            operation="projects.build",
            stage="synthesis",
            progress_kind="phase",
            message="Synthesis cache scanned",
            details={"reused": 4, "missing": 0},
        )
    )
    progress(
        _segment_event("segment.started", "scope-1", completed=0, total=2, segment="a")
    )
    progress(
        _segment_event(
            "segment.completed", "scope-1", completed=1, total=2, segment="a"
        )
    )
    progress(
        _segment_event(
            "segment.completed", "scope-1", completed=2, total=2, segment="b"
        )
    )

    rendered = output.getvalue()
    assert "Building audiobook" in rendered
    assert "Synthesizing speech" in rendered
    assert "Cache: 4 reused · 0 to synthesize" in rendered
    assert "Synthesis: chapter 1/2 complete" in rendered
    assert "segment" not in rendered


def test_live_renderer_maps_scope_to_chapter_and_updates_in_place() -> None:
    output = StringIO()
    progress = LiveReadioProgress(Console(file=output, force_terminal=False, width=100))
    progress.set_chapters(_chapters())
    progress(ReadioEvent(kind="operation.started", operation="projects.build"))
    progress(
        _segment_event(
            "segment.completed", "scope-1", completed=1, total=1, segment="x"
        )
    )
    progress(ReadioEvent(kind="operation.completed", operation="projects.build"))

    rendered = output.getvalue()
    assert "Building audiobook" in rendered
    assert "Chapter 1 — First" in rendered
    assert "Overall" in rendered
    assert "Status" in rendered


def test_live_renderer_falls_back_to_an_unknown_scope_id() -> None:
    output = StringIO()
    progress = LiveReadioProgress(Console(file=output, force_terminal=False, width=100))
    progress.set_chapters(_chapters())
    progress(ReadioEvent(kind="operation.started", operation="projects.build"))
    progress(
        _segment_event(
            "segment.completed",
            "future-scope",
            completed=1,
            total=1,
            segment="unknown",
        )
    )
    progress(ReadioEvent(kind="operation.completed", operation="projects.build"))

    assert "future-scope" in output.getvalue()


def test_null_renderer_emits_nothing() -> None:
    output = StringIO()
    progress = NullReadioProgress()
    progress(
        ReadioEvent(
            kind="operation.started",
            operation="projects.build",
        )
    )
    assert output.getvalue() == ""
