"""Synchronous audiobook workflow orchestration over a fakeable backend."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from ..chapter_selection import format_chapter_numbers, parse_chapter_selection
from .errors import ProjectScopeConflictError
from .models import (
    AudiobookRequest,
    BookInspectionView,
    CatalogItemView,
    InputOverrides,
    MergedSetup,
    OperationResultView,
    PreflightView,
    PreviewView,
    ProjectPlanView,
    ProjectPreparation,
    ProjectStatusView,
    ProjectView,
    ResolvedSetup,
    SetupOrigins,
    SynthesisView,
)
from .setup import merge_saved_setup as merge_setup


class ApplicationBackend(Protocol):
    """Integration operations required by the audiobook application service."""

    def inspect_book(self, source: Path) -> BookInspectionView: ...

    def find_project(self, path: Path) -> ProjectView | None: ...

    def open_project(self, project: ProjectView) -> ProjectView: ...

    def create_project(
        self,
        inspection: BookInspectionView,
        path: Path,
        chapter_numbers: tuple[int, ...],
    ) -> ProjectView: ...

    def resolve_synthesis(
        self,
        project: ProjectView,
        request: AudiobookRequest,
        *,
        use_saved_settings: bool,
    ) -> SynthesisView: ...

    def save_synthesis_setup(
        self, project: ProjectView, request: AudiobookRequest, synthesis: SynthesisView
    ) -> AudiobookRequest: ...

    def load_setup(
        self, project: ProjectView, request: AudiobookRequest
    ) -> tuple[AudiobookRequest, SetupOrigins, bool]: ...

    def build(
        self, project: ProjectView, request: AudiobookRequest
    ) -> OperationResultView: ...

    def preview(
        self, project: ProjectView, request: AudiobookRequest, selection: str
    ) -> PreviewView: ...

    def status(self, project: ProjectView | Path) -> ProjectStatusView: ...

    def plan(self, project: ProjectView | Path) -> ProjectPlanView: ...

    def catalog_choices(
        self, kind: str, query: Mapping[str, object]
    ) -> tuple[CatalogItemView, ...]: ...


class AudiobookApplicationService:
    """Coordinate project setup, persistence, and audiobook operations."""

    def __init__(self, backend: ApplicationBackend) -> None:
        self._backend = backend

    def inspect_book(self, source: Path) -> BookInspectionView:
        return self._backend.inspect_book(source)

    def find_project(self, request: AudiobookRequest) -> ProjectView | None:
        if request.fresh:
            return None
        if request.project is not None:
            return self._backend.find_project(request.project)
        project = self._backend.find_project(request.source.with_suffix(".ssmdbook"))
        if project is not None:
            return project
        legacy_path = request.source.with_suffix(".readio")
        if legacy_path.exists():
            return self._backend.find_project(legacy_path)
        return None

    def merge_saved_settings(
        self,
        project: ProjectView,
        request: AudiobookRequest,
        overrides: InputOverrides,
        *,
        created: bool,
        interactive: bool,
    ) -> MergedSetup:
        saved_request, origins, has_saved_synthesis = self._backend.load_setup(
            project, request
        )
        merged = merge_setup(request, saved_request, overrides, interactive=interactive)
        if created:
            settings_source = "new"
        elif has_saved_synthesis:
            settings_source = "project+cli" if overrides.fields else "project"
        elif origins.project and overrides.fields:
            settings_source = "project+cli"
        elif origins.project:
            settings_source = "project"
        else:
            settings_source = "defaults"
        return MergedSetup(merged, origins, has_saved_synthesis, settings_source)

    def prepare_project(
        self,
        request: AudiobookRequest,
        *,
        chapter_selection: str | None = None,
        inspection: BookInspectionView | None = None,
        existing_project: ProjectView | None = None,
        project_checked: bool = False,
    ) -> ProjectPreparation:
        inspection = inspection or self.inspect_book(request.source)
        project_path = request.project or request.source.with_suffix(".ssmdbook")
        if request.fresh:
            project_path = self._fresh_project_path(project_path)
        else:
            existing = (
                existing_project if project_checked else self.find_project(request)
            )
            if existing is not None:
                project = self._backend.open_project(existing)
                self._validate_existing_scope(chapter_selection, inspection, project)
                return ProjectPreparation(
                    inspection=inspection,
                    project=project,
                    created=False,
                    chapters=project.chapters,
                )

        selection = "all" if chapter_selection is None else chapter_selection
        indices = parse_chapter_selection(selection, len(inspection.chapters))
        if not indices:
            raise ValueError("Chapter selection must include at least one chapter.")
        chapter_numbers = tuple(index + 1 for index in indices)
        project = self._backend.create_project(
            inspection, project_path, chapter_numbers
        )
        return ProjectPreparation(
            inspection=inspection,
            project=project,
            created=True,
            chapters=project.chapters,
        )

    def resolve_and_save_setup(
        self,
        preparation: ProjectPreparation,
        request: AudiobookRequest,
    ) -> ResolvedSetup:
        synthesis = self._backend.resolve_synthesis(
            preparation.project, request, use_saved_settings=False
        )
        saved_request = self._backend.save_synthesis_setup(
            preparation.project, request, synthesis
        )
        return ResolvedSetup(preparation, saved_request, synthesis)

    def preflight(self, resolved: ResolvedSetup) -> PreflightView:
        metadata = resolved.preparation.inspection.metadata
        title_value = metadata.get("title")
        title = title_value if isinstance(title_value, str) else None
        authors_value = metadata.get("authors")
        if isinstance(authors_value, str):
            author = authors_value
        elif isinstance(authors_value, (tuple, list)):
            authors = [name for name in authors_value if isinstance(name, str)]
            author = ", ".join(authors) or None
        else:
            author = None
        return PreflightView(
            preparation=resolved.preparation,
            request=resolved.request,
            synthesis=resolved.synthesis,
            title=title,
            author=author,
            available_chapters=len(resolved.preparation.inspection.chapters),
            settings_saved=True,
        )

    def build(self, resolved: ResolvedSetup) -> OperationResultView:
        return self._backend.build(resolved.preparation.project, resolved.request)

    def preview(
        self,
        preparation: ProjectPreparation,
        request: AudiobookRequest,
        *,
        selection: str = "first:3",
    ) -> PreviewView:
        return self._backend.preview(preparation.project, request, selection)

    def status(self, project: ProjectView | Path) -> ProjectStatusView:
        return self._backend.status(project)

    def plan(self, project: ProjectView | Path) -> ProjectPlanView:
        return self._backend.plan(project)

    def catalog_choices(
        self, kind: str, query: Mapping[str, object] | None = None
    ) -> tuple[CatalogItemView, ...]:
        return self._backend.catalog_choices(kind, query or {})

    @staticmethod
    def _validate_existing_scope(
        requested: str | None,
        inspection: BookInspectionView,
        project: ProjectView,
    ) -> None:
        if requested is None:
            return
        indices = parse_chapter_selection(requested, len(inspection.chapters))
        if not indices:
            raise ValueError("Chapter selection must include at least one chapter.")
        selected = tuple(index + 1 for index in indices)
        if selected == tuple(chapter.number for chapter in project.chapters):
            return
        existing = format_chapter_numbers(
            chapter.number for chapter in project.chapters
        )
        raise ProjectScopeConflictError(
            f"Existing project uses chapters {existing}. "
            "Use --fresh or --project PATH to create a separate project."
        )

    @staticmethod
    def _fresh_project_path(project_path: Path) -> Path:
        base = project_path.with_name(f"{project_path.stem}.fresh{project_path.suffix}")
        candidate = base
        index = 2
        while candidate.exists():
            candidate = base.with_name(f"{base.stem}-{index}{base.suffix}")
            index += 1
        return candidate
