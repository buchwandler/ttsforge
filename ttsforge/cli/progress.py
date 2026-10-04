"""Terminal progress renderers for frontend-neutral application events."""

from __future__ import annotations

from typing import Protocol

from rich.console import Console, RenderableType
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from ..application.events import ApplicationEvent, ProgressState
from ..application.models import ChapterView, SynthesisView

ReadioProgressState = ProgressState

_STAGE_LABELS = {
    "plan": "Planning speech",
    "synthesis": "Synthesizing speech",
    "composition": "Composing audiobook",
    "export": "Writing audiobook",
    "output": "Writing output",
    "readiness": "Preparing speech",
    "render": "Rendering preview",
    "upload": "Uploading output",
}
_OPERATION_LABELS = {
    "audiobooks.inspect": "Inspecting book",
    "audiobooks.create_project": "Preparing chapters",
    "audiobooks.create_project_result": "Preparing chapters",
    "audiobooks.export": "Writing audiobook",
    "projects.preview": "Preparing preview",
    "projects.build": "Building audiobook",
    "projects.status": "Checking project status",
}


def _status_label(state: ProgressState) -> str:
    if state.phase_message:
        return state.phase_message
    if state.stage:
        return _STAGE_LABELS.get(state.stage, "Working")
    if state.operation:
        return _OPERATION_LABELS.get(state.operation, state.operation)
    return "Working"


class ProgressRenderer(Protocol):
    def __call__(self, event: ApplicationEvent) -> None: ...

    def set_chapters(self, chapters: tuple[ChapterView, ...]) -> None: ...

    def set_synthesis(self, resolution: SynthesisView) -> None: ...

    def close(self) -> None: ...


class NullReadioProgress:
    """Silent event sink for JSON output and machine capture."""

    def __call__(self, event: ApplicationEvent) -> None:
        del event

    def set_chapters(self, chapters: tuple[ChapterView, ...]) -> None:
        del chapters

    def set_synthesis(self, resolution: SynthesisView) -> None:
        del resolution

    def close(self) -> None:
        return


