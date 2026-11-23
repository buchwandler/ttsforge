from __future__ import annotations

from pathlib import Path

from ttsforge.application import (
    AudiobookApplicationService,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    LibraryApplicationService,
    NarrationApplicationService,
    ProjectPaths,
    WorkflowPlanView,
)


class FakeBackend:
    def __init__(self) -> None:
        self.setups: dict[Path, AudiobookRequest] = {}

    def inspect_source(self, source: Path) -> BookInspectionView:
        return BookInspectionView(
            source=source,
            kind="book",
            title="Book title",
            author="Author name",
            language="en-US",
            chapters=(
                BookChapterView(1, "Opening"),
                BookChapterView(2, "Middle"),
                BookChapterView(3, "Ending"),
            ),
        )

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        return self.setups[paths.intent]

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None:
        paths.setup_root.mkdir(parents=True, exist_ok=True)
        paths.intent.touch()
        paths.profile.touch()
        self.setups[paths.intent] = request

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object:
        return paths, request

    def inspect(self, request: object) -> WorkflowPlanView:
        paths, selected = request  # type: ignore[misc]
        return WorkflowPlanView(
            source=selected.source,
            workspace=paths.bundle,
            workspace_mode="bundle",
            output=selected.output,
            steps=(),
        )


def _library(tmp_path: Path) -> tuple[LibraryApplicationService, ProjectPaths]:
    root = tmp_path / "library"
    root.mkdir()
    source = tmp_path / "Book.epub"
    source.touch()
    paths = ProjectPaths.for_root(root / "Book.ttsforge")
    request = AudiobookRequest(
        source=source,
        project=paths.root,
        chapters="1,3",
        output=tmp_path / "Book.m4b",
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
    )
    backend = FakeBackend()
    backend.save_setup(paths, request)
    audiobook = AudiobookApplicationService(backend)
    narrations = NarrationApplicationService(audiobook, object())  # type: ignore[arg-type]
    return LibraryApplicationService(audiobook, narrations), paths


def test_library_discovers_and_summarizes_project_through_application_services(
    tmp_path: Path,
) -> None:
    library, paths = _library(tmp_path)
    (paths.root / "audiobook-metadata.json").write_text(
        '{"title":"Override title"}', encoding="utf-8"
    )

    projects = library.list(paths.root.parent)

    assert len(projects) == 1
    project = projects[0]
    assert project.project == paths.root
    assert project.title == "Override title"
    assert project.author == "Author name"
    assert project.source == tmp_path / "Book.epub"
    assert project.chapter_count == 3
    assert project.selected_chapter_count == 2
    assert project.primary_narration_id == "primary"
    assert project.outputs == (tmp_path / "Book.m4b",)
    assert project.last_activity is not None
    assert project.error is None
    assert library.get(project.project_id) == project


def test_library_keeps_malformed_candidates_visible(tmp_path: Path) -> None:
    library, paths = _library(tmp_path)
    malformed = paths.root.parent / "Broken.ttsforge"
    empty = paths.root.parent / "Empty.ttsforge"
    empty.mkdir()
    malformed.mkdir()
    (malformed / "render.readio.toml").touch()

    projects = library.list(paths.root.parent)

    assert [project.project.name for project in projects] == [
        "Book.ttsforge",
        "Broken.ttsforge",
        "Empty.ttsforge",
    ]
    broken = projects[1]
    assert broken.error is not None
    assert "Incomplete TTSForge setup" in broken.error
    assert broken.source is None
    assert broken.narrations == ()


def test_library_requires_an_existing_directory(tmp_path: Path) -> None:
    library, _ = _library(tmp_path)

    try:
        library.list(tmp_path / "missing")
    except ValueError as exc:
        assert "must be a directory" in str(exc)
    else:
        raise AssertionError("expected invalid library root")
