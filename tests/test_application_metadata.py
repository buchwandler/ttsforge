from __future__ import annotations

import json
from pathlib import Path

import pytest

from ttsforge.application.errors import InputValidationError, OperationConflictError
from ttsforge.application.metadata import (
    MetadataApplicationService,
    apply_project_metadata,
    load_metadata_overrides,
    metadata_overrides_path,
    save_metadata_overrides,
)
from ttsforge.application.models import (
    AudiobookMetadata,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ProjectPaths,
)


class _Audiobook:
    def __init__(self, project: Path, source: Path) -> None:
        self.project = project
        self.request = AudiobookRequest(
            source=source,
            project=project,
            language="en-US",
            voice="Voice Label",
            metadata=AudiobookMetadata(title="Saved title", year="2021"),
        )
        self.inspection = BookInspectionView(
            source=source,
            kind="book",
            title="Source title",
            author="Source author",
            language="en-US",
            chapters=(BookChapterView(1, "Opening", "c1", 120),),
            metadata=AudiobookMetadata(
                title="Source title",
                author="Source author",
                language="en-US",
                publisher="Source publisher",
            ),
        )

    def load_saved_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        assert paths.root == self.project
        return self.request

    def inspect_book(self, source: Path) -> BookInspectionView:
        assert source == self.request.source
        return self.inspection


def test_metadata_show_merges_source_saved_and_override_with_narrator_default(
    tmp_path: Path,
) -> None:
    project = tmp_path / "book.ttsforge"
    source = tmp_path / "book.epub"
    source.touch()
    service = MetadataApplicationService(_Audiobook(project, source))
    paths = ProjectPaths.for_root(project)

    initial = service.show(paths)
    assert initial.source_metadata.title == "Source title"
    assert initial.effective.title == "Saved title"
    assert initial.effective.narrator == "Voice Label"

    updated = service.set(
        paths,
        {"author": "Override author", "series": "North Shore", "year": "2024"},
    )
    assert updated.effective.title == "Saved title"
    assert updated.effective.author == "Override author"
    assert updated.effective.series == "North Shore"
    assert updated.effective.publisher == "Source publisher"
    assert load_metadata_overrides(project).year == "2024"
    assert metadata_overrides_path(project).is_file()

    report = service.validate(paths)
    assert report.valid
    assert {finding.id for finding in report.findings} == {"metadata.cover_missing"}


def test_project_metadata_overrides_apply_to_readio_request(tmp_path: Path) -> None:
    project = tmp_path / "book.ttsforge"
    request = AudiobookRequest(
        source=tmp_path / "book.epub",
        metadata=AudiobookMetadata(title="Source", author="Writer"),
    )
    save_metadata_overrides(
        project,
        AudiobookMetadata(
            title="Override",
            subtitle="A short subtitle",
            series_number="3",
            cover=tmp_path / "cover.jpg",
        ),
    )

    selected = apply_project_metadata(request, project)

    assert selected.title == "Override"
    assert selected.metadata.to_readio_mapping() == {
        "title": "Override",
        "subtitle": "A short subtitle",
        "author": "Writer",
        "series_index": "3",
    }
    assert selected.cover == tmp_path / "cover.jpg"


def test_metadata_set_rejects_empty_and_invalid_values(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    service = MetadataApplicationService(_Audiobook(tmp_path / "book.ttsforge", source))
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")

    with pytest.raises(InputValidationError, match="at least one"):
        service.set(paths, {})
    with pytest.raises(InputValidationError, match="four digits"):
        service.set(paths, {"year": "24"})
    with pytest.raises(InputValidationError, match="cannot be empty"):
        service.set(paths, {"title": "  "})


def test_metadata_validation_reports_malformed_saved_year(tmp_path: Path) -> None:
    project = tmp_path / "book.ttsforge"
    source = tmp_path / "book.epub"
    source.touch()
    service = MetadataApplicationService(_Audiobook(project, source))
    save_metadata_overrides(project, AudiobookMetadata(year="Twenty"))

    report = service.validate(ProjectPaths.for_root(project))

    assert not report.valid
    assert [finding.id for finding in report.findings] == [
        "metadata.cover_missing",
        "metadata.year_invalid",
    ]


def test_metadata_override_file_rejects_unknown_fields(tmp_path: Path) -> None:
    project = tmp_path / "book.ttsforge"
    project.mkdir()
    metadata_overrides_path(project).write_text(
        json.dumps({"duration": "not-app-owned"}), encoding="utf-8"
    )

    with pytest.raises(OperationConflictError, match="metadata fields"):
        load_metadata_overrides(project)
