"""Serializable application events and frontend-neutral progress reduction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    """Progress or lifecycle event independent of Readio and UI frameworks."""

    kind: str
    operation: str
    stage: str | None = None
    progress_kind: str | None = None
    message: str | None = None
    completed: int | None = None
    total: int | None = None
    sample_count: int | None = None
    sample_rate: int | None = None
    audio_seconds: float | None = None
    total_audio_seconds: float | None = None
    scope_id: str | None = None
    unit_id: str | None = None
    segment_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a plain mapping suitable for JSON serialization."""
        return asdict(self)


@dataclass(slots=True)
class ScopeProgress:
    scope_id: str
    completed: int = 0
    total: int | None = None
    current_unit_id: str | None = None
    current_segment_id: str | None = None
    finished: bool = False


@dataclass(slots=True)
class ProgressState:
    """Reduce application events into scope-aware audiobook progress state."""

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

    def set_chapters(self, scope_ids: Sequence[str]) -> None:
        self.chapter_scope_ids = tuple(scope_ids)
        for scope_id in self.chapter_scope_ids:
            self.scopes.setdefault(scope_id, ScopeProgress(scope_id))

    @property
    def completed_chapters(self) -> int:
        return sum(
            self.scopes.get(scope_id, ScopeProgress(scope_id)).finished
            for scope_id in self.chapter_scope_ids
        )

    def reduce(self, event: ApplicationEvent) -> None:
        if event.kind == "operation.started":
            self.operation = event.operation
            self.stage = None
            self.phase_message = event.message
            return
        if event.kind == "operation.completed":
            self.operation = event.operation
            self.phase_message = "Done"
            return
        if event.kind == "stage.started":
            self.stage = event.stage
            self.phase_message = event.message
            return
        if event.kind != "progress":
            return

        if event.stage is not None:
            self.stage = event.stage
        if event.message:
            self.phase_message = event.message

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
    def _update_scope_counter(scope: ScopeProgress, event: ApplicationEvent) -> None:
        if event.total is not None:
            scope.total = event.total
        if event.completed is not None:
            scope.completed = max(scope.completed, event.completed)
        elif event.progress_kind in {"unit.completed", "segment.completed"}:
            scope.completed += 1
        if scope.total is not None and scope.completed >= scope.total:
            scope.finished = True

    def _reduce_cache(self, event: ApplicationEvent) -> None:
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
            if (
                not isinstance(required, int)
                or not isinstance(reused_count, int)
                or not isinstance(missing_count, int)
            ):
                continue
            scope = self.scopes.setdefault(scope_id, ScopeProgress(scope_id))
            scope.total = missing_count if missing_count else required
            scope.completed = 0 if missing_count else required
            scope.finished = scope.completed >= scope.total
