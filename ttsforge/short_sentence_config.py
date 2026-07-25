"""Short-sentence configuration helpers for ttsforge."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from pykokoro.short_sentence_handler import (
    PhraseResolveMode,
    RandomizedPhraseResolveMode,
    ShortSentenceConfig,
    WrapResolveMode,
)

from .utils import atomic_write_json, get_user_config_path

DEFAULT_SHORT_SENTENCE = "mode=randomized,threshold=30,selection=auto,max-tries=5"
ADVANCED_CONFIG_FILENAME = "short_sentence_advanced.json"
MAX_SHORT_SENTENCE_THRESHOLD = 300

_MODE_ALIASES = {
    "off": "off",
    "false": "off",
    "disabled": "off",
    "disable": "off",
    "none": "off",
    "wrap": "wrap",
    "phrase": "phrase",
    "randomized": "randomized-phrase",
    "randomized-phrase": "randomized-phrase",
}

_KNOWN_OPTIONS = {
    "config",
    "mode",
    "threshold",
    "selection",
    "max-tries",
    "max_tries",
    "fallback-mode",
    "fallback_mode",
    "pretext",
    "natural-phrase",
    "natural_phrase",
    "end-phrase",
    "end_phrase",
    "natural-phrases",
    "natural_phrases",
    "end-phrases",
    "end_phrases",
    "frame-duration-ms",
    "frame_duration_ms",
    "energy-threshold",
    "energy_threshold",
    "silence-threshold",
    "silence_threshold",
    "min-silence-seconds",
    "min_silence_seconds",
    "cutter",
}


def get_advanced_short_sentence_config_path() -> Path:
    """Return the default advanced short-sentence JSON config path."""
    return get_user_config_path().with_name(ADVANCED_CONFIG_FILENAME)


def default_advanced_short_sentence_data() -> dict[str, Any]:
    """Build a complete advanced short-sentence JSON config with defaults."""
    phrase = PhraseResolveMode()
    randomized = RandomizedPhraseResolveMode()
    wrap = WrapResolveMode()
    default_lang_phrases = {
        "a": list(randomized.neutral_phrases),
        "b": list(randomized.neutral_phrases),
    }
    default_lang_end_phrases = {
        "a": list(randomized.end_phrases),
        "b": list(randomized.end_phrases),
    }
    return {
        "mode": "randomized",
        "threshold": 30,
        "selection": "auto",
        "max-tries": 5,
        "fallback-mode": "wrap",
        "pretext": wrap.phoneme_pretext,
        "natural-phrase": {
            "a": phrase.neutral_phrase,
            "b": phrase.neutral_phrase,
        },
        "end-phrase": {
            "a": phrase.end_phrase,
            "b": phrase.end_phrase,
        },
        "natural-phrases": default_lang_phrases,
        "end-phrases": default_lang_end_phrases,
        "cutter": randomized.cutter,
        "frame-duration-ms": randomized.frame_duration_ms,
        "energy-threshold": randomized.energy_threshold,
        "silence-threshold": randomized.silence_threshold,
        "min-silence-seconds": randomized.min_silence_seconds,
    }


def write_advanced_short_sentence_config(path: Path | None = None) -> Path:
    """Write the default advanced short-sentence JSON file and return its path."""
    target = path or get_advanced_short_sentence_config_path()
    atomic_write_json(
        target,
        default_advanced_short_sentence_data(),
        indent=2,
        ensure_ascii=False,
    )
    return target


def load_short_sentence_json_config(path: Path) -> dict[str, Any]:
    """Load a short-sentence JSON config object."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("short sentence config JSON must contain an object")
    return data


def resolve_short_sentence_config(
    value: str | None,
    *,
    language_code: str | None = None,
    warn: Callable[[str], None] | None = None,
    base_dir: Path | None = None,
) -> ShortSentenceConfig | None:
    """Resolve a ttsforge short-sentence option string into pykokoro config."""
    data = _resolve_short_sentence_data(value, warn=warn, base_dir=base_dir)
    return _build_short_sentence_config(data, language_code=language_code, warn=warn)


def validate_short_sentence_config(
    value: str | None,
    *,
    base_dir: Path | None = None,
) -> list[str]:
    """Return validation errors for a ttsforge short-sentence option string."""
    warnings: list[str] = []
    data = _resolve_short_sentence_data(
        value,
        warn=warnings.append,
        base_dir=base_dir,
    )

    errors = [
        warning
        for warning in warnings
        if warning.startswith("Failed to load short-sentence config")
    ]
    mode = str(data.get("mode", "randomized")).strip()
    if mode not in _MODE_ALIASES:
        valid_modes = ", ".join(("off", "wrap", "phrase", "randomized"))
        errors.append(
            f"Unknown short-sentence mode '{mode}'. Valid modes: {valid_modes}"
        )
    return errors


