"""HTTP request models kept separate from application dataclasses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceInspectRequest(StrictModel):
    path: str


class AudiobookRequestModel(StrictModel):
    source: str
    project: str | None = None
    chapters: str | None = None
    output: str | None = None
    language: str | None = None
    engine: str | None = None
    target: str | None = None
    voice: str | None = None
    engine_options: dict[str, JsonValue] = Field(default_factory=dict)
    speed: float | None = None
    spacy: Literal["off", "auto", "sm", "md", "lg", "trf"] | None = None
    speech_profile: str | None = None
    pause_timing: Literal["fixed", "natural", "engaging"] | None = None
    bitrate: str | int | None = None
    target_lufs: float | None = None
    title: str | None = None
    author: str | None = None
    cover: str | None = None
    offline: bool = False
    refresh: bool = False
    rebuild_from: str | None = None
    replace_output: bool = False
    fresh: bool = False
    new_variant: bool = False


class JobSubmissionModel(StrictModel):
    request: AudiobookRequestModel
    explicit_fields: list[str] = Field(default_factory=list)


class SpacyEnsureRequest(StrictModel):
    language: str
    tier: Literal["sm", "md", "lg", "trf"]
    offline: bool = False
