from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from ttsforge.application.models import (
    AudiobookMetadata,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    WorkflowPlanView,
    WorkflowStepView,
)
from ttsforge.server.app import create_app


class _Audiobook:
    def __init__(self, source: Path, project: Path, output: Path) -> None:
        self.request = AudiobookRequest(
            source=source,
            project=project,
            chapters="1",
            output=output,
            engine="engine",
            target="target",
            voice="voice",
            metadata=AudiobookMetadata(title="Book", author="Writer", language="en-US"),
        )
        self.inspection = BookInspectionView(
            source=source,
            kind="book",
            title="Book",
            author="Writer",
            language="en-US",
            chapters=(
                BookChapterView(1, "Opening", "c1", 100),
                BookChapterView(2, "Ending", "c2", 200),
            ),
        )
        self.workflow = WorkflowPlanView(
            source=source,
            workspace=project,
            workspace_mode="project",
            output=output,
            steps=(
                WorkflowStepView(
                    stage="export",
                    package="audioexport",
                    action="reuse",
                    selector=None,
                    reason="Output is reusable",
                    state="complete",
                ),
            ),
        )

    def load_saved_setup(self, paths):
        return self.request

    def inspect_book(self, source):
        return self.inspection

    def list_variants(self, paths, *, source=None):
        return ()

    def status(self, paths):
        return self.workflow


def test_studio_metadata_chapter_and_qc_routes(tmp_path: Path) -> None:
    project = tmp_path / "book.ttsforge"
    project.mkdir()
    source = tmp_path / "book.epub"
    source.touch()
    output = tmp_path / "book.m4b"
    output.write_bytes(b"audio")
    audiobook = _Audiobook(source, project, output)
    app = create_app(
        token="secret-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(
            audiobook=audiobook,
            catalog=object(),
            conversion=object(),
        ),
    )
    headers = {"Authorization": "Bearer secret-token"}

    with TestClient(app) as client:
        metadata = client.get(
            "/api/v1/projects/metadata",
            params={"project": str(project)},
            headers=headers,
        )
        updated = client.patch(
            "/api/v1/projects/metadata",
            headers=headers,
            json={"project": str(project), "metadata": {"series": "North Shore"}},
        )
        chapters = client.get(
            "/api/v1/projects/chapters",
            params={"project": str(project)},
            headers=headers,
        )
        selection = client.post(
            "/api/v1/projects/chapters/select",
            headers=headers,
            json={"project": str(project), "selection": "1"},
        )
        conflict = client.post(
            "/api/v1/projects/chapters/select",
            headers=headers,
            json={"project": str(project), "selection": "2"},
        )
        report = client.post(
            "/api/v1/projects/qc",
            headers=headers,
            json={"project": str(project)},
        )
        validation = client.post(
            "/api/v1/projects/metadata/validate",
            headers=headers,
            json={"project": str(project)},
        )

    assert metadata.status_code == 200
    assert metadata.json()["effective"]["title"] == "Book"
    assert updated.status_code == 200
    assert updated.json()["effective"]["series"] == "North Shore"
    assert chapters.status_code == 200
    assert chapters.json()["chapters"][0]["selected"] is True
    assert selection.status_code == 200
    assert selection.json()["selection"] == "1"
    assert conflict.status_code == 409
    assert report.status_code == 200
    assert report.json()["passed"] is True
    assert report.json()["findings"][-1]["id"] == "media.deep_qc_unavailable"
    assert validation.status_code == 200
    assert validation.json()["valid"] is True


def test_studio_metadata_update_requires_at_least_one_value(tmp_path: Path) -> None:
    project = tmp_path / "book.ttsforge"
    project.mkdir()
    source = tmp_path / "book.epub"
    source.touch()
    output = tmp_path / "book.m4b"
    audiobook = _Audiobook(source, project, output)
    app = create_app(
        token="secret-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(
            audiobook=audiobook,
            catalog=object(),
            conversion=object(),
        ),
    )

    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/projects/metadata",
            headers={"Authorization": "Bearer secret-token"},
            json={"project": str(project), "metadata": {}},
        )

    assert response.status_code == 400
    assert "at least one" in response.json()["error"]["message"]
