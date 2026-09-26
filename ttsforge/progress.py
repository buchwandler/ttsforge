"""Scoped progress reduction and terminal renderers for public Readio events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from readio.api import AudiobookProjectChapter, ReadioEvent, SynthesisResolution
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


@dataclass(slots=True)
class ScopeProgress:
    scope_id: str
    completed: int = 0
    total: int | None = None
    current_unit_id: str | None = None
    current_segment_id: str | None = None
    finished: bool = False


@dataclass(slots=True)
class ReadioProgressState:
    """Reducer for Readio progress events, independent of Rich and terminals."""

    operation: str | None = None
    stage: str | None = None
    phase_message: str | None = None
    scopes: dict[str, ScopeProgress] = field(default_factory=dict)
    current_scope_id: str | None = None
    cache_reused: int | None = None
    cache_missing: int | None = None
    composition_completed: int | None = None
    composition_total: int | None = None
    chapter_scope_ids: tuple[str, ...] = ()

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None:
        self.chapter_scope_ids = tuple(chapter.scope_id for chapter in chapters)
        for scope_id in self.chapter_scope_ids:
            self.scopes.setdefault(scope_id, ScopeProgress(scope_id))

    @property
    def completed_chapters(self) -> int:
        return sum(
            self.scopes.get(scope_id, ScopeProgress(scope_id)).finished
            for scope_id in self.chapter_scope_ids
        )

    def reduce(self, event: ReadioEvent) -> None:
        if event.kind == "operation.started":
            self.operation = event.operation
            self.stage = None
            self.phase_message = _OPERATION_LABELS.get(
                event.operation, event.message or event.operation
            )
            return
        if event.kind == "operation.completed":
            self.operation = event.operation
            self.phase_message = "Done"
            return
        if event.kind == "stage.started":
            self.stage = event.stage
            self.phase_message = _STAGE_LABELS.get(
                event.stage or "", event.message or "Working"
            )
            return
        if event.kind != "progress":
            return

        if event.stage is not None:
            self.stage = event.stage
        if event.message:
            self.phase_message = event.message
        elif self.stage and self.phase_message is None:
            self.phase_message = _STAGE_LABELS.get(self.stage, "Working")

        if self.stage == "composition":
            if event.completed is not None:
                self.composition_completed = event.completed
            if event.total is not None:
                self.composition_total = event.total

        self._reduce_cache(event)
        if event.scope_id is None:
            return

        scope = self.scopes.setdefault(event.scope_id, ScopeProgress(event.scope_id))
        self.current_scope_id = event.scope_id
        if event.progress_kind in {"unit.started", "unit.completed"}:
            if event.unit_id is not None:
                scope.current_unit_id = event.unit_id
            self._update_scope_counter(scope, event)
        elif event.progress_kind in {"segment.started", "segment.completed"}:
            if event.segment_id is not None:
                scope.current_segment_id = event.segment_id
            self._update_scope_counter(scope, event)

    @staticmethod
    def _update_scope_counter(scope: ScopeProgress, event: ReadioEvent) -> None:
        if event.total is not None:
            scope.total = event.total
        if event.completed is not None:
            scope.completed = max(scope.completed, event.completed)
        elif event.progress_kind in {"unit.completed", "segment.completed"}:
            scope.completed += 1
        if scope.total is not None and scope.completed >= scope.total:
            scope.finished = True

    def _reduce_cache(self, event: ReadioEvent) -> None:
        if event.progress_kind != "phase" or not event.details:
            return
        reused = event.details.get("reused")
        missing = event.details.get("missing")
        if isinstance(reused, int):
            self.cache_reused = reused
        if isinstance(missing, int):
            self.cache_missing = missing

        per_scope = event.details.get("per_scope")
        if not isinstance(per_scope, Mapping):
            return
        for scope_id, details in per_scope.items():
            if not isinstance(scope_id, str) or not isinstance(details, Mapping):
                continue
            required = details.get("required")
            reused_count = details.get("reused")
            missing_count = details.get("rendered")
            if not all(
                isinstance(value, int)
                for value in (required, reused_count, missing_count)
            ):
                continue
            scope = self.scopes.setdefault(scope_id, ScopeProgress(scope_id))
            scope.total = missing_count if missing_count else required
            scope.completed = 0 if missing_count else required
            scope.finished = scope.completed >= scope.total


class ProgressRenderer(Protocol):
    def __call__(self, event: ReadioEvent) -> None: ...

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None: ...

    def set_synthesis(self, resolution: SynthesisResolution) -> None: ...

    def close(self) -> None: ...


class NullReadioProgress:
    """Silent event sink for JSON output and machine capture."""

    def __call__(self, event: ReadioEvent) -> None:
        del event

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None:
        del chapters

    def set_synthesis(self, resolution: SynthesisResolution) -> None:
        del resolution

    def close(self) -> None:
        return


class LineReadioProgress:
    """Milestone renderer for redirected output; suppresses segment chatter."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ReadioProgressState()
        self.chapter_by_scope: dict[str, AudiobookProjectChapter] = {}
        self._last_line: str | None = None

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None:
        self.chapter_by_scope = {chapter.scope_id: chapter for chapter in chapters}
        self.state.set_chapters(chapters)

    def set_synthesis(self, resolution: SynthesisResolution) -> None:
        del resolution

    def __call__(self, event: ReadioEvent) -> None:
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

    def _emit_phase(self, event: ReadioEvent) -> None:
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
        self.chapter_by_scope: dict[str, AudiobookProjectChapter] = {}
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

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None:
        self.chapter_by_scope = {chapter.scope_id: chapter for chapter in chapters}
        self.state.set_chapters(chapters)
        self._progress.update(
            self._overall_task,
            total=len(chapters),
            completed=self.state.completed_chapters,
        )
        self._update_live()

    def set_synthesis(self, resolution: SynthesisResolution) -> None:
        values = [resolution.engine]
        if resolution.model:
            values.append(resolution.model)
        if resolution.voice:
            values.append(resolution.voice)
        self.engine_label = " · ".join(values)
        self._update_live()

    def __call__(self, event: ReadioEvent) -> None:
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
        grid.add_row("Status", self.state.phase_message or "Working")
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

    def __call__(self, event: ReadioEvent) -> None:
        if not self._silent:
            super().__call__(event)

    def set_chapters(self, chapters: tuple[AudiobookProjectChapter, ...]) -> None:
        if not self._silent:
            super().set_chapters(chapters)

    def set_synthesis(self, resolution: SynthesisResolution) -> None:
        if not self._silent:
            super().set_synthesis(resolution)

    def close(self) -> None:
        if not self._silent:
            super().close()
