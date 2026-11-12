"""Rich progress renderers for normalized Readio workflow events."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from rich.console import Console, RenderableType
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    Task,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from ..application.events import ApplicationEvent, ProgressState
from ..application.models import BookChapterView
from ..chapter_selection import parse_chapter_selection

ReadioProgressState = ProgressState

_STAGE_LABELS = {
    "preflight": "Checking workflow",
    "convert": "Converting source",
    "compile": "Preparing speech",
    "render_plan": "Planning speech",
    "render": "Rendering speech",
    "compose": "Composing audiobook",
    "export": "Writing M4B",
}


def _stage_label(stage: str | None) -> str:
    if stage is None:
        return "Working"
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def _event_label(event: ApplicationEvent) -> str:
    label = _stage_label(event.stage)
    if event.selector:
        label = f"{label} · {event.selector}"
    elif event.package:
        label = f"{label} · {event.package}"
    if event.message:
        return f"{label}: {event.message}"
    if event.kind == "stage.started":
        return f"Starting {label.lower()}"
    if event.kind == "stage.completed":
        return f"Completed {label.lower()}"
    if event.current is not None and event.total is not None:
        return f"{label}: {event.current}/{event.total}"
    return f"{label}: {event.kind}"


@dataclass(frozen=True, slots=True)
class _ResolvedChapter:
    number: int | None
    title: str | None
    position: int | None
    total: int | None


class _ChapterProgressContext:
    def __init__(
        self,
        chapters: tuple[BookChapterView, ...],
        selected_chapters: str | None,
    ) -> None:
        self._by_number = {chapter.number: chapter for chapter in chapters}
        self._by_source_id = {
            chapter.source_id: chapter
            for chapter in chapters
            if chapter.source_id is not None
        }
        selector = selected_chapters if selected_chapters is not None else "all"
        try:
            selected_indices = parse_chapter_selection(selector, len(chapters))
        except ValueError:
            selected_indices = []
        selected_total = len(selected_indices)
        self._selected_positions = {
            chapters[index].number: (position, selected_total)
            for position, index in enumerate(selected_indices, 1)
        }

    def resolve(self, state: ProgressState) -> _ResolvedChapter | None:
        chapter = None
        if state.chapter_id is not None:
            chapter = self._by_source_id.get(state.chapter_id)
        if chapter is None and state.chapter_number is not None:
            chapter = self._by_number.get(state.chapter_number)

        number = chapter.number if chapter is not None else state.chapter_number
        title = chapter.title if chapter is not None else state.chapter_title
        if number is None and title is None:
            return None

        selection = self._selected_positions.get(number) if number is not None else None
        position, total = selection if selection is not None else (None, None)
        return _ResolvedChapter(number, title, position, total)


def _progress_bucket(current: int | None, total: int | None) -> int | None:
    if current is None or total is None or total <= 0 or current < 0 or current > total:
        return None
    return current * 10 // total


def _chapter_label(chapter: _ResolvedChapter) -> str:
    parts = []
    if chapter.position is not None and chapter.total is not None:
        parts.append(f"{chapter.position}/{chapter.total}")
    if chapter.number is not None:
        parts.append(str(chapter.number))
    if chapter.title:
        parts.append(chapter.title)
    return " · ".join(parts)


def _chapter_key(
    state: ProgressState,
    context: _ChapterProgressContext,
) -> tuple[object, ...] | None:
    chapter = context.resolve(state)
    if chapter is not None:
        return (chapter.number, chapter.title, chapter.position, chapter.total)
    if any((state.chapter_id, state.chapter_number, state.chapter_title)):
        return (state.chapter_id, state.chapter_number, state.chapter_title)
    return None


def _line_label(
    event: ApplicationEvent,
    state: ProgressState,
    context: _ChapterProgressContext,
) -> str:
    if event.stage not in _STAGE_LABELS:
        return _event_label(event)

    parts = [_stage_label(event.stage)]
    if event.package and not event.selector:
        parts.append(event.package)
    if event.selector:
        parts.append(f"Selection {event.selector}")
    chapter = context.resolve(state)
    if chapter is not None:
        parts.append(f"Chapter {_chapter_label(chapter)}")

    details = []
    if event.current is not None and event.total is not None and event.total > 0:
        percentage = event.current * 100 // event.total
        details.append(f"{event.current}/{event.total} ({percentage}%)")
    if state.reused:
        details.append("cached")
    if event.message:
        details.append(event.message)
    elif event.kind == "stage.started":
        details.append("starting")
    elif event.kind == "stage.completed":
        details.append("completed")
    elif not details:
        details.append(event.kind)
    return f"{' · '.join(parts)}: {' · '.join(details)}"


def format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, whole_seconds = divmod(int(seconds), 60)
    hours, whole_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02}:{whole_minutes:02}:{whole_seconds:02}"
    return f"{whole_minutes:02}:{whole_seconds:02}"


class _ElapsedText:
    def __init__(
        self,
        clock: Callable[[], float],
        started_at: Callable[[], float | None],
        finished_at: Callable[[], float | None],
    ) -> None:
        self._clock = clock
        self._started_at = started_at
        self._finished_at = finished_at

    def __rich__(self) -> Text:
        started_at = self._started_at()
        if started_at is None:
            return Text("")
        finished_at = self._finished_at()
        end = finished_at if finished_at is not None else self._clock()
        return Text(format_elapsed(end - started_at))


class _StageEtaColumn(TimeRemainingColumn):
    def __init__(self, eligible: Callable[[], bool]) -> None:
        super().__init__(compact=True)
        self._eligible = eligible

    def render(self, task: Task) -> Text:
        if not self._eligible() or task.finished or task.time_remaining is None:
            return Text("")
        return Text.assemble("ETA ", super().render(task))


class ProgressRenderer(Protocol):
    def __call__(self, event: ApplicationEvent) -> None: ...

    @property
    def elapsed_seconds(self) -> float | None: ...

    def close(self, *, success: bool = False) -> None: ...


class NullReadioProgress:
    """Silent event sink for JSON output and machine capture."""

    def __call__(self, event: ApplicationEvent) -> None:
        del event

    @property
    def elapsed_seconds(self) -> float | None:
        return None

    def close(self, *, success: bool = False) -> None:
        return


class LineReadioProgress:
    """Milestone renderer for redirected output."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        chapters: tuple[BookChapterView, ...] = (),
        selected_chapters: str | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ProgressState()
        self._chapter_context = _ChapterProgressContext(chapters, selected_chapters)
        self._last_line: str | None = None
        self._last_bucket: int | None = None
        self._last_chapter_key: tuple[object, ...] | None = None
        self._clock = clock
        self._workflow_started_at: float | None = None
        self._workflow_finished_at: float | None = None

    @property
    def elapsed_seconds(self) -> float | None:
        if self._workflow_started_at is None:
            return None
        finished_at = self._workflow_finished_at
        end = finished_at if finished_at is not None else self._clock()
        return end - self._workflow_started_at

    def __call__(self, event: ApplicationEvent) -> None:
        if self._workflow_started_at is None:
            self._workflow_started_at = self._clock()
        previous_stage = self.state.stage
        previous_chapter = self._last_chapter_key
        self.state.reduce(event)

        stage_changed = event.stage != previous_stage
        if stage_changed:
            self._last_bucket = None
        chapter = _chapter_key(self.state, self._chapter_context)
        chapter_changed = chapter != previous_chapter
        bucket = _progress_bucket(event.current, event.total)
        lifecycle = event.kind in {"stage.started", "stage.completed", "stage.reused"}
        bucket_advanced = bucket is not None and (
            self._last_bucket is None or bucket > self._last_bucket
        )
        if lifecycle or stage_changed or chapter_changed or bucket_advanced:
            self._emit(
                _line_label(event, self.state, self._chapter_context),
                force=lifecycle or stage_changed or chapter_changed,
            )
            if bucket is not None:
                self._last_bucket = bucket
        self._last_chapter_key = chapter

    def _emit(self, line: str, *, force: bool = False) -> None:
        if line and (force or line != self._last_line):
            self.console.print(line)
            self._last_line = line

    def close(self, *, success: bool = False) -> None:
        if self._workflow_started_at is not None and self._workflow_finished_at is None:
            self._workflow_finished_at = self._clock()