class LineReadioProgress:
    """Milestone renderer for redirected output; suppresses segment chatter."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ReadioProgressState()
        self.chapter_by_scope: dict[str, ChapterView] = {}
        self._last_line: str | None = None

    def set_chapters(self, chapters: tuple[ChapterView, ...]) -> None:
        self.chapter_by_scope = {chapter.scope_id: chapter for chapter in chapters}
        self.state.set_chapters(tuple(chapter.scope_id for chapter in chapters))

    def set_synthesis(self, resolution: SynthesisView) -> None:
        del resolution

    def __call__(self, event: ApplicationEvent) -> None:
        was_finished = {
            scope_id for scope_id, scope in self.state.scopes.items() if scope.finished
        }
        self.state.reduce(event)
        if event.kind == "operation.started":
            self._emit(
                _OPERATION_LABELS.get(event.operation, event.message or event.operation)
            )
        elif event.kind == "operation.completed":
            if event.operation in {"projects.build", "audiobooks.export"}:
                self._emit("Build step complete")
        elif event.kind == "stage.started":
            self._emit(_STAGE_LABELS.get(event.stage or "", event.message or "Working"))
        elif event.kind == "progress":
            if event.progress_kind == "phase":
                self._emit_phase(event)
            self._emit_completed_chapters(was_finished)

    def _emit_phase(self, event: ApplicationEvent) -> None:
        if event.message == "Synthesis cache scanned":
            reused = self.state.cache_reused or 0
            missing = self.state.cache_missing or 0
            self._emit(f"Cache: {reused} reused · {missing} to synthesize")
        elif event.message:
            self._emit(event.message)

    def _emit_completed_chapters(self, was_finished: set[str]) -> None:
        for scope_id, scope in self.state.scopes.items():
            if (
                not scope.finished
                or scope_id in was_finished
                or scope_id not in self.chapter_by_scope
            ):
                continue
            chapter = self.chapter_by_scope[scope_id]
            count = len(self.chapter_by_scope)
            self._emit(f"Synthesis: chapter {chapter.number}/{count} complete")

    def _emit(self, line: str) -> None:
        if line and line != self._last_line:
            self.console.print(line)
            self._last_line = line

    def close(self) -> None:
        return


class LiveReadioProgress:
    """Single-owner Rich Live display for scope-aware terminal progress."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ReadioProgressState()
        self.chapter_by_scope: dict[str, ChapterView] = {}
        self.engine_label: str | None = None
        self._live: Live | None = None
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description:12}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            auto_refresh=False,
            expand=True,
        )
        self._overall_task = self._progress.add_task("Overall", total=0)
        self._chapter_task = self._progress.add_task("Chapter", total=None)

    def set_chapters(self, chapters: tuple[ChapterView, ...]) -> None:
        self.chapter_by_scope = {chapter.scope_id: chapter for chapter in chapters}
        self.state.set_chapters(tuple(chapter.scope_id for chapter in chapters))
        self._progress.update(
            self._overall_task,
            total=len(chapters),
            completed=self.state.completed_chapters,
        )
        self._update_live()

    def set_synthesis(self, resolution: SynthesisView) -> None:
        values = [resolution.engine]
        if resolution.model:
            values.append(resolution.model)
        if resolution.voice:
            values.append(resolution.voice)
        self.engine_label = " · ".join(values)
        self._update_live()

    def __call__(self, event: ApplicationEvent) -> None:
        self.state.reduce(event)
        if event.kind == "operation.started" and self._live is None:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.start()
        self._update_progress()
        self._update_live()
        if event.kind == "operation.completed":
            self.close()

    def _update_progress(self) -> None:
        self._progress.update(
            self._overall_task,
            total=len(self.chapter_by_scope),
            completed=self.state.completed_chapters,
        )
        scope_id = self.state.current_scope_id
        scope = self.state.scopes.get(scope_id) if scope_id else None
        chapter = self.chapter_by_scope.get(scope_id) if scope_id else None
        label = (
            f"Chapter {chapter.number}"
            if chapter is not None
            else (scope_id or "Chapter")
        )
        if chapter is not None and chapter.title:
            label += f" — {chapter.title}"
        self._progress.update(
            self._chapter_task,
            description=label,
            total=scope.total if scope is not None else None,
            completed=scope.completed if scope is not None else 0,
        )

    def _render(self) -> RenderableType:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="bold")
        grid.add_column(ratio=1)
        grid.add_row("Building audiobook")
        grid.add_row(self._progress)
        scope_id = self.state.current_scope_id
        if scope_id:
            chapter = self.chapter_by_scope.get(scope_id)
            current = (
                f"Chapter {chapter.number} — {chapter.title}"
                if chapter is not None
                else scope_id
            )
            grid.add_row("Current", current)
        if self.engine_label:
            grid.add_row("Engine", self.engine_label)
        if self.state.cache_reused is not None or self.state.cache_missing is not None:
            reused = self.state.cache_reused or 0
            missing = self.state.cache_missing or 0
            grid.add_row("Cache", f"{reused} reused · {missing} to synthesize")
        grid.add_row("Status", _status_label(self.state))
        return grid

    def _update_live(self) -> None:
        if self._live is not None:
            self._live.update(self._render(), refresh=False)

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None


class RichReadioProgress(LineReadioProgress):
    """Compatibility wrapper for the former Rich-named milestone callback."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        json_mode: bool = False,
    ) -> None:
        super().__init__(console=console)
        self._silent = json_mode

    def __call__(self, event: ApplicationEvent) -> None:
        if not self._silent:
            super().__call__(event)

    def set_chapters(self, chapters: tuple[ChapterView, ...]) -> None:
        if not self._silent:
            super().set_chapters(chapters)

    def set_synthesis(self, resolution: SynthesisView) -> None:
        if not self._silent:
            super().set_synthesis(resolution)

    def close(self) -> None:
        if not self._silent:
            super().close()
