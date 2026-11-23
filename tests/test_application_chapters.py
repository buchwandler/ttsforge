from __future__ import annotations

from pathlib import Path

import pytest

from ttsforge.application.chapters import ChapterApplicationService
from ttsforge.application.errors import InputValidationError, ProjectScopeConflictError
from ttsforge.application.models import (
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ProjectPaths,
    WorkflowPlanView,
    WorkflowStepView,
)


class _Audiobook:
    def __init__(self, source: Path, project: Path, selection: str) -> None:
        self.request = AudiobookRequest(
            source=source,
            project=project,
            chapters=selection,
            output=source.with_suffix(".m4b"),
        )
        self.inspection = BookInspectionView(
            source=source,
            kind="book",
            title="Book",
            author="Writer",
            language="en-US",
            chapters=(
                BookChapterView(1, "Opening", "chapter-1", 100),
                BookChapterView(2, "Arrival", "chapter-2", 200),
            ),
        )
        self.workflow = WorkflowPlanView(
            source=source,
            workspace=project,
            workspace_mode="project",
            output=source.with_suffix(".m4b"),
            steps=(
                WorkflowStepView(
                    stage="render",
                    package="voicerender",
                    action="reuse",
                    selector="chapter-1",
                    reason="Already rendered",
                    state="complete",
                ),
            ),
        )

    def load_saved_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        return self.request

    def inspect_book(self, source: Path) -> BookInspectionView:
        return self.inspection

    def status(self, paths: ProjectPaths) -> WorkflowPlanView:
        return self.workflow


def test_chapter_list_for_source_defaults_all_selected(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    service = ChapterApplicationService(_Audiobook(source, tmp_path / "project", "1"))

    chapters = service.list(source)

    assert [chapter.selected for chapter in chapters] == [True, True]
    assert [chapter.char_count for chapter in chapters] == [100, 200]
    assert all(chapter.workflow_state is None for chapter in chapters)


def test_project_chapter_status_projects_selection_and_workflow_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = tmp_path / "book.ttsforge"
    project.mkdir()
    service = ChapterApplicationService(_Audiobook(source, project, "2"))

    chapters = service.status(ProjectPaths.for_root(project))

    assert [chapter.selected for chapter in chapters] == [False, True]
    assert chapters[0].workflow_state == "complete"
    assert chapters[0].estimated_duration_seconds is None
    assert chapters[0].final_duration_seconds is None


def test_chapter_select_accepts_equivalent_existing_scope(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = tmp_path / "book.ttsforge"
    service = ChapterApplicationService(_Audiobook(source, project, "1-2"))

    result = service.select(ProjectPaths.for_root(project), "2,1")

    assert result.selection == "1-2"
    assert result.selected_chapters == (1, 2)


def test_chapter_select_rejects_project_scope_change(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = tmp_path / "book.ttsforge"
    service = ChapterApplicationService(_Audiobook(source, project, "1"))

    with pytest.raises(ProjectScopeConflictError, match="separate project"):
        service.select(ProjectPaths.for_root(project), "2")


def test_chapter_select_rejects_invalid_selection(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = tmp_path / "book.ttsforge"
    service = ChapterApplicationService(_Audiobook(source, project, "1"))

    with pytest.raises(InputValidationError, match="exceeds total chapters"):
        service.select(ProjectPaths.for_root(project), "3")
