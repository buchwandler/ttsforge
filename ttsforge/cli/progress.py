"""Rich progress renderers for normalized Readio workflow events."""

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


class ProgressRenderer(Protocol):
    def __call__(self, event: ApplicationEvent) -> None: ...

    def close(self) -> None: ...


class NullReadioProgress:
    """Silent event sink for JSON output and machine capture."""

    def __call__(self, event: ApplicationEvent) -> None:
        del event

    def close(self) -> None:
        return


class LineReadioProgress:
    """Milestone renderer for redirected output."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ProgressState()
        self._last_line: str | None = None

    def __call__(self, event: ApplicationEvent) -> None:
        self.state.reduce(event)
        self._emit(_event_label(event))

    def _emit(self, line: str) -> None:
        if line and line != self._last_line:
            self.console.print(line)
            self._last_line = line

    def close(self) -> None:
        return


class LiveReadioProgress:
    """Single-owner Rich Live display for a Readio workflow."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.state = ProgressState()
        self._live: Live | None = None
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description:24}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            auto_refresh=False,
            expand=True,
        )
        self._task = self._progress.add_task("Working", total=None)

    def __call__(self, event: ApplicationEvent) -> None:
        previous_stage = self.state.stage
        self.state.reduce(event)
        if self._live is None:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.start()
        if event.stage != previous_stage:
            self._progress.reset(
                self._task,
                total=event.total,
                completed=event.current or 0,
            )
        elif event.total is not None or event.current is not None:
            self._progress.update(
                self._task,
                total=event.total,
                completed=event.current,
            )
        if event.kind == "stage.completed" and event.total is None:
            self._progress.update(self._task, total=1, completed=1)
        self._update_live()

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
            grid.add_row("Selector", self.state.selector)
        if self.state.message:
            grid.add_row("Status", self.state.message)
        elif self.state.kind:
            grid.add_row("Status", self.state.kind)
        if self.state.elapsed_seconds is not None:
            grid.add_row("Elapsed", f"{self.state.elapsed_seconds:.1f}s")
        return grid

    def _update_live(self) -> None:
        if self._live is not None:
            self._live.update(self._render(), refresh=False)

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None


class RichReadioProgress(LineReadioProgress):
    """Compatibility name for the milestone progress renderer."""

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

    def close(self) -> None:
        if not self._silent:
            super().close()
