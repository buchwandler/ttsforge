from __future__ import annotations

from pathlib import Path

import pytest

from ttsforge.application import (
    AudiobookApplicationService,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ConversionCoordinator,
    InputValidationError,
    NarrationApplicationService,
    OperationConflictError,
    ProjectPaths,
    WorkflowPlanView,
)
from ttsforge.application.catalog import TargetChoiceView, VoiceChoiceView


class FakeJobManager:
    def submit(self, request, overrides, *, narration_id=None):
        from types import SimpleNamespace

        from ttsforge.server.jobs import JobState

        return SimpleNamespace(id="narration-job", state=JobState.QUEUED)

    def shutdown(self) -> None:
        pass


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
            chapters=(BookChapterView(1, "Opening"),),
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


class FakeCatalog:
    def targets(self, **kwargs) -> tuple[TargetChoiceView, ...]:
        return (
            TargetChoiceView(
                id="target-a",
                languages=("en-US",),
                status="ready",
                runtime_available=True,
                default_voice="voice-a",
                voice_count=2,
                qualities=(),
                voice_mode="named",
                sample_rate=24000,
                features=(),
                reference_only=False,
            ),
        )

    def voices(self, **kwargs) -> tuple[VoiceChoiceView, ...]:
        return tuple(
            VoiceChoiceView(
                id=voice,
                language="en-US",
                locale="en-US",
                language_label="English",
                gender="unknown",
                default=voice == "voice-a",
                runtime_available=True,
            )
            for voice in ("voice-a", "voice-b", "voice-c")
        )


def _services(tmp_path: Path):
    source = tmp_path / "Book.epub"
    source.touch()
    project = ProjectPaths.for_source(source)
    primary = AudiobookRequest(
        source=source,
        project=project.root,
        output=tmp_path / "Book.m4b",
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
    )
    backend = FakeBackend()
    backend.save_setup(project, primary)
    audiobook = AudiobookApplicationService(backend)
    narrations = NarrationApplicationService(audiobook, FakeCatalog())
    return project, backend, audiobook, narrations


def test_create_persists_display_name_and_uses_it_for_output(tmp_path: Path) -> None:
    project, backend, _, narrations = _services(tmp_path)

    created = narrations.create(
        project,
        display_name="Kokoro Heart",
        engine="engine-a",
        target="target-a",
        voice="voice-b",
    )

    assert created.display_name == "Kokoro Heart"
    assert created.primary is False
    assert created.output == tmp_path / "Book [Kokoro Heart].m4b"
    variant_paths = ProjectPaths.for_variant(project.root, created.id)
    assert variant_paths.intent.is_file()
    assert variant_paths.profile.is_file()
    assert (variant_paths.setup_root / "narration.json").is_file()
    assert backend.setups[project.intent].voice == "voice-a"
    assert narrations.get(project, created.id).display_name == "Kokoro Heart"


def test_profile_path_resolves_primary_and_additional_narrations(
    tmp_path: Path,
) -> None:
    project, _, _, narrations = _services(tmp_path)
    alternate = narrations.create(
        project,
        display_name="Kokoro Heart",
        engine="engine-a",
        target="target-a",
        voice="voice-b",
    )

    assert narrations.profile_path(project, "primary") == project.profile
    assert (
        narrations.profile_path(project, alternate.id)
        == ProjectPaths.for_variant(project.root, alternate.id).profile
    )


def test_display_name_collisions_get_distinct_outputs_and_render_uses_saved_setup(
    tmp_path: Path,
) -> None:
    project, _, _, narrations = _services(tmp_path)
    first = narrations.create(
        project,
        display_name="Kokoro",
        engine="engine-a",
        target="target-a",
        voice="voice-b",
    )
    second = narrations.create(
        project,
        display_name="Kokoro",
        engine="engine-a",
        target="target-a",
        voice="voice-c",
    )

    assert first.output == tmp_path / "Book [Kokoro].m4b"
    assert second.output == tmp_path / "Book [Kokoro] (2).m4b"
    request, overrides = narrations.request_for_render(project, first.id)
    assert request.new_variant
    assert request.voice == "voice-b"
    assert overrides.includes("output")


def test_delete_removes_only_additional_setup_and_protects_primary(
    tmp_path: Path,
) -> None:
    project, _, _, narrations = _services(tmp_path)
    created = narrations.create(
        project,
        display_name="Kokoro",
        engine="engine-a",
        target="target-a",
        voice="voice-b",
    )
    assert created.output is not None
    created.output.touch()

    narrations.delete(project, created.id)

    assert created.output.is_file()
    assert not ProjectPaths.for_variant(project.root, created.id).setup_root.exists()
    with pytest.raises(
        OperationConflictError, match="primary narration cannot be deleted"
    ):
        narrations.delete(project, "primary")
    with pytest.raises(InputValidationError, match="project-local"):
        narrations.get(project, "../outside")


def test_studio_narration_routes_create_list_preflight_job_and_delete(
    tmp_path: Path,
) -> None:
    pytest.importorskip("fastapi")
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from ttsforge.server.app import create_app

    project, _, audiobook, _ = _services(tmp_path)
    catalog = FakeCatalog()
    app = create_app(
        token="test-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(
            audiobook=audiobook,
            catalog=catalog,
            conversion=ConversionCoordinator(audiobook, catalog),
        ),
        job_manager=FakeJobManager(),
    )
    headers = {"Authorization": "Bearer test-token"}
    base_url = "/api/v1/projects/narrations"

    with TestClient(app) as client:
        created = client.post(
            base_url,
            headers=headers,
            json={
                "project": str(project.root),
                "display_name": "Kokoro Heart",
                "engine": "engine-a",
                "target": "target-a",
                "voice": "voice-b",
            },
        )
        narration_id = created.json()["id"]
        listed = client.get(
            base_url, params={"project": str(project.root)}, headers=headers
        )
        preflight = client.post(
            f"{base_url}/{narration_id}/preflight",
            params={"project": str(project.root)},
            headers=headers,
        )
        job = client.post(
            f"{base_url}/{narration_id}/jobs",
            params={"project": str(project.root)},
            headers=headers,
        )
        deleted = client.delete(
            f"{base_url}/{narration_id}",
            params={"project": str(project.root)},
            headers=headers,
        )

    assert created.status_code == 201
    assert created.json()["display_name"] == "Kokoro Heart"
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["narrations"]] == [
        "primary",
        narration_id,
    ]
    assert preflight.status_code == 200
    assert preflight.json()["request"]["voice"] == "voice-b"
    assert job.status_code == 202
    assert job.json() == {"id": "narration-job", "state": "queued"}
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
