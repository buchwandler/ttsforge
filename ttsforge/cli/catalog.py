"""TTSForge-owned views for concise backend catalog choices."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias


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


CatalogChoiceView: TypeAlias = EngineChoiceView | TargetChoiceView | VoiceChoiceView

_ENGINE_FEATURES = (
    ("supports_named_voices", "voices"),
    ("supports_lexicons", "lexicons"),
    ("supports_model_sources", "model sources"),
    ("supports_qualities", "qualities"),
    ("supports_voice_level_calibration", "voice level"),
    ("reference_audio", "reference audio"),
)
_FEATURE_LABELS = {
    "named_voices": "voices",
    "lexicons": "lexicons",
    "model_sources": "model sources",
    "qualities": "qualities",
    "voice_level_calibration": "voice level",
    "pronunciation_overrides": "pronunciation overrides",
    "reference_voice": "reference audio",
    "prepared_voice": "prepared voices",
    "speakers": "speakers",
    "request_measurement": "request measurement",
}


def _value(record: object, key: str, default: object = None) -> object:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def _metadata(record: object) -> Mapping[str, object]:
    value = _value(record, "metadata")
    return value if isinstance(value, Mapping) else {}


def _capability_names(record: object) -> tuple[str, ...]:
    capabilities = _value(record, "capabilities")
    if isinstance(capabilities, Mapping):
        return tuple(key for key, enabled in capabilities.items() if enabled)
    return _strings(capabilities)


def engine_choice_view(engine: object) -> EngineChoiceView:
    identifier = _value(engine, "id")
    if not isinstance(identifier, str):
        identifier = str(identifier)
    installed_value = _value(engine, "installed", True)
    installed = bool(installed_value)
    version_value = _value(engine, "installed_version") or _value(engine, "version")
    version = version_value if isinstance(version_value, str) else None
    features = [
        label for key, label in _ENGINE_FEATURES if bool(_value(engine, key, False))
    ]
    features.extend(
        _FEATURE_LABELS.get(name, name.replace("_", " "))
        for name in _capability_names(engine)
        if _FEATURE_LABELS.get(name, name.replace("_", " ")) not in features
    )
    reason_value = _value(engine, "missing_dependency")
    reason = reason_value if isinstance(reason_value, str) else None
    return EngineChoiceView(
        id=identifier,
        version=version,
        installed=installed,
        runnable=bool(_value(engine, "runnable", installed)),
        features=tuple(features),
        reason=reason,
    )


def _target_language_labels(target: object) -> dict[str, str]:
    labels: dict[str, str] = {}
    details = _value(target, "voice_details", ())
    if not isinstance(details, Sequence) or isinstance(details, str):
        return labels
    for detail in details:
        label = _value(detail, "language_label")
        if not isinstance(label, str) or not label:
            continue
        for code in (
            _value(detail, "language"),
            _value(detail, "locale"),
            *_strings(_value(detail, "languages")),
        ):
            if isinstance(code, str) and code:
                labels[code.casefold()] = label
    return labels


def target_choice_view(target: object) -> TargetChoiceView:
    identifier = _value(target, "id")
    if not isinstance(identifier, str):
        identifier = str(identifier)
    languages = _strings(_value(target, "languages"))
    if not languages:
        languages = _strings(_value(target, "language"))
    labels = _target_language_labels(target)
    languages = tuple(
        labels.get(language.casefold(), language) for language in languages
    )
    voices = _strings(_value(target, "voices"))
    speakers = _strings(_value(target, "speakers"))
    default_voice = _value(target, "default_voice")
    if not isinstance(default_voice, str):
        default_voice = None
    capabilities = _capability_names(target)
    metadata = _metadata(target)
    requires_reference = (
        "reference_voice" in capabilities
        or bool(metadata.get("supports_reference_enrollment"))
        or bool(metadata.get("supports_voice_enrollment"))
    )
    reference_only = (
        requires_reference and not voices and not speakers and default_voice is None
    )
    status_value = _value(target, "status", "ready")
    sample_rate_value = _value(target, "sample_rate")
    sample_rate = (
        sample_rate_value
        if isinstance(sample_rate_value, int)
        and not isinstance(sample_rate_value, bool)
        else None
    )
    voice_mode_value = metadata.get("voice_mode")
    voice_mode = voice_mode_value if isinstance(voice_mode_value, str) else None
    features = tuple(
        _FEATURE_LABELS.get(name, name.replace("_", " ")) for name in capabilities
    )
    return TargetChoiceView(
        id=identifier,
        languages=languages,
        status=status_value if isinstance(status_value, str) else str(status_value),
        runtime_available=bool(_value(target, "runtime_available", True)),
        default_voice=default_voice,
        voice_count=len(voices) or len(speakers),
        qualities=_strings(_value(target, "qualities")),
        voice_mode=voice_mode,
        sample_rate=sample_rate,
        features=features,
        reference_only=reference_only,
    )


def voice_choice_view(
    voice: object,
    *,
    default_voice: str | None = None,
) -> VoiceChoiceView:
    identifier = (
        _value(voice, "id") or _value(voice, "voice") or _value(voice, "speaker")
    )
    if not isinstance(identifier, str):
        identifier = _value(voice, "selector")
    if not isinstance(identifier, str):
        identifier = str(identifier)
    languages = _strings(_value(voice, "languages"))
    language_value = _value(voice, "language")
    language = language_value if isinstance(language_value, str) else None
    if language is None and languages:
        language = languages[0]
    metadata = _metadata(voice)
    voice_metadata = metadata.get("voice")
    if not isinstance(voice_metadata, Mapping):
        voice_metadata = {}
    language_label_value = _value(voice, "language_label") or voice_metadata.get(
        "language_label"
    )
    language_label = (
        language_label_value if isinstance(language_label_value, str) else None
    )
    locale_value = _value(voice, "locale")
    locale = locale_value if isinstance(locale_value, str) else None
    gender_value = _value(voice, "gender")
    gender = (
        gender_value if isinstance(gender_value, str) and gender_value else "unknown"
    )
    installed = _value(voice, "installed", True)
    runtime_available = bool(_value(voice, "runtime_available", installed))
    return VoiceChoiceView(
        id=identifier,
        language=language,
        locale=locale,
        language_label=language_label,
        gender=gender,
        default=identifier == default_voice or _value(voice, "voice") == default_voice,
        runtime_available=runtime_available,
    )
