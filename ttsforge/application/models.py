"""Compact application-owned audiobook requests and presentation views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path
    intent: Path
    profile: Path
    bundle: Path
    # Publicly, variant storage is an additional narration; the key remains internal.
    variant_key: str | None = None

    @classmethod
    def for_root(cls, root: Path) -> ProjectPaths:
        return cls(
            root=root,
            intent=root / "render.readio.toml",
            profile=root / "narrator.renderprofile.toml",
            bundle=root / "book.ssmd-bundle",
        )

    @property
    def setup_root(self) -> Path:
        return self.intent.parent

    @classmethod
    def for_variant(cls, root: Path, variant_key: str) -> ProjectPaths:
        setup_root = root / "variants" / variant_key
        return cls(
            root=root,
            intent=setup_root / "render.readio.toml",
            profile=setup_root / "narrator.renderprofile.toml",
            bundle=root / "book.ssmd-bundle",
            variant_key=variant_key,
        )

    @classmethod
    def for_source(cls, source: Path, project: Path | None = None) -> ProjectPaths:
        root = project or source.with_suffix(".ttsforge")
        return cls.for_root(root)


@dataclass(frozen=True, slots=True)
class AudiobookMetadata:
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    narrator: str | None = None
    series: str | None = None
    series_number: str | None = None
    language: str | None = None
    publisher: str | None = None
    year: str | None = None
    cover: Path | None = None

    def overlay(self, other: AudiobookMetadata) -> AudiobookMetadata:
        return AudiobookMetadata(
            **{
                name: getattr(other, name)
                if getattr(other, name) is not None
                else getattr(self, name)
                for name in self.__dataclass_fields__
            }
        )

    def to_readio_mapping(self) -> dict[str, str]:
        values = {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "narrator": self.narrator,
            "series": self.series,
            "series_index": self.series_number,
            "language": self.language,
            "publisher": self.publisher,
            "year": self.year,
        }
        return {key: value for key, value in values.items() if value is not None}

    def is_empty(self) -> bool:
        return not any(
            getattr(self, name) is not None for name in self.__dataclass_fields__
        )


@dataclass(frozen=True, slots=True)
class AudiobookRequest:
    source: Path
    project: Path | None = None
    chapters: str | None = None
    output: Path | None = None
    language: str | None = None
    engine: str | None = None
    target: str | None = None
    voice: str | None = None
    engine_options: Mapping[str, object] = field(default_factory=dict)
    speed: float | None = None
    spacy: str | None = None
    speech_profile: Path | None = None
    pause_timing: str | None = None
    bitrate: str | int | None = None
    target_lufs: float | None = None
    metadata: AudiobookMetadata = field(default_factory=AudiobookMetadata)
    title: str | None = None
    author: str | None = None
    cover: Path | None = None
    offline: bool = False
    refresh: bool = False
    rebuild_from: str | None = None
    replace_output: bool = False
    fresh: bool = False
    new_variant: bool = False

    def __post_init__(self) -> None:
        metadata = self.metadata.overlay(
            AudiobookMetadata(title=self.title, author=self.author, cover=self.cover)
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "title", metadata.title)
        object.__setattr__(self, "author", metadata.author)
        object.__setattr__(self, "cover", metadata.cover)


AudiobookOptions = AudiobookRequest


@dataclass(frozen=True, slots=True)
class InputOverrides:
    fields: frozenset[str] = frozenset()

    def includes(self, field_name: str) -> bool:
        return field_name in self.fields


@dataclass(frozen=True, slots=True)
class SetupOrigins:
    explicit: frozenset[str] = frozenset()
    project: frozenset[str] = frozenset()
    derived: frozenset[str] = frozenset()

    def needs_input(self, field_name: str) -> bool:
        return field_name not in self.explicit | self.project | self.derived

    def should_confirm_derived(self, field_name: str) -> bool:
        return field_name not in self.explicit and field_name not in self.project


@dataclass(frozen=True, slots=True)
class BookChapterView:
    number: int
    title: str
    source_id: str | None = None
    char_count: int | None = None


@dataclass(frozen=True, slots=True)
class BookInspectionView:
    source: Path
    kind: str
    title: str | None
    author: str | None
    language: str | None
    chapters: tuple[BookChapterView, ...]
    cover: Path | None = None
    metadata: AudiobookMetadata = field(default_factory=AudiobookMetadata)


QcSeverity = Literal["pass", "warning", "error", "unknown"]


@dataclass(frozen=True, slots=True)
class QcFinding:
    id: str
    severity: QcSeverity
    section: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AudiobookQcReport:
    project: Path
    narration_id: str | None
    passed: bool
    findings: tuple[QcFinding, ...]


@dataclass(frozen=True, slots=True)
class AudiobookMetadataView:
    project: Path
    source: Path
    source_metadata: AudiobookMetadata
    overrides: AudiobookMetadata
    effective: AudiobookMetadata


@dataclass(frozen=True, slots=True)
class MetadataValidationReport:
    project: Path
    valid: bool
    findings: tuple[QcFinding, ...]


@dataclass(frozen=True, slots=True)
class ChapterStatusView:
    number: int
    title: str
    source_id: str | None
    char_count: int | None
    selected: bool
    workflow_state: str | None = None
    estimated_duration_seconds: float | None = None
    final_duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ChapterSelectionView:
    project: Path
    selection: str
    selected_chapters: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AudiobookCapabilitiesView:
    source_inspection: bool
    synthesis_preview: bool
    m4b_export: bool
    persistent_workspace: bool
    available_engines: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreviewAudio:
    wav: bytes
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectVariantView:
    variant_key: str
    output: Path | None = None
    engine: str | None = None
    target: str | None = None
    voice: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class NarrationId:
    value: str

    def __post_init__(self) -> None:
        if (
            not self.value
            or self.value in {".", ".."}
            or "/" in self.value
            or "\\" in self.value
        ):
            raise ValueError(
                "Narration IDs must be a non-empty project-local identifier."
            )


@dataclass(frozen=True, slots=True)
class NarrationView:
    id: str
    display_name: str
    primary: bool
    output: Path | None = None
    engine: str | None = None
    target: str | None = None
    voice: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SpacyModelView:
    language: str
    tier: str
    model: str
    installed: bool
    spacy_version: str | None
    model_version: str | None


ModelState = Literal[
    "missing",
    "ready",
    "outdated",
    "partial",
    "corrupt",
    "unavailable",
    "unknown",
]
ModelUpdateState = Literal["current", "update_available", "unavailable", "unknown"]


@dataclass(frozen=True, slots=True)
class EngineModelView:
    engine: str
    target: str
    quality: str | None
    language: str | None
    label: str | None
    installed: bool
    available: bool
    state: ModelState
    local_version: str | None
    available_version: str | None
    update_state: ModelUpdateState
    bytes_installed: int | None
    bytes_download: int | None
    storage_id: str | None
    installable: bool
    updatable: bool
    removable: bool
    verifiable: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class VoiceSetupView:
    language: str
    engine: str
    target: str
    voice: str | None
    options: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogItemView:
    id: str
    label: str
    engine: str | None = None
    language: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowBlockerView:
    code: str
    message: str
    owner: str | None
    recoverable: bool
    suggested_action: str | None


@dataclass(frozen=True, slots=True)
class WorkflowStepView:
    stage: str
    package: str
    action: str
    selector: str | None
    reason: str
    state: str
    reason_code: str = "specialist_state_unknown"
    force: bool = False
    blockers: tuple[WorkflowBlockerView, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowPlanView:
    source: Path
    workspace: Path | None
    workspace_mode: str
    output: Path | None
    steps: tuple[WorkflowStepView, ...]
    warnings: tuple[str, ...] = ()
    executable: bool = True
    variant: str | None = None


@dataclass(frozen=True, slots=True)
class SetupPreparation:
    paths: ProjectPaths
    inspection: BookInspectionView
    request: AudiobookRequest
    origins: SetupOrigins
    reused: bool


@dataclass(frozen=True, slots=True)
class ResolvedSetup:
    preparation: SetupPreparation
    request: AudiobookRequest
    render_request: object


@dataclass(frozen=True, slots=True)
class PreflightView:
    setup: ResolvedSetup
    workflow: WorkflowPlanView


@dataclass(frozen=True, slots=True)
class StageExecutionView:
    stage: str
    package: str
    action: str
    state_before: str
    state_after: str | None
    elapsed_seconds: float
    reason_code: str


@dataclass(frozen=True, slots=True)
class ExecutionSummaryView:
    stages: tuple[StageExecutionView, ...]
    specialist_versions: Mapping[str, str | None]
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ConversionResultView:
    output: Path
    workspace: Path | None
    workspace_mode: str
    executed_stages: tuple[str, ...]
    reused_stages: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    variant: str | None = None
    execution: ExecutionSummaryView | None = None
