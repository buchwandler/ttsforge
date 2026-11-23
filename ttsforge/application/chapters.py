"""Application views for book chapters and project-scoped selection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..chapter_selection import (
    normalize_chapter_selection,
    parse_chapter_selection,
)
from .errors import (
    InputValidationError,
    OperationConflictError,
    ProjectScopeConflictError,
)
from .models import (
    BookInspectionView,
    ChapterSelectionView,
    ChapterStatusView,
    ProjectPaths,
    WorkflowStepView,
)

if TYPE_CHECKING:
    from .service import AudiobookApplicationService


class ChapterApplicationService:
    """Present source chapters and preserve the project's shared selection scope."""

    def __init__(self, audiobook: AudiobookApplicationService) -> None:
        self._audiobook = audiobook

    def list(self, source_or_project: Path) -> tuple[ChapterStatusView, ...]:
        if source_or_project.is_dir():
            return self.status(ProjectPaths.for_root(source_or_project))
        inspection = self._audiobook.inspect_book(source_or_project)
        return self._chapter_views(inspection, "all")

    def status(self, paths: ProjectPaths) -> tuple[ChapterStatusView, ...]:
        saved = self._audiobook.load_saved_setup(paths)
        if saved is None:
            raise OperationConflictError(
                f"No saved TTSForge setup exists in {paths.root}."
            )
        inspection = self._audiobook.inspect_book(saved.source)
        workflow = self._audiobook.status(paths)
        selected = set(
            parse_chapter_selection(saved.chapters or "all", len(inspection.chapters))
        )
        return tuple(
            ChapterStatusView(
                number=chapter.number,
                title=chapter.title,
                source_id=chapter.source_id,
                char_count=chapter.char_count,
                selected=chapter.number - 1 in selected,
                workflow_state=_chapter_workflow_state(
                    chapter.source_id, chapter.number, workflow.steps
                ),
            )
            for chapter in inspection.chapters
        )

    def select(self, paths: ProjectPaths, selection: str) -> ChapterSelectionView:
        saved = self._audiobook.load_saved_setup(paths)
        if saved is None:
            raise OperationConflictError(
                f"No saved TTSForge setup exists in {paths.root}."
            )
        inspection = self._audiobook.inspect_book(saved.source)
        try:
            normalized = normalize_chapter_selection(
                selection, len(inspection.chapters)
            )
            current = normalize_chapter_selection(
                saved.chapters or "all", len(inspection.chapters)
            )
        except ValueError as exc:
            raise InputValidationError(str(exc)) from exc
        if normalized != current:
            raise ProjectScopeConflictError(
                f"Project {paths.root} is configured for chapters '{current}'. "
                f"A different chapter selection ('{normalized}') requires a separate "
                "project. Use a fresh project path."
            )
        return ChapterSelectionView(
            project=paths.root,
            selection=normalized,
            selected_chapters=tuple(
                index + 1
                for index in parse_chapter_selection(
                    normalized, len(inspection.chapters)
                )
            ),
        )

    @staticmethod
    def _chapter_views(
        inspection: BookInspectionView, selection: str
    ) -> tuple[ChapterStatusView, ...]:
        selected = set(parse_chapter_selection(selection, len(inspection.chapters)))
        return tuple(
            ChapterStatusView(
                number=chapter.number,
                title=chapter.title,
                source_id=chapter.source_id,
                char_count=chapter.char_count,
                selected=chapter.number - 1 in selected,
            )
            for chapter in inspection.chapters
        )


def _chapter_workflow_state(
    source_id: str | None, number: int, steps: tuple[WorkflowStepView, ...]
) -> str | None:
    selectors = {f"chapter-{number}"}
    if source_id is not None:
        selectors.add(source_id)
    for step in steps:
        if step.selector in selectors:
            return step.state
    return None
