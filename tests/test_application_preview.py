from __future__ import annotations

from pathlib import Path

import pytest

from ttsforge.application.errors import InputValidationError
from ttsforge.application.models import PreviewAudio, ProjectPaths
from ttsforge.application.preview import PreviewApplicationService, PreviewRequest


class _Cancellation:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _Narrations:
    def __init__(self) -> None:
        self.calls: list[tuple[ProjectPaths, str]] = []

    def profile_path(self, paths: ProjectPaths, narration_id: str) -> Path:
        self.calls.append((paths, narration_id))
        if narration_id == "primary":
            return paths.profile
        return ProjectPaths.for_variant(paths.root, narration_id).profile


class _Backend:
    def __init__(self) -> None:
        self.token = _Cancellation()
        self.calls: list[tuple[object, ...]] = []
        self.audio = PreviewAudio(
            wav=b"RIFFpreview",
            sample_rate=24_000,
            channels=1,
            frames=120,
            duration_seconds=0.005,
            warnings=("sample warning",),
        )

    def new_cancellation_token(self) -> _Cancellation:
        return self.token

    def synthesize_preview(
        self,
        *,
        text: str,
        profile: Path,
        role: str | None = None,
        cancellation: object | None = None,
    ) -> PreviewAudio:
        self.calls.append((text, profile, role, cancellation))
        return self.audio


def _service() -> tuple[PreviewApplicationService, _Narrations, _Backend]:
    narrations = _Narrations()
    backend = _Backend()
    return PreviewApplicationService(narrations, backend), narrations, backend


def test_preview_uses_selected_saved_profile_and_returns_ephemeral_audio(
    tmp_path: Path,
) -> None:
    service, narrations, backend = _service()
    project = tmp_path / "book.ttsforge"

    result = service.preview(
        PreviewRequest(
            project=project,
            narration_id="kokoro-voice",
            text="  Hello, listener.  ",
        )
    )

    assert result.narration_id == "kokoro-voice"
    assert result.excerpt.text == "Hello, listener."
    assert result.excerpt.source == "explicit"
    assert result.audio is backend.audio
    assert narrations.calls == [(ProjectPaths.for_root(project), "kokoro-voice")]
    assert backend.calls == [
        (
            "Hello, listener.",
            ProjectPaths.for_variant(project, "kokoro-voice").profile,
            None,
            backend.token,
        )
    ]
    assert not project.exists()


def test_preview_defaults_to_primary_narration(tmp_path: Path) -> None:
    service, narrations, backend = _service()

    result = service.preview(
        PreviewRequest(project=tmp_path / "book.ttsforge", text="Hi")
    )

    assert result.narration_id == "primary"
    assert narrations.calls[0][1] == "primary"
    assert (
        backend.calls[0][1] == ProjectPaths.for_root(tmp_path / "book.ttsforge").profile
    )


@pytest.mark.parametrize("text", [None, "", " \t\n "])
def test_preview_rejects_missing_or_blank_text_without_synthesizing(
    tmp_path: Path, text: str | None
) -> None:
    service, narrations, backend = _service()

    with pytest.raises(InputValidationError, match="Preview text cannot be blank"):
        service.preview(PreviewRequest(project=tmp_path, text=text))

    assert not narrations.calls
    assert not backend.calls


@pytest.mark.parametrize(
    ("chapter", "paragraph"),
    [(1, None), (None, 2)],
)
def test_preview_rejects_source_excerpts_until_readio_exposes_the_api(
    tmp_path: Path, chapter: int | None, paragraph: int | None
) -> None:
    service, narrations, backend = _service()

    with pytest.raises(InputValidationError, match="public source excerpt API"):
        service.preview(
            PreviewRequest(
                project=tmp_path,
                text="Do not use this text for an excerpt request.",
                chapter=chapter,
                paragraph=paragraph,
            )
        )

    assert not narrations.calls
    assert not backend.calls


def test_preview_accepts_an_external_cancellation_token(tmp_path: Path) -> None:
    service, _, backend = _service()
    cancellation = _Cancellation()

    service.preview(
        PreviewRequest(project=tmp_path, text="Hello"), cancellation=cancellation
    )

    assert backend.calls[0][3] is cancellation
