"""Audiobook-level workflow over Readio's public application API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from readio.api import (
    AUDIOBOOK_EXPORT_FORMAT,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_AUDIOBOOK_FORMATS,
    AudiobookExportResult,
    AudiobookInspection,
    AudiobookProjectChapter,
    PreviewRequest,
    PreviewResult,
    ProjectBuildRequest,
    ProjectBuildResult,
    ProjectFormatError,
    ProjectPlanResult,
    ProjectRef,
    ProjectStatus,
    Readio,
    ReadioEvent,
    SynthesisRequest,
    SynthesisResolution,
)

from .chapter_selection import parse_chapter_selection
from .options import AudiobookOptions
from .readio_backend import (
    BuildTarget,
    audiobook_export_options,
    composition_options,
    create_readio,
    project_build_request,
    synthesis_request,
)


@dataclass(frozen=True, slots=True)
class ProjectSetup:
    """Result of TTSForge's create-or-reuse audiobook project workflow."""

    project: ProjectRef
    created: bool
    chapters: tuple[AudiobookProjectChapter, ...] = ()

    @property
    def selected_chapters(self) -> tuple[int, ...]:
        return tuple(chapter.number for chapter in self.chapters)


@dataclass(frozen=True, slots=True)
class ConversionPreflight:
    """Resolved, user-facing audiobook setup prepared before synthesis."""

    source: Path
    title: str | None
    author: str | None
    project: ProjectRef
    project_created: bool
    available_chapters: int
    chapters: tuple[AudiobookProjectChapter, ...]
    output: Path | None
    format: str
    synthesis_request: SynthesisRequest
    synthesis: SynthesisResolution
    bitrate: str | None
    target_lufs: float | None
    offline: bool
    refresh: bool


class LegacyWorkspaceError(ValueError):
    """Raised when an existing TTSForge workspace cannot be a Readio project."""


