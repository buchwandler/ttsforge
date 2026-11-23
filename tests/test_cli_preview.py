from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from typer.testing import CliRunner

from ttsforge.application.models import PreviewAudio
from ttsforge.application.preview import (
    PreviewExcerpt,
    PreviewRequest,
    PreviewResult,
)
from ttsforge.cli import app

cli_module = import_module("ttsforge.cli.app")


class _Cancellation:
    def cancel(self) -> None:
        pass


class _PreviewService:
    instances: list[_PreviewService] = []

    def __init__(self, narrations: object, backend: object) -> None:
        del narrations, backend
        self.request: PreviewRequest | None = None
        self.cancellation: object | None = None
        self.__class__.instances.append(self)

    def new_cancellation_token(self) -> _Cancellation:
        return _Cancellation()

    def preview(
        self, request: PreviewRequest, *, cancellation: object | None = None
    ) -> PreviewResult:
        self.request = request
        self.cancellation = cancellation
        return PreviewResult(
            narration_id=request.narration_id or "primary",
            excerpt=PreviewExcerpt(text=request.text or ""),
            audio=PreviewAudio(
                wav=b"RIFFpreview",
                sample_rate=24_000,
                channels=1,
                frames=240,
                duration_seconds=0.01,
            ),
        )


def test_preview_command_writes_wav_only_to_the_requested_path(
    tmp_path: Path, monkeypatch
) -> None:
    _PreviewService.instances.clear()
    monkeypatch.setattr(cli_module, "_service", lambda: (object(), object()))
    monkeypatch.setattr(cli_module, "PreviewApplicationService", _PreviewService)
    project = tmp_path / "book.ttsforge"
    output = tmp_path / "previews" / "sample.wav"

    result = CliRunner().invoke(
        app,
        [
            "preview",
            str(project),
            "--text",
            "A short preview.",
            "--narration",
            "voice-one",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["narration_id"] == "voice-one"
    assert payload["audio"]["sample_rate"] == 24_000
    assert payload["output"] == str(output)
    assert output.read_bytes() == b"RIFFpreview"
    assert _PreviewService.instances[0].request == PreviewRequest(
        project=project,
        narration_id="voice-one",
        text="A short preview.",
    )
    assert _PreviewService.instances[0].cancellation is not None
    assert not project.exists()


def test_preview_command_refuses_to_overwrite_an_existing_wav(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cli_module, "_service", lambda: (object(), object()))
    monkeypatch.setattr(cli_module, "PreviewApplicationService", _PreviewService)
    output = tmp_path / "sample.wav"
    output.write_bytes(b"existing")

    result = CliRunner().invoke(
        app,
        [
            "preview",
            str(tmp_path / "book.ttsforge"),
            "--text",
            "Hi",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "Preview output already exists" in result.output
    assert output.read_bytes() == b"existing"
