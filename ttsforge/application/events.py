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


_CHAPTER_ORIENTED_STAGES = frozenset(
    {"convert", "compile", "render_plan", "render", "compose"}
)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


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
    chapter_id: str | None = None
    chapter_number: int | None = None
    chapter_title: str | None = None
    reused: bool = False
    completed: bool = False

    def reduce(self, event: ApplicationEvent) -> None:
        previous_stage = self.stage
        self.stage = event.stage
        self.kind = event.kind
        self.message = event.message
        self.package = event.package
        self.selector = event.selector
        self.current = event.current
        self.total = event.total
        self.elapsed_seconds = event.elapsed_seconds
        details = dict(event.details)
        self.details = details
        self.reused = event.kind == "stage.reused"
        self.completed = event.kind in {"stage.completed", "stage.reused"}

        chapter_id = _optional_str(details.get("chapter_id"))
        chapter_number = _optional_int(details.get("chapter_number"))
        chapter_title = _optional_str(details.get("chapter_title"))
        if any(
            value is not None for value in (chapter_id, chapter_number, chapter_title)
        ):
            self.chapter_id = chapter_id
            self.chapter_number = chapter_number
            self.chapter_title = chapter_title
        elif (
            event.stage != previous_stage
            and event.stage not in _CHAPTER_ORIENTED_STAGES
        ):
            self.chapter_id = None
            self.chapter_number = None
            self.chapter_title = None
