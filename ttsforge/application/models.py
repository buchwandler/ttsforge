"""Frontend-neutral requests and result views for audiobook operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudiobookRequest:
    """User-facing choices for one EPUB-to-audiobook operation."""

    source: Path
    project: Path | None = None
    chapters: str = "all"
    output: Path | None = None
    format: str = "m4b"
    language: str | None = None
    voice: str | None = None
    engine: str | None = None
    model: str | None = None
    model_source: str | None = None
    quality: str | None = None
    speed: float | None = None
    bitrate: str | None = None
    lexicons: tuple[str, ...] | None = None
    clear_lexicons: bool = False
    auto_lexicons: bool = False
    g2p_fallback: str | None = None
    lexicon_data_policy: str | None = None
    spacy: str | None = None
    short_sentence: str | None = None
    allow_experimental: bool = False
    voice_level: str | None = None
    pause_mode: str | None = None
    unit: str | None = None
    target_lufs: float | None = None
    offline: bool = False
    refresh: bool = False
    force: bool = False
    fresh: bool = False
    title: str | None = None
    author: str | None = None
    cover: Path | None = None


# Public compatibility name retained for existing TTSForge imports.
AudiobookOptions = AudiobookRequest


@dataclass(frozen=True, slots=True)
class InputOverrides:
    """Fields explicitly supplied by a frontend for one operation."""

    fields: frozenset[str] = frozenset()

    def includes(self, field: str) -> bool:
        return field in self.fields


@dataclass(frozen=True, slots=True)
class DiscoveryRequest:
    """Frontend-neutral catalog discovery controls."""

    offline: bool = False
    refresh: bool = False
    preference: str = "auto"


@dataclass(frozen=True, slots=True)
class SetupOrigins:
    """Record which setup fields are explicit and which came from a project."""

    explicit: frozenset[str] = frozenset()
    project: frozenset[str] = frozenset()

    def needs_input(self, field: str, *, reconfigure: bool = False) -> bool:
        if field in self.explicit:
            return False
        return not (field in self.project and not reconfigure)

    @property
    def cli(self) -> frozenset[str]:
        """Compatibility alias for the former CLI provenance field."""
        return self.explicit

    def prompt_required(self, field: str, *, reconfigure: bool = False) -> bool:
        """Compatibility alias for ``needs_input``."""
        return self.needs_input(field, reconfigure=reconfigure)


@dataclass(frozen=True, slots=True)
class CatalogItemView:
    """Serializable catalog choice without a Readio DTO dependency."""

    id: str
    label: str
    engine: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ChapterView:
    """Frontend-neutral chapter metadata for project and preflight views."""

    number: int
    title: str
    source_id: str | None = None
    scope_id: str | None = None
    parent_id: str | None = None
    level: int = 0
    char_count: int | None = None


@dataclass(frozen=True, slots=True)
class ProjectView:
    """Frontend-neutral identity for a managed audiobook project."""

    path: Path
    project_id: str
    name: str
    kind: str
    source_format: str
    chapters: tuple[ChapterView, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversionResultView:
    """Frontend-neutral summary returned after an audiobook operation."""

    project: ProjectView
    output: Path | None
    chapters: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BookInspectionView:
    """Book metadata and chapters translated from an integration adapter."""

    source: Path
    metadata: Mapping[str, object]
    chapters: tuple[ChapterView, ...]


@dataclass(frozen=True, slots=True)
class ProjectPreparation:
    """Project and persisted chapter scope prepared for one request."""

    inspection: BookInspectionView
    project: ProjectView
    created: bool
    chapters: tuple[ChapterView, ...]

    @property
    def selected_chapters(self) -> tuple[int, ...]:
        return tuple(chapter.number for chapter in self.chapters)


@dataclass(frozen=True, slots=True)
class MergedSetup:
    """Saved setup merged with this invocation's explicit overrides."""

    request: AudiobookRequest
    origins: SetupOrigins
    has_saved_synthesis: bool
    settings_source: str


@dataclass(frozen=True, slots=True)
class SynthesisView:
    """Resolved synthesis settings independent of Readio response classes."""

    engine: str
    language: str
    voice: str | None
    model: str | None
    speed: float
    unit: str
    pause_mode: str
    model_source: str | None = None
    quality: str | None = None
    spacy: str | None = None
    short_sentence: str | None = None
    lexicons: tuple[str, ...] | None = None
    clear_lexicons: bool | None = None
    auto_lexicons: bool | None = None
    g2p_fallback: str | None = None
    lexicon_data_policy: str | None = None
    voice_level: str | None = None
    allow_experimental: bool = False


@dataclass(frozen=True, slots=True)
class PreflightView:
    """Resolved conversion summary ready for presentation or confirmation."""

    preparation: ProjectPreparation
    request: AudiobookRequest
    synthesis: SynthesisView
    title: str | None
    author: str | None
    available_chapters: int
    settings_saved: bool
    settings_source: str = "defaults"


@dataclass(frozen=True, slots=True)
class ResolvedSetup:
    """Setup resolution persisted before preflight or build confirmation."""

    preparation: ProjectPreparation
    request: AudiobookRequest
    synthesis: SynthesisView


@dataclass(frozen=True, slots=True)
class OperationResultView:
    """Serializable summary of a completed or planned project operation."""

    operation: str
    project: ProjectView
    output: Path | None = None
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreviewView:
    """Summary of a rendered preview operation."""

    project: ProjectView
    items: int
    frames: int
    sample_rate: int


@dataclass(frozen=True, slots=True)
class ProjectStatusView:
    """Frontend-neutral project status and next-action summary."""

    project: ProjectView
    status: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectPlanView:
    """Frontend-neutral speech-plan summary."""

    project: ProjectView
    details: Mapping[str, object] = field(default_factory=dict)