class LiveReadioProgress:
    """Single-owner Rich Live display for a Readio workflow."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        chapters: tuple[BookChapterView, ...] = (),
        selected_chapters: str | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ProgressState()
        self._chapter_context = _ChapterProgressContext(chapters, selected_chapters)
        self._clock = clock
        self._workflow_started_at: float | None = None
        self._workflow_finished_at: float | None = None
        self._stage_started_at: float | None = None
        self._stage: str | None = None
        self._live: Live | None = None
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description:24}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            _StageEtaColumn(self._has_stage_eta),
            console=self.console,
            auto_refresh=False,
            expand=True,
        )
        self._task = self._progress.add_task("Working", total=None)

    @property
    def elapsed_seconds(self) -> float | None:
        if self._workflow_started_at is None:
            return None
        finished_at = self._workflow_finished_at
        end = finished_at if finished_at is not None else self._clock()
        return end - self._workflow_started_at

    def __call__(self, event: ApplicationEvent) -> None:
        now = self._clock()
        if self._workflow_started_at is None:
            self._workflow_started_at = now

        previous_stage = self._stage
        stage_started = event.stage != previous_stage or event.kind == "stage.started"
        if stage_started:
            self._stage = event.stage
            self._stage_started_at = now

        self.state.reduce(event)
        if self._live is None:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.start()

        if stage_started:
            self._progress.remove_task(self._task)
            self._task = self._progress.add_task(
                _stage_label(event.stage),
                total=event.total,
                completed=event.current if event.current is not None else 0,
            )
        elif event.total is not None or event.current is not None:
            self._progress.update(
                self._task,
                total=event.total,
                completed=event.current if event.current is not None else 0,
            )

        if event.kind == "stage.reused":
            self._progress.update(self._task, total=1, completed=1)
        elif event.kind == "stage.completed":
            task = self._progress.tasks[0]
            if task.total is None:
                self._progress.update(self._task, total=1, completed=1)
            else:
                self._progress.update(self._task, completed=task.total)
        self._update_live()

    def _has_stage_eta(self) -> bool:
        current = self.state.current
        total = self.state.total
        return (
            self._workflow_finished_at is None
            and not self.state.completed
            and not self.state.reused
            and current is not None
            and total is not None
            and total > 0
            and 0 < current <= total
        )

    def _render(self) -> RenderableType:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="bold")
        grid.add_column(ratio=1)
        grid.add_row("Audiobook workflow")
        grid.add_row(self._progress)
        grid.add_row("Stage", _stage_label(self.state.stage))
        if self.state.package:
            grid.add_row("Package", self.state.package)
        if self.state.selector:
            grid.add_row("Selection", self.state.selector)
        chapter = self._chapter_context.resolve(self.state)
        if chapter is not None:
            grid.add_row("Chapter", _chapter_label(chapter))
        if self.state.reused:
            grid.add_row("Status", f"cached · {self.state.message or 'stage reused'}")
        elif self.state.message:
            grid.add_row("Status", self.state.message)
        elif self.state.kind:
            grid.add_row("Status", self.state.kind)
        if self._workflow_started_at is not None:
            grid.add_row(
                "Elapsed",
                _ElapsedText(
                    self._clock,
                    lambda: self._workflow_started_at,
                    lambda: self._workflow_finished_at,
                ),
            )
        if self._stage_started_at is not None:
            grid.add_row(
                "Stage time",
                _ElapsedText(
                    self._clock,
                    lambda: self._stage_started_at,
                    lambda: self._workflow_finished_at,
                ),
            )
        return grid

    def _update_live(self) -> None:
        if self._live is not None:
            self._live.update(self._render(), refresh=False)

    def close(self, *, success: bool = False) -> None:
        if self._live is None:
            return
        if self._workflow_finished_at is None:
            self._workflow_finished_at = self._clock()
        if success:
            task = self._progress.tasks[0]
            if task.total is None:
                self._progress.update(self._task, total=1, completed=1)
            else:
                self._progress.update(self._task, completed=task.total)
            self.state.completed = True
        self._update_live()
        self._live.refresh()
        self._live.stop()
        self._live = None


class RichReadioProgress(LineReadioProgress):
    """Compatibility name for the milestone progress renderer."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        json_mode: bool = False,
        chapters: tuple[BookChapterView, ...] = (),
        selected_chapters: str | None = None,
    ) -> None:
        super().__init__(
            console=console,
            chapters=chapters,
            selected_chapters=selected_chapters,
        )
        self._silent = json_mode

    def __call__(self, event: ApplicationEvent) -> None:
        if not self._silent:
            super().__call__(event)

    def close(self, *, success: bool = False) -> None:
        if not self._silent:
            super().close(success=success)
