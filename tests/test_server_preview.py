from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from ttsforge.application.models import PreviewAudio
from ttsforge.application.preview import PreviewExcerpt, PreviewRequest, PreviewResult
from ttsforge.server.app import create_app


class _Cancellation:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _PreviewService:
    def __init__(self) -> None:
        self.request: PreviewRequest | None = None
        self.cancellation = _Cancellation()

    def new_cancellation_token(self) -> _Cancellation:
        return self.cancellation

    def preview(
        self, request: PreviewRequest, *, cancellation: object | None = None
    ) -> PreviewResult:
        self.request = request
        assert cancellation is self.cancellation
        return PreviewResult(
            narration_id=request.narration_id or "primary",
            excerpt=PreviewExcerpt(text=request.text or ""),
            audio=PreviewAudio(
                wav=b"RIFFpreview",
                sample_rate=24_000,
                channels=1,
                frames=120,
                duration_seconds=0.005,
            ),
        )


def test_preview_route_returns_ephemeral_wav_and_audio_metadata(tmp_path: Path) -> None:
    previews = _PreviewService()
    app = create_app(
        token="secret-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(
            audiobook=object(),
            catalog=object(),
            conversion=object(),
            preview=previews,
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/previews",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "project": str(tmp_path / "book.ttsforge"),
                "narration_id": "voice-one",
                "text": "Read this aloud.",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFpreview"
    assert response.headers["x-ttsforge-narration-id"] == "voice-one"
    assert response.headers["x-ttsforge-sample-rate"] == "24000"
    assert response.headers["x-ttsforge-channels"] == "1"
    assert previews.request == PreviewRequest(
        project=tmp_path / "book.ttsforge",
        narration_id="voice-one",
        text="Read this aloud.",
    )
    assert not previews.cancellation.cancelled