class AudiobookConverter:
    """Small product service for EPUB inspection and Readio project workflows."""

    def __init__(
        self,
        app: Readio | None = None,
        *,
        on_event: Callable[[ReadioEvent], None] | None = None,
    ) -> None:
        if app is not None and on_event is not None:
            raise ValueError("Pass an app or an event handler, not both.")
        self._app = app if app is not None else create_readio(on_event=on_event)

    def inspect(self, source: Path) -> AudiobookInspection:
        """Inspect an EPUB using Readio's audiobook service."""
        return self._app.audiobooks.inspect(source)

    @staticmethod
    def default_project_path(source: Path) -> Path:
        """Return the stable sibling project path for an EPUB."""
        return source.with_suffix(".readio")

    def find_project(self, options: AudiobookOptions) -> ProjectRef | None:
        """Find the selected project, refusing an opaque legacy directory."""
        if options.fresh:
            return None
        project_path = options.project or self.default_project_path(options.source)
        try:
            existing = self._app.projects.find(project_path)
        except ProjectFormatError as exc:
            raise LegacyWorkspaceError(
                "This directory is not a Readio project and cannot resume a "
                "legacy TTSForge workspace. Start a new Readio project with "
                "--fresh."
            ) from exc
        if existing is None and project_path.exists():
            raise LegacyWorkspaceError(
                f"The existing directory is not a Readio project: {project_path}. "
                "Legacy TTSForge workspaces cannot be resumed; use --fresh "
                "to create a separate Readio project."
            )
        return existing

    def create_or_open_project(
        self,
        options: AudiobookOptions,
        *,
        inspection: AudiobookInspection | None = None,
        existing_project: ProjectRef | None = None,
        project_checked: bool = False,
    ) -> ProjectSetup:
        """Create an EPUB project once, then reuse its persisted chapter scope."""
        project_path = options.project or self.default_project_path(options.source)
        if options.fresh:
            project_path = self._fresh_project_path(project_path)

        if not options.fresh:
            existing = (
                existing_project if project_checked else self.find_project(options)
            )
            if existing is not None:
                project = self._app.projects.open(existing.root)
                description = self._app.audiobooks.describe_project(project)
                return ProjectSetup(
                    project=project,
                    created=False,
                    chapters=description.chapters,
                )
        if inspection is None:
            inspection = self.inspect(options.source)
        if options.chapters.strip().lower() == "all":
            chapter_selection = "all"
        else:
            indices = parse_chapter_selection(
                options.chapters, len(inspection.chapters)
            )
            if not indices:
                raise ValueError("Chapter selection must include at least one chapter.")
            chapter_selection = ",".join(str(index + 1) for index in indices)

        created = self._app.audiobooks.create_project_result(
            options.source,
            chapters=chapter_selection,
            output=project_path,
        )
        return ProjectSetup(
            project=created.project,
            created=True,
            chapters=created.chapters,
        )

    def preflight(
        self,
        setup: ProjectSetup,
        inspection: AudiobookInspection,
        options: AudiobookOptions,
        *,
        synthesis: SynthesisRequest | None = None,
    ) -> ConversionPreflight:
        """Resolve and collect the exact settings planned for the build."""
        request = synthesis if synthesis is not None else synthesis_request(options)
        resolved = self._app.projects.resolve_synthesis(setup.project, request)
        title_value = inspection.metadata.get("title")
        title = title_value if isinstance(title_value, str) else None
        authors_value = inspection.metadata.get("authors")
        if isinstance(authors_value, str):
            author = authors_value
        elif isinstance(authors_value, (tuple, list)):
            authors = [name for name in authors_value if isinstance(name, str)]
            author = ", ".join(authors) or None
        else:
            author = None
        return ConversionPreflight(
            source=options.source,
            title=title,
            author=author,
            project=setup.project,
            project_created=setup.created,
            available_chapters=len(inspection.chapters),
            chapters=setup.chapters,
            output=options.output,
            format=options.format.lower(),
            synthesis_request=request,
            synthesis=resolved,
            bitrate=options.bitrate,
            target_lufs=options.target_lufs,
            offline=options.offline,
            refresh=options.refresh,
        )

    def status(self, project: ProjectRef | Path) -> ProjectStatus:
        """Report authoritative project state from Readio."""
        return self._app.projects.status(project)

    def plan(self, project: ProjectRef | Path) -> ProjectPlanResult:
        """Generate/refresh speech plans through Readio's project service."""
        return self._app.projects.plan(project)

    def build_and_export(
        self,
        project: ProjectRef | Path,
        options: AudiobookOptions,
        *,
        synthesis: SynthesisRequest | None = None,
    ) -> AudiobookExportResult | ProjectBuildResult:
        """Build the project and export with the format-specific public API."""
        output_format = options.format.lower()
        if output_format in SUPPORTED_AUDIOBOOK_FORMATS:
            if output_format != AUDIOBOOK_EXPORT_FORMAT:
                raise ValueError(f"Unsupported audiobook format: {output_format}")
            self._app.projects.build(
                project,
                project_build_request(
                    options, target="composition", synthesis=synthesis
                ),
            )
            return self._app.audiobooks.export(
                project, audiobook_export_options(options)
            )
        if output_format not in SUPPORTED_AUDIO_FORMATS:
            supported = (*SUPPORTED_AUDIO_FORMATS, *SUPPORTED_AUDIOBOOK_FORMATS)
            raise ValueError(
                f"Unsupported audio format {output_format!r}; "
                f"choose from {', '.join(supported)}."
            )
        return self._app.projects.build(
            project,
            project_build_request(options, target="export", synthesis=synthesis),
        )

    def preview(
        self,
        project: ProjectRef | Path,
        options: AudiobookOptions,
        *,
        selection: str = "first:3",
    ) -> PreviewResult:
        """Render a preview using the same public synthesis/composition policy."""
        request = PreviewRequest(
            selection=selection,
            synthesis=synthesis_request(options),
            composition=composition_options(options),
        )
        return self._app.projects.preview(project, request)

    @staticmethod
    def build_request(
        options: AudiobookOptions,
        *,
        target: BuildTarget,
        synthesis: SynthesisRequest | None = None,
    ) -> ProjectBuildRequest:
        """Map an audiobook choice and optional shared request to Readio."""
        return project_build_request(options, target=target, synthesis=synthesis)

    @staticmethod
    def _fresh_project_path(project_path: Path) -> Path:
        base = project_path.with_name(f"{project_path.stem}.fresh{project_path.suffix}")
        candidate = base
        index = 2
        while candidate.exists():
            candidate = base.with_name(f"{base.stem}-{index}{base.suffix}")
            index += 1
        return candidate
