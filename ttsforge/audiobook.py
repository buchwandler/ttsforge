"""Audiobook-level workflow over Readio's public application API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .application.errors import LegacyWorkspaceError, ProjectMigrationRequiredError
from .application.events import ApplicationEvent
from .application.service import AudiobookApplicationService
from .chapter_selection import parse_chapter_selection
from .options import AudiobookOptions
from .readio_backend import (
    BuildTarget,
    ReadioBackend,
    create_readio,
    project_build_request,
)

__all__ = [
    "AudiobookConverter",
    "AudiobookOptions",
    "ConversionPreflight",
    "LegacyWorkspaceError",
    "ProjectMigrationRequiredError",
    "ProjectSetup",
]


@dataclass(frozen=True, slots=True)
class ProjectSetup:
    """Result of TTSForge's create-or-reuse audiobook project workflow."""

    project: Any
    created: bool
    chapters: tuple[Any, ...] = ()

    @property
    def selected_chapters(self) -> tuple[int, ...]:
        return tuple(chapter.number for chapter in self.chapters)


@dataclass(frozen=True, slots=True)
class ConversionPreflight:
    """Resolved, user-facing audiobook setup prepared before synthesis."""

    source: Path
    title: str | None
    author: str | None
    project: Any
    project_created: bool
    available_chapters: int
    chapters: tuple[Any, ...]
    output: Path | None
    format: str
    synthesis_request: Any | None
    synthesis: Any
    bitrate: str | None
    target_lufs: float | None
    offline: bool
    refresh: bool

    settings_source: str = "defaults"
    settings_saved: bool = False


class AudiobookConverter:
    """Small product service for EPUB inspection and Readio project workflows."""

    def __init__(
        self,
        app: Any | None = None,
        *,
        on_event: Callable[[ApplicationEvent], None] | None = None,
    ) -> None:
        if app is not None and on_event is not None:
            raise ValueError("Pass an app or an event handler, not both.")
        self._backend = ReadioBackend(
            app if app is not None else create_readio(on_event=on_event)
        )

    def application_service(self) -> AudiobookApplicationService:
        """Create the frontend-neutral service over this converter's adapter."""
        return AudiobookApplicationService(self._backend)

    def normalize_engine(self, engine: str) -> str:
        """Normalize an engine alias through Readio's public catalog API."""
        return self._backend.normalize_engine(engine)

    def inspect(self, source: Path) -> Any:
        """Inspect an EPUB through the Readio adapter."""
        return self._backend.inspect(source)

    def resolve_synthesis(
        self,
        project: Any | Path,
        request: Any,
        *,
        use_saved_settings: bool = True,
    ) -> Any:
        """Resolve request defaults through the Readio adapter."""
        return self._backend.resolve_synthesis_raw(
            project, request, use_saved_settings=use_saved_settings
        )

    def project_settings(self, project: Any | Path) -> Any:
        """Read desired build settings through the Readio adapter."""
        return self._backend.project_settings(project)

    def save_project_settings(self, project: Any | Path, settings: Any) -> Any:
        """Persist desired build settings through the Readio adapter."""
        return self._backend.configure_project(project, settings)

    def engines(self) -> tuple[Any, ...]:
        """List engines known to this converter's Readio application."""
        return self._backend.engines()

    def models(
        self,
        *,
        language: str | None,
        engine: str | None,
        discovery: Any,
    ) -> Any:
        """List models through the shared Readio catalog."""
        return self._backend.models_listing(
            language=language, engine=engine, discovery=discovery
        )

    def voices(
        self,
        *,
        language: str | None,
        engine: str | None,
        model: str | None,
        discovery: Any,
    ) -> Any:
        """List voices through the shared Readio catalog."""
        return self._backend.voices_listing(
            language=language, engine=engine, model=model, discovery=discovery
        )

    def lexicons(
        self,
        *,
        language: str | None,
        engine: str | None,
        model: str | None,
        discovery: Any,
    ) -> Any:
        """List lexicons through the shared Readio catalog."""
        return self._backend.lexicons_listing(
            language=language, engine=engine, model=model, discovery=discovery
        )

    @staticmethod
    def default_project_path(source: Path) -> Path:
        """Return the stable sibling project path for an EPUB."""
        return source.with_suffix(".ssmdbook")

    def find_project(self, options: AudiobookOptions) -> Any | None:
        """Find the selected project through the Readio adapter."""
        if options.fresh:
            return None
        if options.project is not None:
            return self._backend.find_project_ref(options.project)
        project = self._backend.find_project_ref(
            self.default_project_path(options.source)
        )
        if project is not None:
            return project
        legacy_path = options.source.with_suffix(".readio")
        if legacy_path.exists():
            return self._backend.find_project_ref(legacy_path)
        return None

    def create_or_open_project(
        self,
        options: AudiobookOptions,
        *,
        inspection: Any | None = None,
        existing_project: Any | None = None,
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
                project = self._backend.open_project_ref(existing)
                description = self._backend.describe_project(project)
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

        created = self._backend.create_project_result(
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
        inspection: Any,
        options: AudiobookOptions,
        *,
        synthesis: Any | None = None,
    ) -> ConversionPreflight:
        """Resolve and collect the exact settings planned for the build."""
        request = synthesis
        resolved = self.resolve_synthesis(setup.project, request)
        title_value = inspection.metadata.get("title")
        title = title_value if isinstance(title_value, str) else None
        authors_value = inspection.metadata.get("authors")
        author: str | None
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

    def status(self, project: Any | Path) -> Any:
        """Report authoritative project state through the Readio adapter."""
        return self._backend.status_raw(project)

    def plan(self, project: Any | Path) -> Any:
        """Generate or refresh speech plans through the Readio adapter."""
        return self._backend.plan_raw(project)

    def build_and_export(self, project: Any | Path, options: AudiobookOptions) -> Any:
        """Build and export through the Readio adapter."""
        return self._backend.build_and_export(project, options)

    def preview(
        self,
        project: Any | Path,
        options: AudiobookOptions,
        *,
        selection: str = "first:3",
    ) -> Any:
        """Render a preview through the Readio adapter."""
        return self._backend.preview_raw(project, options, selection)

    @staticmethod
    def build_request(
        options: AudiobookOptions,
        *,
        target: BuildTarget,
        synthesis: Any | None = None,
    ) -> Any:
        """Map an audiobook choice and optional request through the adapter."""
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
