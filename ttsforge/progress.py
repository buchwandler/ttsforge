"""Human-readable progress presentation for public Readio events."""

from __future__ import annotations

from readio.api import ReadioEvent
from rich.console import Console

_STAGE_LABELS = {
    "plan": "Planning speech",
    "synthesis": "Synthesizing",
    "composition": "Composing audiobook",
    "export": "Encoding audiobook",
    "output": "Writing output",
    "readiness": "Preparing speech",
    "render": "Rendering preview",
    "upload": "Uploading output",
}
_OPERATION_LABELS = {
    "audiobooks.inspect": "Inspecting book",
    "audiobooks.create_project": "Preparing chapters",
    "audiobooks.create_project_result": "Preparing chapters",
    "projects.preview": "Preparing preview",
    "projects.build": "Building audiobook",
    "projects.status": "Checking project status",
}


class RichReadioProgress:
    """Present Readio events as concise human progress on stderr.

    JSON mode suppresses all human-facing progress so stdout remains a clean
    machine-readable channel. Repeated identical updates and duplicate terminal
    events are suppressed.
    """

    def __init__(
        self,
        console: Console | None = None,
        *,
        json_mode: bool = False,
    ) -> None:
        self.console = console or Console(stderr=True, highlight=False, markup=False)
        self.json_mode = json_mode
        self._last_line: str | None = None
        self._active_operation: str | None = None
        self._operation_completed = False

    def __call__(self, event: ReadioEvent) -> None:
        if self.json_mode:
            return

        if event.kind == "operation.started":
            self._active_operation = event.operation
            self._operation_completed = False
            label = _OPERATION_LABELS.get(
                event.operation, event.message or event.operation
            )
            self._emit(label)
            return

        if event.kind == "operation.completed":
            if self._active_operation == event.operation and self._operation_completed:
                return
            self._active_operation = event.operation
            self._operation_completed = True
            self._emit("Done")
            return

        if event.kind == "stage.started":
            label = _STAGE_LABELS.get(event.stage or "", event.message or "Working")
            self._emit(label)
            return

        if event.kind != "progress":
            return

        label = _STAGE_LABELS.get(event.stage or "", event.message or "Working")
        if event.message:
            line = event.message
        elif event.completed is not None and event.total is not None:
            line = f"{label}: {event.completed}/{event.total}"
        elif event.audio_seconds is not None:
            if event.total_audio_seconds is not None:
                line = (
                    f"{label}: {event.audio_seconds:.1f}/"
                    f"{event.total_audio_seconds:.1f} seconds"
                )
            else:
                line = f"{label}: {event.audio_seconds:.1f} seconds"
        else:
            line = label
        self._emit(line)

    def _emit(self, line: str) -> None:
        if not line or line == self._last_line:
            return
        self.console.print(line)
        self._last_line = line