def short_sentence_fallback_note(
    value: str | None,
    *,
    language_code: str | None = None,
    base_dir: Path | None = None,
) -> str | None:
    """Return a user-facing note when phrase config falls back for a language."""
    data = _resolve_short_sentence_data(value, base_dir=base_dir)
    mode = _mode(data.get("mode", "randomized"))
    if mode in {"off", "wrap"}:
        return None

    selection = _selection(data.get("selection", "auto"))
    lang = _normalize_language_code(language_code)
    missing = _missing_phrase_options(data, mode, selection, lang)
    if not missing:
        return None

    fallback_mode = _fallback_mode(data.get("fallback-mode", "wrap"))
    fallback_text = "none" if fallback_mode is False else str(fallback_mode)
    return (
        f"Missing phrases for language '{lang}' ({', '.join(missing)}); "
        f"using fallback-mode={fallback_text}."
    )


def _resolve_short_sentence_data(
    value: str | None,
    *,
    warn: Callable[[str], None] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    option = value if value is not None and value.strip() else DEFAULT_SHORT_SENTENCE
    raw = _parse_short_sentence_option(option, warn=warn)
    overrides = _load_linked_config(raw, warn=warn, base_dir=base_dir)
    return _merge_short_sentence_defaults(overrides)


def _merge_short_sentence_defaults(overrides: dict[str, Any]) -> dict[str, Any]:
    merged = default_advanced_short_sentence_data()
    for key, value in overrides.items():
        if key == "config":
            continue
        normalized_key = _normalize_key(key)
        default_value = merged.get(normalized_key)
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged[normalized_key] = _deep_merge_dicts(default_value, value)
        else:
            merged[normalized_key] = value
    return merged


def _deep_merge_dicts(
    defaults: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        default_value = merged.get(key)
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(default_value, value)
        else:
            merged[key] = value
    return merged


def _warn(warn: Callable[[str], None] | None, message: str) -> None:
    if warn:
        warn(message)


def _parse_short_sentence_option(
    value: str,
    *,
    warn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    text = value.strip()
    if not text:
        return {}

    if text in _MODE_ALIASES:
        return {"mode": _MODE_ALIASES[text]}

    result: dict[str, Any] = {}
    reader = csv.reader([text], skipinitialspace=True)
    try:
        parts = next(reader)
    except csv.Error:
        parts = text.split(",")

    for index, part in enumerate(parts):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            if index == 0 and item in _MODE_ALIASES:
                result["mode"] = _MODE_ALIASES[item]
            else:
                _warn(warn, f"Unrecognized short-sentence option '{item}'")
            continue

        key, raw_value = item.split("=", 1)
        key = key.strip()
        normalized_key = _normalize_key(key)
        if normalized_key not in _KNOWN_OPTIONS:
            _warn(warn, f"Unrecognized short-sentence option '{key}'")
            continue
        result[normalized_key] = raw_value.strip()

    return result


def _load_linked_config(
    data: dict[str, Any],
    *,
    warn: Callable[[str], None] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    config_path = data.get("config")
    if not isinstance(config_path, str) or not config_path.strip():
        return data

    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
        if not path.exists() and base_dir is None:
            config_relative_path = get_user_config_path().parent / config_path
            if config_relative_path.exists():
                path = config_relative_path

    try:
        loaded = load_short_sentence_json_config(path)
    except Exception as exc:
        _warn(warn, f"Failed to load short-sentence config '{path}': {exc}")
        return {key: value for key, value in data.items() if key != "config"}

    merged = {key: value for key, value in data.items() if key != "config"}
    return {**loaded, **merged}


def _build_short_sentence_config(
    data: dict[str, Any],
    *,
    language_code: str | None = None,
    warn: Callable[[str], None] | None = None,
) -> ShortSentenceConfig | None:
    for key in data:
        if _normalize_key(key) not in _KNOWN_OPTIONS:
            _warn(warn, f"Unrecognized short-sentence option '{key}'")

    mode = _mode(data.get("mode", "randomized"), warn=warn)
    if mode == "off":
        return ShortSentenceConfig(enabled=False)

    threshold = _threshold_value(data, warn=warn)
    max_tries = _int_value(data, "max-tries", 5, warn=warn)
    selection = _selection(data.get("selection", "auto"), warn=warn)
    fallback_mode = _fallback_mode(data.get("fallback-mode", "wrap"), warn=warn)
    lang = _normalize_language_code(language_code)

    wrap = WrapResolveMode(phoneme_pretext=str(data.get("pretext", "\u2014")))
    phrase_defaults = PhraseResolveMode()
    randomized_defaults = RandomizedPhraseResolveMode()
    natural_phrase = _language_string(
        _lookup(data, "natural-phrase"),
        lang,
        warn=warn,
        option_name="natural-phrase",
    )
    end_phrase = _language_string(
        _lookup(data, "end-phrase"),
        lang,
        warn=warn,
        option_name="end-phrase",
    )
    natural_phrases = _language_string_list(
        _lookup(data, "natural-phrases"),
        lang,
        warn=warn,
        option_name="natural-phrases",
    )
    end_phrases = _language_string_list(
        _lookup(data, "end-phrases"),
        lang,
        warn=warn,
        option_name="end-phrases",
    )
    if _should_use_fallback_mode(
        mode,
        selection,
        natural_phrase=natural_phrase,
        end_phrase=end_phrase,
        natural_phrases=natural_phrases,
        end_phrases=end_phrases,
        has_natural_phrase=_has_option(data, "natural-phrase"),
        has_end_phrase=_has_option(data, "end-phrase"),
        has_natural_phrases=_has_option(data, "natural-phrases"),
        has_end_phrases=_has_option(data, "end-phrases"),
    ):
        mode = fallback_mode

    phrase = PhraseResolveMode(
        phrase_selection=cast(Any, selection),
        neutral_phrase=natural_phrase or phrase_defaults.neutral_phrase,
        end_phrase=end_phrase or phrase_defaults.end_phrase,
        frame_duration_ms=_int_value(
            data, "frame-duration-ms", phrase_defaults.frame_duration_ms, warn=warn
        ),
        energy_threshold=_float_value(
            data, "energy-threshold", phrase_defaults.energy_threshold, warn=warn
        ),
        silence_threshold=_float_value(
            data, "silence-threshold", phrase_defaults.silence_threshold, warn=warn
        ),
        min_silence_seconds=_float_value(
            data,
            "min-silence-seconds",
            phrase_defaults.min_silence_seconds,
            warn=warn,
        ),
        cutter=cast(Any, str(_lookup(data, "cutter") or phrase_defaults.cutter)),
    )
    randomized = RandomizedPhraseResolveMode(
        phrase_selection=cast(Any, selection),
        neutral_phrases=natural_phrases or randomized_defaults.neutral_phrases,
        end_phrases=end_phrases or randomized_defaults.end_phrases,
        frame_duration_ms=phrase.frame_duration_ms,
        energy_threshold=phrase.energy_threshold,
        silence_threshold=phrase.silence_threshold,
        min_silence_seconds=phrase.min_silence_seconds,
        cutter=phrase.cutter,
    )

    return ShortSentenceConfig(
        enabled=True,
        min_phoneme_length=threshold,
        phoneme_pretext=wrap.phoneme_pretext,
        resolve_mode=mode,
        resolve_modes={
            "wrap": wrap,
            "phrase": phrase,
            "randomized-phrase": randomized,
        },
        phrase_fallback_tries=max_tries,
    )


def _normalize_key(key: object) -> str:
    return str(key).strip().replace("_", "-")


def _mode(value: object, *, warn: Callable[[str], None] | None = None) -> str:
    text = str(value).strip()
    mode = _MODE_ALIASES.get(text)
    if mode is None:
        _warn(warn, f"Unknown short-sentence mode '{text}', using randomized")
        return "randomized-phrase"
    return mode


def _fallback_mode(
    value: object, *, warn: Callable[[str], None] | None = None
) -> str | Literal[False]:
    text = str(value).strip()
    if text in {"none", "off", "false", "disabled", "disable"}:
        return False
    if text == "wrap":
        return "wrap"
    _warn(warn, f"Unknown short-sentence fallback mode '{text}', using wrap")
    return "wrap"


def _selection(
    value: object, *, warn: Callable[[str], None] | None = None
) -> str:
    text = str(value).strip()
    if text == "natural":
        return "neutral"
    if text in {"auto", "neutral", "end"}:
        return text
    _warn(warn, f"Unknown short-sentence selection '{text}', using auto")
    return "auto"


def _lookup(data: dict[str, Any], key: str) -> Any:
    return data.get(key, data.get(key.replace("-", "_")))


def _has_option(data: dict[str, Any], key: str) -> bool:
    return key in data or key.replace("-", "_") in data


def _normalize_language_code(language_code: str | None) -> str:
    return (language_code or "a").strip().lower()


def _language_string(
    value: object,
    language_code: str,
    *,
    warn: Callable[[str], None] | None = None,
    option_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _warn(
            warn,
            f"Short-sentence '{option_name}' must be an object keyed by language",
        )
        return None
    selected = value.get(language_code)
    if selected is None:
        return None
    if isinstance(selected, str):
        return selected
    _warn(warn, f"Short-sentence '{option_name}.{language_code}' must be a string")
    return None


def _language_string_list(
    value: object,
    language_code: str,
    *,
    warn: Callable[[str], None] | None = None,
    option_name: str,
) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _warn(
            warn,
            f"Short-sentence '{option_name}' must be an object keyed by language",
        )
        return None
    selected = value.get(language_code)
    if selected is None:
        return None
    if isinstance(selected, list) and all(isinstance(item, str) for item in selected):
        return list(selected)
    _warn(
        warn,
        f"Short-sentence '{option_name}.{language_code}' must be an array of strings",
    )
    return None


def _should_use_fallback_mode(
    mode: str | Literal[False],
    selection: str,
    *,
    natural_phrase: str | None,
    end_phrase: str | None,
    natural_phrases: list[str] | None,
    end_phrases: list[str] | None,
    has_natural_phrase: bool,
    has_end_phrase: bool,
    has_natural_phrases: bool,
    has_end_phrases: bool,
) -> bool:
    if mode == "phrase":
        if selection == "neutral":
            return has_natural_phrase and natural_phrase is None
        if selection == "end":
            return has_end_phrase and end_phrase is None
        return (has_natural_phrase and natural_phrase is None) or (
            has_end_phrase and end_phrase is None
        )
    if mode == "randomized-phrase":
        if selection == "neutral":
            return has_natural_phrases and natural_phrases is None
        if selection == "end":
            return has_end_phrases and end_phrases is None
        return (has_natural_phrases and natural_phrases is None) or (
            has_end_phrases and end_phrases is None
        )
    return False


def _missing_phrase_options(
    data: dict[str, Any],
    mode: str | Literal[False],
    selection: str,
    language_code: str,
) -> list[str]:
    missing: list[str] = []
    if mode == "phrase":
        phrases = _lookup(data, "natural-phrase")
        end_phrases = _lookup(data, "end-phrase")
        if selection in {"auto", "neutral"} and not _has_language_value(
            phrases,
            language_code,
        ):
            missing.append("natural-phrase")
        if selection in {"auto", "end"} and not _has_language_value(
            end_phrases,
            language_code,
        ):
            missing.append("end-phrase")
    elif mode == "randomized-phrase":
        phrases = _lookup(data, "natural-phrases")
        end_phrases = _lookup(data, "end-phrases")
        if selection in {"auto", "neutral"} and not _has_language_value(
            phrases,
            language_code,
        ):
            missing.append("natural-phrases")
        if selection in {"auto", "end"} and not _has_language_value(
            end_phrases,
            language_code,
        ):
            missing.append("end-phrases")
    return missing


def _has_language_value(value: object, language_code: str) -> bool:
    if not isinstance(value, dict):
        return False
    selected = value.get(language_code)
    if isinstance(selected, str):
        return bool(selected)
    if isinstance(selected, list):
        return bool(selected) and all(isinstance(item, str) for item in selected)
    return False


def _int_value(
    data: dict[str, Any],
    key: str,
    default: int,
    *,
    warn: Callable[[str], None] | None = None,
) -> int:
    value = _lookup(data, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        _warn(warn, f"Invalid short-sentence integer for '{key}': {value}")
        return default


def _threshold_value(
    data: dict[str, Any],
    *,
    warn: Callable[[str], None] | None = None,
) -> int:
    threshold = _int_value(data, "threshold", 30, warn=warn)
    if threshold > MAX_SHORT_SENTENCE_THRESHOLD:
        _warn(
            warn,
            "Short-sentence threshold "
            f"{threshold} exceeds maximum {MAX_SHORT_SENTENCE_THRESHOLD}; "
            f"using {MAX_SHORT_SENTENCE_THRESHOLD}",
        )
        return MAX_SHORT_SENTENCE_THRESHOLD
    return threshold


def _float_value(
    data: dict[str, Any],
    key: str,
    default: float,
    *,
    warn: Callable[[str], None] | None = None,
) -> float:
    value = _lookup(data, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        _warn(warn, f"Invalid short-sentence number for '{key}': {value}")
        return default
