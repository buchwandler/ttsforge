"""Paragraph render-unit planning and resumable progress primitives.

This module deliberately depends only on standard-library data structures.  The
PyKokoro adapter converts its public descriptor types into these records at the
boundary, which keeps state and output code testable without initializing ONNX.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeVar, cast

ConversionUnit = Literal["chapter", "paragraph"]
RenderUnitKind = Literal["title", "paragraph"]

PARAGRAPH_OUTPUT_SCHEMA = 1
PARAGRAPH_MANIFEST_SCHEMA = 1
UNIT_FILENAME_SCHEMA = 1
PARAGRAPH_PAUSE_OWNERSHIP = "following-boundary-owned-by-previous-v1"
PYKOKORO_RENDERER_VERSION = "0.8.1"


def renderer_contract_payload() -> dict[str, object]:
    """Return the renderer contract that gates resumable paragraph audio."""
    return {
        "schema": 2,
        "ssmd": "0.8",
        "pykokoro": PYKOKORO_RENDERER_VERSION,
        "paragraph_unit": 1,
        "pause_ownership": PARAGRAPH_PAUSE_OWNERSHIP,
        "unit_filename_schema": UNIT_FILENAME_SCHEMA,
        "paragraph_manifest_schema": PARAGRAPH_MANIFEST_SCHEMA,
    }


def validate_conversion_unit(value: str) -> ConversionUnit:
    if value not in {"chapter", "paragraph"}:
        raise ValueError("conversion_unit must be 'chapter' or 'paragraph'")
    return cast(ConversionUnit, value)


def stable_hash(value: object, *, length: int = 64) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True, slots=True)
class PreparedUnitDescriptor:
    """Dependency-light copy of a public PyKokoro unit descriptor."""

    index: int
    paragraph_index: int
    text: str
    text_hash: str
    char_start: int = 0
    char_end: int = 0
    marker_names: tuple[str, ...] = ()

    @property
    def char_count(self) -> int:
        return max(self.char_end - self.char_start, len(self.text))


class PreparedUnitsProvider(Protocol):
    @property
    def units(self) -> Sequence[object]: ...

    def render(self, *, skip_indices: Iterable[int] = ()) -> Iterable[object]: ...

    def __enter__(self) -> PreparedUnitsProvider: ...

    def __exit__(self, *args: object) -> None: ...


def descriptor_from_public(value: object) -> PreparedUnitDescriptor:
    """Copy only documented descriptor fields from PyKokoro."""
    text = str(getattr(value, "text", ""))
    char_start = int(getattr(value, "char_start", 0))
    char_end = int(getattr(value, "char_end", char_start + len(text)))
    text_hash = str(getattr(value, "text_hash", "")) or stable_hash(text, length=64)
    marker_names = tuple(str(item) for item in getattr(value, "marker_names", ()))
    return PreparedUnitDescriptor(
        index=int(value.index),
        paragraph_index=int(
            getattr(value, "paragraph_idx", getattr(value, "paragraph_index", 0))
        ),
        text=text,
        text_hash=text_hash,
        char_start=char_start,
        char_end=char_end,
        marker_names=marker_names,
    )


@dataclass
class RenderUnitState:
    """Persisted identity and output state for one playback unit."""

    sequence_index: int
    unit_index: int
    chapter_position: int
    source_chapter_index: int
    paragraph_index: int
    kind: RenderUnitKind
    content_hash: str
    render_fingerprint: str
    char_count: int
    source_paragraph_index: int | None = None
    chapter_unit_index: int | None = None
    completed: bool = False
    audio_file: str | None = None
    marker_file: str | None = None
    sample_rate: int = 24000
    duration: float = 0.0
    content_duration: float = 0.0
    trailing_chapter_silence: float = 0.0
    render_wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        # ``paragraph_index`` was the original persisted/output ordinal. Keep
        # accepting it for old callers and state files while exposing the two
        # distinct meanings explicitly in the current schema.
        if self.source_paragraph_index is None:
            self.source_paragraph_index = self.paragraph_index
        if self.chapter_unit_index is None:
            self.chapter_unit_index = self.paragraph_index
        self.paragraph_index = self.chapter_unit_index

    def identity(self) -> tuple[object, ...]:
        return (
            self.sequence_index,
            self.unit_index,
            self.chapter_position,
            self.source_chapter_index,
            self.source_paragraph_index,
            self.chapter_unit_index,
            self.kind,
            self.content_hash,
            self.render_fingerprint,
            self.char_count,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "unit_index": self.unit_index,
            "chapter_position": self.chapter_position,
            "source_chapter_index": self.source_chapter_index,
            "paragraph_index": self.paragraph_index,
            "source_paragraph_index": self.source_paragraph_index,
            "chapter_unit_index": self.chapter_unit_index,
            "kind": self.kind,
            "content_hash": self.content_hash,
            "render_fingerprint": self.render_fingerprint,
            "char_count": self.char_count,
            "completed": self.completed,
            "audio_file": self.audio_file,
            "marker_file": self.marker_file,
            "sample_rate": self.sample_rate,
            "duration": self.duration,
            "content_duration": self.content_duration,
            "trailing_chapter_silence": self.trailing_chapter_silence,
            "render_wall_seconds": self.render_wall_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RenderUnitState:
        allowed = {
            field_name: data[field_name]
            for field_name in (
                "sequence_index",
                "unit_index",
                "chapter_position",
                "source_chapter_index",
                "paragraph_index",
                "source_paragraph_index",
                "chapter_unit_index",
                "kind",
                "content_hash",
                "render_fingerprint",
                "char_count",
                "completed",
                "audio_file",
                "marker_file",
                "sample_rate",
                "duration",
                "content_duration",
                "trailing_chapter_silence",
                "render_wall_seconds",
            )
            if field_name in data
        }
        return cls(
            sequence_index=int(allowed["sequence_index"]),
            unit_index=int(allowed["unit_index"]),
            chapter_position=int(allowed["chapter_position"]),
            source_chapter_index=int(allowed["source_chapter_index"]),
            paragraph_index=int(allowed["paragraph_index"]),
            source_paragraph_index=(
                int(allowed["source_paragraph_index"])
                if allowed.get("source_paragraph_index") is not None
                else None
            ),
            chapter_unit_index=(
                int(allowed["chapter_unit_index"])
                if allowed.get("chapter_unit_index") is not None
                else None
            ),
            kind=cast(RenderUnitKind, str(allowed["kind"])),
            content_hash=str(allowed["content_hash"]),
            render_fingerprint=str(allowed["render_fingerprint"]),
            char_count=int(allowed["char_count"]),
            completed=bool(allowed.get("completed", False)),
            audio_file=(
                str(allowed["audio_file"])
                if allowed.get("audio_file") is not None
                else None
            ),
            marker_file=(
                str(allowed["marker_file"])
                if allowed.get("marker_file") is not None
                else None
            ),
            sample_rate=int(allowed.get("sample_rate", 24000)),
            duration=float(allowed.get("duration", 0.0)),
            content_duration=float(allowed.get("content_duration", 0.0)),
            trailing_chapter_silence=float(
                allowed.get("trailing_chapter_silence", 0.0)
            ),
            render_wall_seconds=float(allowed.get("render_wall_seconds", 0.0)),
        )


def unit_render_fingerprint(
    descriptor: PreparedUnitDescriptor,
    *,
    chapter_fingerprint: str,
    source_paragraph_index: int,
    chapter_unit_index: int,
    kind: RenderUnitKind,
) -> str:
    return stable_hash(
        {
            "chapter": chapter_fingerprint,
            "unit_index": descriptor.index,
            "source_paragraph_index": source_paragraph_index,
            "chapter_unit_index": chapter_unit_index,
            "kind": kind,
            "text_hash": descriptor.text_hash,
            "char_start": descriptor.char_start,
            "char_end": descriptor.char_end,
        }
    )


def map_descriptors(
    descriptors: Sequence[object],
    *,
    chapter_position: int,
    source_chapter_index: int,
    chapter_fingerprint: str,
    sequence_start: int,
    announced_title: bool,
    sample_rate: int = 24000,
) -> list[RenderUnitState]:
    """Map ordered public descriptors to persisted TTSForge units."""
    mapped: list[RenderUnitState] = []
    for offset, raw in enumerate(descriptors):
        descriptor = descriptor_from_public(raw)
        is_title = announced_title and offset == 0
        chapter_unit_index = (
            0 if is_title else (offset if announced_title else offset + 1)
        )
        source_paragraph_index = descriptor.paragraph_index
        kind: RenderUnitKind = "title" if is_title else "paragraph"
        mapped.append(
            RenderUnitState(
                sequence_index=sequence_start + offset,
                unit_index=descriptor.index,
                chapter_position=chapter_position,
                source_chapter_index=source_chapter_index,
                paragraph_index=chapter_unit_index,
                source_paragraph_index=source_paragraph_index,
                chapter_unit_index=chapter_unit_index,
                kind=kind,
                content_hash=descriptor.text_hash,
                render_fingerprint=unit_render_fingerprint(
                    descriptor,
                    chapter_fingerprint=chapter_fingerprint,
                    source_paragraph_index=source_paragraph_index,
                    chapter_unit_index=chapter_unit_index,
                    kind=kind,
                ),
                char_count=descriptor.char_count,
                sample_rate=sample_rate,
            )
        )
    return mapped


def reconcile_units(
    saved: Sequence[RenderUnitState],
    planned: Sequence[RenderUnitState],
) -> tuple[list[RenderUnitState], list[RenderUnitState]]:
    """Reuse matching prefix state and invalidate the first changed suffix."""
    first_mismatch = len(saved)
    for index, (old, new) in enumerate(zip(saved, planned, strict=False)):
        if old.identity() != new.identity():
            first_mismatch = index
            break
    if len(saved) != len(planned):
        first_mismatch = min(first_mismatch, min(len(saved), len(planned)))

    reconciled: list[RenderUnitState] = []
    stale: list[RenderUnitState] = []
    for index, planned_unit in enumerate(planned):
        if index < first_mismatch:
            previous = saved[index]
            planned_unit.completed = previous.completed
            planned_unit.audio_file = previous.audio_file
            planned_unit.marker_file = previous.marker_file
            planned_unit.sample_rate = previous.sample_rate
            planned_unit.duration = previous.duration
            planned_unit.content_duration = previous.content_duration
            planned_unit.trailing_chapter_silence = previous.trailing_chapter_silence
            planned_unit.render_wall_seconds = previous.render_wall_seconds
        elif index < len(saved):
            stale.append(saved[index])
        reconciled.append(planned_unit)
    stale.extend(saved[len(planned) :])
    return reconciled, stale


def invalidate_units_from(units: list[RenderUnitState], index: int) -> None:
    for unit in units[index:]:
        unit.completed = False
        unit.audio_file = None
        unit.marker_file = None
        unit.duration = 0.0
        unit.content_duration = 0.0
        unit.trailing_chapter_silence = 0.0


def next_incomplete_unit(units: Sequence[RenderUnitState]) -> RenderUnitState | None:
    return next((unit for unit in units if not unit.completed), None)


def completed_unit_count(units: Sequence[RenderUnitState]) -> int:
    return sum(1 for unit in units if unit.completed)


def chapter_completed(units: Sequence[RenderUnitState]) -> bool:
    return bool(units) and all(unit.completed for unit in units)


@dataclass
class UnitRateEstimator:
    """Robust bounded estimator for unit overhead plus character work."""

    observations: list[tuple[float, int]] = field(default_factory=list)
    max_observations: int = 32

    def add(self, wall_seconds: float, char_count: int) -> None:
        if wall_seconds >= 0 and char_count >= 0:
            self.observations.append((wall_seconds, char_count))
            del self.observations[: -self.max_observations]

    def estimate(self, remaining_units: int, remaining_chars: int) -> float:
        if remaining_units <= 0:
            return 0.0
        if not self.observations:
            return 0.0
        per_unit = statistics.median(value for value, _ in self.observations)
        rates = [wall / chars for wall, chars in self.observations if chars > 0]
        per_char = statistics.median(rates) if rates else 0.0
        return max(0.0, per_unit * remaining_units + per_char * remaining_chars)


T = TypeVar("T")


def validate_completed_units(
    units: Sequence[RenderUnitState],
    validator: Callable[[RenderUnitState], bool],
) -> list[RenderUnitState]:
    """Mark invalid completed units incomplete and return units needing rerender."""
    invalid: list[RenderUnitState] = []
    for unit in units:
        if unit.completed and not validator(unit):
            unit.completed = False
            unit.audio_file = None
            unit.marker_file = None
            unit.duration = 0.0
            unit.content_duration = 0.0
            invalid.append(unit)
    if invalid:
        first = min(unit.sequence_index for unit in invalid)
        for unit in units:
            if unit.sequence_index >= first:
                unit.completed = False
    return invalid
