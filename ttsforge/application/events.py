"""Frontend-neutral progress events normalized from Readio's workflow contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    """Presentation-focused copy of a normalized Readio workflow event."""

    stage: str
    kind: str
    message: str | None = None
    package: str | None = None
    selector: str | None = None
    current: int | None = None
    total: int | None = None
    elapsed_seconds: float | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a plain mapping suitable for JSON serialization."""
        return asdict(self)


@dataclass(slots=True)
class ProgressState:
    """Latest normalized workflow event for a terminal progress renderer."""

    stage: str | None = None
    kind: str | None = None
    message: str | None = None
    package: str | None = None
    selector: str | None = None
    current: int | None = None
    total: int | None = None
    elapsed_seconds: float | None = None
    details: Mapping[str, object] = field(default_factory=dict)
    completed: bool = False

    def reduce(self, event: ApplicationEvent) -> None:
        self.stage = event.stage
        self.kind = event.kind
        self.message = event.message
        self.package = event.package
        self.selector = event.selector
        self.current = event.current
        self.total = event.total
        self.elapsed_seconds = event.elapsed_seconds
        self.details = dict(event.details)
        self.completed = event.kind == "stage.completed"
