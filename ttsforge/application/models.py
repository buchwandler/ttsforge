"""Compact application-owned audiobook requests and presentation views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path
    intent: Path
    profile: Path
    bundle: Path

    @classmethod
    def for_root(cls, root: Path) -> ProjectPaths:
        return cls(
            root=root,
            intent=root / "render.readio.toml",
            profile=root / "narrator.renderprofile.toml",
            bundle=root / "book.ssmd-bundle",
        )

    @classmethod
    def for_source(cls, source: Path, project: Path | None = None) -> ProjectPaths:
        root = project or source.with_suffix(".ttsforge")
        return cls.for_root(root)


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
    title: str | None = None
    author: str | None = None
    cover: Path | None = None
    offline: bool = False
    refresh: bool = False
    rebuild_from: str | None = None
    replace_output: bool = False
    fresh: bool = False


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


@dataclass(frozen=True, slots=True)
class SpacyModelView:
    language: str
    tier: str
    model: str
    installed: bool
    spacy_version: str | None
    model_version: str | None


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
class WorkflowStepView:
    stage: str
    package: str
    action: str
    selector: str | None
    reason: str
    state: str


@dataclass(frozen=True, slots=True)
class WorkflowPlanView:
    source: Path
    workspace: Path | None
    workspace_mode: str
    output: Path | None
    steps: tuple[WorkflowStepView, ...]
    warnings: tuple[str, ...] = ()


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
class ConversionResultView:
    output: Path
    workspace: Path | None
    workspace_mode: str
    executed_stages: tuple[str, ...]
    reused_stages: tuple[str, ...]
    warnings: tuple[str, ...] = ()
