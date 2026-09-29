"""Audiobook project workflow tests using Readio's public API shapes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import (
    AudiobookChapter,
    AudiobookInspection,
    AudiobookProjectChapter,
    AudiobookProjectResult,
    ProjectRef,
    ProjectSettings,
    SynthesisRequest,
    SynthesisResolution,
)

from ttsforge.audiobook import AudiobookConverter, LegacyWorkspaceError, ProjectSetup
from ttsforge.options import AudiobookOptions


def _project(path: Path) -> ProjectRef:
    return ProjectRef(
        root=path,
        project_id="project-id",
        name="Sample book",
        kind="audiobook",
        source_format="epub",
    )


def _inspection(source: Path) -> AudiobookInspection:
    chapters = tuple(
        AudiobookChapter(
            number=number,
            source_id=f"chapter-{number}",
            title=title,
            href=f"chapter-{number}.xhtml",
            parent_id=None,
            level=0,
            char_count=length,
            markdown=f"# {title}",
        )
        for number, title, length in (
            (1, "First", 20),
            (2, "Second", 30),
            (3, "Third", 40),
        )
    )
    return AudiobookInspection(
        source=source,
        metadata={"title": "Sample book", "authors": ["A. Writer"]},
        chapters=chapters,
    )


def test_create_project_uses_inspection_and_persists_normalized_chapters(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    project_path = tmp_path / "book.readio"
    project = _project(project_path)
    calls: list[tuple[Path, str, Path]] = []
    created = AudiobookProjectResult(
        project=project,
        source=source,
        chapters=(
            AudiobookProjectChapter(
                number=1, scope_id="chapter-0001", title="First", level=0
            ),
            AudiobookProjectChapter(
                number=3, scope_id="chapter-0003", title="Third", level=0
            ),
        ),
    )
    app = SimpleNamespace(
        audiobooks=SimpleNamespace(
            inspect=lambda path: _inspection(path),
            create_project_result=lambda path, *, chapters, output: (
                calls.append((path, chapters, output)) or created
            ),
        ),
        projects=SimpleNamespace(find=lambda path: None),
    )

    setup = AudiobookConverter(app=app).create_or_open_project(
        AudiobookOptions(source=source, chapters="3,1-1")
    )

    assert setup.project is project
    assert setup.created is True
    assert setup.selected_chapters == (1, 3)
    assert calls == [(source, "1,3", project_path)]


def test_existing_project_is_opened_and_not_reinitialized(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    project_path = tmp_path / "book.readio"
    project_path.mkdir()
    project = _project(project_path)
    opened: list[Path] = []
    created: list[Path] = []
    app = SimpleNamespace(
        audiobooks=SimpleNamespace(
            describe_project=lambda project: SimpleNamespace(
                chapters=(
                    AudiobookProjectChapter(
                        number=2,
                        scope_id="chapter-0002",
                        title="Second",
                        level=0,
                    ),
                )
            ),
            inspect=lambda path: pytest.fail(
                "existing project should not reinspect EPUB"
            ),
            create_project_result=lambda *args, **kwargs: created.append(project_path),
        ),
        projects=SimpleNamespace(
            find=lambda path: project,
            open=lambda path: opened.append(path) or project,
        ),
    )

    setup = AudiobookConverter(app=app).create_or_open_project(
        AudiobookOptions(source=source, chapters="2")
    )

    assert setup.project is project
    assert setup.created is False
    assert setup.selected_chapters == (2,)
    assert opened == [project_path]
    assert created == []


def test_legacy_workspace_is_preserved_and_requires_fresh_project(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    project_path = tmp_path / "book.readio"
    project_path.mkdir()
    app = SimpleNamespace(
        audiobooks=SimpleNamespace(),
        projects=SimpleNamespace(find=lambda path: None),
    )

    with pytest.raises(LegacyWorkspaceError, match="--fresh"):
        AudiobookConverter(app=app).create_or_open_project(
            AudiobookOptions(source=source)
        )

    assert project_path.is_dir()


def test_fresh_project_uses_new_path_without_deleting_legacy_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    project_path = tmp_path / "book.readio"
    project_path.mkdir()
    fresh_path = tmp_path / "book.fresh.readio"
    project = _project(fresh_path)
    created = AudiobookProjectResult(project=project, source=source, chapters=())
    calls: list[Path] = []
    app = SimpleNamespace(
        audiobooks=SimpleNamespace(
            inspect=lambda path: _inspection(path),
            create_project_result=lambda path, *, chapters, output: (
                calls.append(output) or created
            ),
        ),
        projects=SimpleNamespace(find=lambda path: pytest.fail("fresh skips lookup")),
    )

    setup = AudiobookConverter(app=app).create_or_open_project(
        AudiobookOptions(source=source, fresh=True)
    )

    assert setup.project is project
    assert setup.created is True
    assert calls == [fresh_path]
    assert project_path.is_dir()


def test_status_and_preview_delegate_to_project_service(tmp_path: Path) -> None:
    project = _project(tmp_path / "book.readio")
    status = object()
    preview = object()
    observed: dict[str, object] = {}

    def get_status(target: object) -> object:
        observed["status_target"] = target
        return status

    def render_preview(target: object, request: object) -> object:
        observed.update(preview_target=target, preview_request=request)
        return preview

    app = SimpleNamespace(
        projects=SimpleNamespace(status=get_status, preview=render_preview),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    actual_status = converter.status(project)
    actual_preview = converter.preview(
        project, AudiobookOptions(source=Path("book.epub"))
    )

    assert actual_status is status
    assert actual_preview is preview
    assert observed["status_target"] is project
    assert observed["preview_target"] is project
    assert observed["preview_request"].selection == "first:3"  # type: ignore[union-attr]


def test_preflight_resolves_and_retains_one_shared_synthesis_request(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    project = _project(tmp_path / "book.readio")
    request = SynthesisRequest(language="en-us", voice="af_heart")
    resolution = SynthesisResolution(
        engine="pykokoro",
        language="en-us",
        voice="af_heart",
        model="kokoro-v1",
        model_source="github",
        quality="fp32",
        speed=1.1,
        unit="paragraph",
        pause_mode="sentence",
        voice_level=None,
    )
    observed: list[tuple[object, object]] = []

    def resolve(target: object, synthesis: object) -> SynthesisResolution:
        observed.append((target, synthesis))
        return resolution

    converter = AudiobookConverter(
        app=SimpleNamespace(projects=SimpleNamespace(resolve_synthesis=resolve))
    )
    chapters = (
        AudiobookProjectChapter(number=2, scope_id="scope-2", title="Second", level=0),
    )
    setup = ProjectSetup(project=project, created=False, chapters=chapters)
    options = AudiobookOptions(source=source, output=tmp_path / "book.m4b")

    preflight = converter.preflight(
        setup, _inspection(source), options, synthesis=request
    )

    assert observed == [(project, request)]
    assert preflight.synthesis_request is request
    assert preflight.synthesis is resolution
    assert preflight.title == "Sample book"
    assert preflight.author == "A. Writer"
    assert preflight.chapters == chapters
    assert tuple(chapter.number for chapter in preflight.chapters) == (2,)


def test_converter_reads_and_saves_settings_through_project_service() -> None:
    project = _project(Path("book.readio"))
    settings = ProjectSettings()
    configured = ProjectSettings(composition=None)
    calls: list[tuple[str, object, object | None]] = []

    def read(target: object) -> ProjectSettings:
        calls.append(("settings", target, None))
        return settings

    def configure(target: object, value: ProjectSettings) -> ProjectSettings:
        calls.append(("configure", target, value))
        return configured

    app = SimpleNamespace(projects=SimpleNamespace(settings=read, configure=configure))
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    assert converter.project_settings(project) is settings
    assert converter.save_project_settings(project, settings) is configured
    assert calls == [
        ("settings", project, None),
        ("configure", project, settings),
    ]
