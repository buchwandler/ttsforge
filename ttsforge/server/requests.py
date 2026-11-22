"""Convert validated HTTP/worker request models at the application boundary."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from ..application import AudiobookRequest, InputOverrides, InputValidationError
from .models import AudiobookRequestModel


def application_request(model: AudiobookRequestModel) -> AudiobookRequest:
    return AudiobookRequest(
        source=Path(model.source).expanduser(),
        project=_path(model.project),
        chapters=model.chapters,
        output=_path(model.output),
        language=model.language,
        engine=model.engine,
        target=model.target,
        voice=model.voice,
        engine_options=model.engine_options,
        speed=model.speed,
        spacy=model.spacy,
        speech_profile=_path(model.speech_profile),
        pause_timing=model.pause_timing,
        bitrate=model.bitrate,
        target_lufs=model.target_lufs,
        title=model.title,
        author=model.author,
        cover=_path(model.cover),
        offline=model.offline,
        refresh=model.refresh,
        rebuild_from=model.rebuild_from,
        replace_output=model.replace_output,
        fresh=model.fresh,
        new_variant=model.new_variant,
    )


def application_overrides(explicit_fields: list[str]) -> InputOverrides:
    valid_fields = {item.name for item in fields(AudiobookRequest)}
    unknown = sorted(set(explicit_fields) - valid_fields)
    if unknown:
        raise InputValidationError(
            "Unknown explicit request fields: " + ", ".join(unknown)
        )
    if len(set(explicit_fields)) != len(explicit_fields):
        raise InputValidationError("Explicit request fields must be unique.")
    return InputOverrides(frozenset(explicit_fields))


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value is not None else None
