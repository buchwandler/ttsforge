from __future__ import annotations

from pathlib import Path

import pytest

from ttsforge.application.errors import ProjectScopeConflictError
from ttsforge.application.models import (
    AudiobookRequest,
    BookInspectionView,
    CatalogItemView,
    ChapterView,
    InputOverrides,
    OperationResultView,
    PreviewView,
    ProjectPlanView,
    ProjectStatusView,
    ProjectView,
    SetupOrigins,
    SynthesisView,
)
from ttsforge.application.service import AudiobookApplicationService


def _chapters() -> tuple[ChapterView, ...]:
    return tuple(
        ChapterView(number=index, title=f"Chapter {index}", source_id=f"c{index}")
        for index in range(1, 4)
    )


def _project(path: Path, chapters: tuple[ChapterView, ...] = ()) -> ProjectView:
    return ProjectView(
        path=path,
        project_id="project-id",
        name="A book",
        kind="audiobook",
        source_format="epub",
        chapters=chapters,
    )


class _FakeBackend:
    def __init__(self, existing: ProjectView | None = None) -> None:
        self.existing = existing
        self.calls: list[tuple[object, ...]] = []
        self.inspection = BookInspectionView(
            source=Path("book.epub"),
            metadata={"title": "A title", "authors": ["One", "Two"]},
            chapters=_chapters(),
        )
        self.synthesis = SynthesisView(
            engine="kokoro",
            language="en-us",
            voice="af_sarah",
            model="v1.0",
            speed=1.0,
            unit="sentence",
            pause_mode="auto",
        )

    def inspect_book(self, source: Path) -> BookInspectionView:
        self.calls.append(("inspect", source))
        return self.inspection

    def find_project(self, path: Path) -> ProjectView | None:
        self.calls.append(("find", path))
        return self.existing

    def open_project(self, project: ProjectView) -> ProjectView:
        self.calls.append(("open", project.path))
        return project

    def create_project(
        self,
        inspection: BookInspectionView,
        path: Path,
        chapter_numbers: tuple[int, ...],
    ) -> ProjectView:
        self.calls.append(("create", path, chapter_numbers))
        chapters = tuple(
            chapter
            for chapter in inspection.chapters
            if chapter.number in chapter_numbers
        )
        return _project(path, chapters)

    def resolve_synthesis(
        self,
        project: ProjectView,
        request: AudiobookRequest,
        *,
        use_saved_settings: bool,
    ) -> SynthesisView:
        self.calls.append(("resolve", project.path, use_saved_settings))
        return self.synthesis

    def save_synthesis_setup(
        self, project: ProjectView, request: AudiobookRequest, synthesis: SynthesisView
    ) -> AudiobookRequest:
        self.calls.append(("save", project.path))
        return request

    def load_setup(self, project: ProjectView, request: AudiobookRequest):
        self.calls.append(("load_setup", project.path))
        return (
            AudiobookRequest(source=request.source, engine="kokoro", language="en-us"),
            SetupOrigins(project=frozenset({"engine", "language"})),
            True,
        )

    def build(
        self, project: ProjectView, request: AudiobookRequest
    ) -> OperationResultView:
        self.calls.append(("build", project.path))
        return OperationResultView("build", project)

    def preview(
        self, project: ProjectView, request: AudiobookRequest, selection: str
    ) -> PreviewView:
        self.calls.append(("preview", project.path, selection))
        return PreviewView(project, items=3, frames=100, sample_rate=24000)

    def status(self, project: ProjectView | Path) -> ProjectStatusView:
        self.calls.append(("status", project))
        resolved = project if isinstance(project, ProjectView) else _project(project)
        return ProjectStatusView(resolved, "ready")

    def plan(self, project: ProjectView | Path) -> ProjectPlanView:
        self.calls.append(("plan", project))
        resolved = project if isinstance(project, ProjectView) else _project(project)
        return ProjectPlanView(resolved)

    def catalog_choices(self, kind: str, query) -> tuple[CatalogItemView, ...]:
        self.calls.append(("catalog", kind, query))
        return (CatalogItemView("kokoro", "Kokoro", engine="kokoro"),)


def test_prepare_new_project_applies_selected_chapter_scope() -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"))

    preparation = service.prepare_project(request, chapter_selection="1,3")

    assert preparation.created
    assert preparation.selected_chapters == (1, 3)
    assert ("create", Path("book.ssmdbook"), (1, 3)) in backend.calls


def test_prepare_reuses_project_and_rejects_a_scope_change() -> None:
    existing = _project(Path("book.readio"), (_chapters()[0], _chapters()[2]))
    backend = _FakeBackend(existing)
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"))

    preparation = service.prepare_project(request)
    assert preparation.project is existing
    assert not preparation.created
    assert preparation.selected_chapters == (1, 3)

    with pytest.raises(
        ProjectScopeConflictError, match="Existing project uses chapters"
    ):
        service.prepare_project(request, chapter_selection="1-2")


def test_fresh_project_uses_a_separate_nonexisting_path(tmp_path: Path) -> None:
    current = tmp_path / "book.readio"
    current.touch()
    first_fresh = tmp_path / "book.fresh.readio"
    first_fresh.touch()
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(
        source=tmp_path / "book.epub", project=current, fresh=True
    )

    preparation = service.prepare_project(request)

    assert preparation.created
    assert preparation.project.path == tmp_path / "book.fresh-2.readio"
    assert not any(call[0] == "find" for call in backend.calls)


def test_setup_is_resolved_before_persistence_and_persisted_before_build() -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"))
    preparation = service.prepare_project(request)

    resolved = service.resolve_and_save_setup(preparation, request)
    preflight = service.preflight(resolved)

    assert preflight.settings_saved
    assert preflight.title == "A title"
    assert preflight.author == "One, Two"
    assert [call[0] for call in backend.calls[-2:]] == ["resolve", "save"]

    service.build(resolved)
    assert [call[0] for call in backend.calls[-3:]] == ["resolve", "save", "build"]


def test_cancel_after_setup_persistence_does_not_build() -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"))
    preparation = service.prepare_project(request)
    service.resolve_and_save_setup(preparation, request)

    assert "save" in [call[0] for call in backend.calls]
    assert "build" not in [call[0] for call in backend.calls]


def test_preview_status_plan_and_catalog_delegate_through_backend() -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"))
    preparation = service.prepare_project(request)

    preview = service.preview(preparation, request, selection="first:2")
    status = service.status(preparation.project)
    plan = service.plan(preparation.project)
    catalog = service.catalog_choices("engines", {"language": "en-us"})

    assert preview.items == 3
    assert status.status == "ready"
    assert plan.project == preparation.project
    assert catalog[0].id == "kokoro"
    assert ("preview", preparation.project.path, "first:2") in backend.calls


def test_saved_setup_merge_keeps_explicit_choices_and_tracks_origins() -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    request = AudiobookRequest(source=Path("book.epub"), language="de")

    merged = service.merge_saved_settings(
        _project(Path("book.readio")),
        request,
        InputOverrides(fields=frozenset({"language"})),
        created=False,
        interactive=True,
    )

    assert merged.request.language == "de"
    assert merged.request.engine is None
    assert merged.origins.project == frozenset({"engine", "language"})
    assert merged.has_saved_synthesis
    assert merged.settings_source == "project+cli"
    assert backend.calls[0][0] == "load_setup"
