from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import readio.api as readio_api
from readio.api import Readio
from readio.errors import WorkflowCancelledError

from ttsforge.application.errors import WorkflowFailureError
from ttsforge.readio_backend import ReadioBackend


def test_preview_adapter_uses_readio_synthesis_and_maps_audio_metadata() -> None:
    audio = SimpleNamespace(
        to_wav_bytes=lambda: b"RIFFpreview",
        sample_rate=24_000,
        channels=2,
        frames=960,
        duration_seconds=0.02,
    )
    spoken = SimpleNamespace(audio=audio, warnings=("voice warning",))
    calls: list[tuple[object, object]] = []

    def synthesize(request: object, *, cancellation: object) -> object:
        calls.append((request, cancellation))
        return spoken

    backend = ReadioBackend(app=cast(Readio, SimpleNamespace(synthesize=synthesize)))
    cancellation = backend.new_cancellation_token()
    profile = Path("project/variants/voice/narrator.renderprofile.toml")

    result = backend.synthesize_preview(
        text="A short preview.", profile=profile, cancellation=cancellation
    )

    assert isinstance(cancellation, readio_api.CancellationToken)
    assert calls[0][0] == readio_api.SpeakRequest(
        text="A short preview.", profile=profile
    )
    assert calls[0][1] is cancellation
    assert result.wav == b"RIFFpreview"
    assert result.sample_rate == 24_000
    assert result.channels == 2
    assert result.frames == 960
    assert result.duration_seconds == 0.02
    assert result.warnings == ("voice warning",)


def test_preview_adapter_projects_readio_cancellation() -> None:
    def synthesize(request: object, *, cancellation: object) -> object:
        del request, cancellation
        raise WorkflowCancelledError()

    backend = ReadioBackend(app=cast(Readio, SimpleNamespace(synthesize=synthesize)))

    with pytest.raises(WorkflowFailureError) as raised:
        backend.synthesize_preview(text="Stop", profile=Path("profile.toml"))

    assert raised.value.code == "cancellation_requested"
    assert raised.value.category == "cancelled"
