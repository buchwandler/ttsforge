"""TTSForge-owned views for concise backend catalog choices."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from .serialization import JsonValue, json_value


class EngineInfoRecord(Protocol):
    id: str
    version: str | None
    installed: bool
    runnable: bool
    features: tuple[str, ...]
    reason: str | None


class TargetInfoRecord(Protocol):
    id: str
    languages: tuple[str, ...]
    status: str
    runtime_available: bool
    default_voice: str | None
    voice_count: int
    qualities: tuple[str, ...]
    voice_mode: str | None
    sample_rate: int | None
    features: tuple[str, ...]
    reference_only: bool


class VoiceInfoRecord(Protocol):
    id: str
    language: str | None
    locale: str | None
    language_label: str | None
    gender: str
    default: bool
    runtime_available: bool


class EngineOptionInfoRecord(Protocol):
    name: str
    value_type: str | None
    required: bool
    default: object
    choices: tuple[object, ...]
    minimum: int | float | None
    maximum: int | float | None
    description: str
    identity_affecting: bool
    runtime_only: bool


@dataclass(frozen=True, slots=True)
class EngineChoiceView:
    id: str
    version: str | None
    installed: bool
    runnable: bool
    features: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TargetChoiceView:
    id: str
    languages: tuple[str, ...]
    status: str
    runtime_available: bool
    default_voice: str | None
    voice_count: int
    qualities: tuple[str, ...]
    voice_mode: str | None
    sample_rate: int | None
    features: tuple[str, ...]
    reference_only: bool


@dataclass(frozen=True, slots=True)
class VoiceChoiceView:
    id: str
    language: str | None
    locale: str | None
    language_label: str | None
    gender: str
    default: bool
    runtime_available: bool


@dataclass(frozen=True, slots=True)
class EngineOptionView:
    name: str
    value_type: str | None
    required: bool
    default: JsonValue
    choices: tuple[JsonValue, ...]
    minimum: int | float | None
    maximum: int | float | None
    description: str
    identity_affecting: bool
    runtime_only: bool


CatalogChoiceView: TypeAlias = EngineChoiceView | TargetChoiceView | VoiceChoiceView

_FEATURE_LABELS = {
    "named_voices": "voices",
    "lexicons": "lexicons",
    "model_sources": "model sources",
    "qualities": "qualities",
    "voice_level_calibration": "voice level",
    "reference_voice": "reference audio",
    "prepared_voice": "prepared voices",
    "speakers": "speakers",
    "request_measurement": "request measurement",
}


def _feature_labels(features: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_FEATURE_LABELS.get(feature, feature) for feature in features)


def engine_choice_view(engine: EngineInfoRecord) -> EngineChoiceView:
    return EngineChoiceView(
        id=engine.id,
        version=engine.version,
        installed=engine.installed,
        runnable=engine.runnable,
        features=_feature_labels(engine.features),
        reason=engine.reason,
    )


def target_choice_view(target: TargetInfoRecord) -> TargetChoiceView:
    return TargetChoiceView(
        id=target.id,
        languages=target.languages,
        status=target.status,
        runtime_available=target.runtime_available,
        default_voice=target.default_voice,
        voice_count=target.voice_count,
        qualities=target.qualities,
        voice_mode=target.voice_mode,
        sample_rate=target.sample_rate,
        features=_feature_labels(target.features),
        reference_only=target.reference_only,
    )


def voice_choice_view(voice: VoiceInfoRecord) -> VoiceChoiceView:
    return VoiceChoiceView(
        id=voice.id,
        language=voice.language,
        locale=voice.locale,
        language_label=voice.language_label,
        gender=voice.gender,
        default=voice.default,
        runtime_available=voice.runtime_available,
    )


def inspected_voice_choice_view(voice: object) -> VoiceChoiceView | None:
    """Project the legacy inspect_voice result, which is not a catalog DTO."""
    if isinstance(voice, Mapping):
        identifier = voice.get("id") or voice.get("voice")
        language = voice.get("language")
        locale = voice.get("locale")
        language_label = voice.get("language_label")
        gender = voice.get("gender", "unknown")
        default = voice.get("default", False)
        runtime_available = voice.get("runtime_available", voice.get("installed", True))
    else:
        identifier = getattr(voice, "id", None) or getattr(voice, "voice", None)
        language = getattr(voice, "language", None)
        locale = getattr(voice, "locale", None)
        language_label = getattr(voice, "language_label", None)
        gender = getattr(voice, "gender", "unknown")
        default = getattr(voice, "default", False)
        runtime_available = getattr(
            voice, "runtime_available", getattr(voice, "installed", True)
        )
    if not isinstance(identifier, str) or not identifier:
        return None
    return VoiceChoiceView(
        id=identifier,
        language=language if isinstance(language, str) else None,
        locale=locale if isinstance(locale, str) else None,
        language_label=language_label if isinstance(language_label, str) else None,
        gender=gender if isinstance(gender, str) and gender else "unknown",
        default=bool(default),
        runtime_available=bool(runtime_available),
    )


def engine_option_view(option: EngineOptionInfoRecord) -> EngineOptionView:
    return EngineOptionView(
        name=option.name,
        value_type=option.value_type,
        required=option.required,
        default=json_value(option.default),
        choices=tuple(json_value(choice) for choice in option.choices),
        minimum=option.minimum,
        maximum=option.maximum,
        description=option.description,
        identity_affecting=option.identity_affecting,
        runtime_only=option.runtime_only,
    )
