"""Canonical generation identities used by resumable TTSForge conversions.

This module deliberately does not import :mod:`ttsforge.conversion`.  The
identity builder accepts the validated options object structurally so state
loading and option construction can depend on it without introducing a
conversion-module import cycle.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeAlias, cast

from .prosody_support import prosody_policy_payload
from .render_units import (
    PARAGRAPH_OUTPUT_SCHEMA,
    PARAGRAPH_PAUSE_OWNERSHIP,
    renderer_contract_payload,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

GENERATION_IDENTITY_SCHEMA = 2


@dataclass(frozen=True, slots=True)
class GenerationIdentity:
    """The canonical payload and digest used to identify generated audio."""

    schema: int
    payload: dict[str, JsonValue]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class IdentityDifference:
    """One saved/current difference at a dotted payload path."""

    path: str
    saved: JsonValue
    current: JsonValue


def _canonicalize(value: object, *, path: str = "$") -> JsonValue:
    """Convert supported values to strict JSON-compatible values.

    The identity payload is an explicit contract.  Unknown values are errors;
    falling back to ``repr`` or ``str`` would make resume identity depend on
    implementation details or process-local object representations.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"identity value at {path} must be finite")
        return value
    if isinstance(value, Enum):
        return _canonicalize(value.value, path=path)
    if isinstance(value, Path):
        return _normalized_path(value)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"identity mapping key at {path} must be a string")
            result[key] = _canonicalize(item, path=f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _canonicalize(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, (set, frozenset)):
        raise TypeError(f"identity value at {path} cannot be a set")
    raise TypeError(
        f"unsupported identity value at {path}: {type(value).__name__}; "
        "use an explicit payload builder"
    )


def canonicalize_json(value: object) -> JsonValue:
    """Return a strict canonical-JSON-compatible representation."""
    return _canonicalize(value)


def canonical_json(value: Mapping[str, JsonValue]) -> str:
    """Serialize a payload using the identity's stable JSON contract."""
    normalized = _canonicalize(value)
    if not isinstance(normalized, dict):  # pragma: no cover - guarded by typing
        raise TypeError("generation identity payload must be a mapping")
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def generation_fingerprint(payload: Mapping[str, JsonValue]) -> str:
    """Hash a complete canonical generation payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _normalized_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def path_identity(
    path: Path | str | None,
    *,
    kind: str = "file",
    hash_content: bool = True,
    required: bool = False,
) -> dict[str, JsonValue] | None:
    """Return an intentional identity for a file or directory path.

    Logical default model selections pass ``None`` and therefore do not hash
    mutable cache files.  Explicit files can request validation and content
    hashing.  Directory policies record the normalized directory path only.
    """
    if path is None:
        return None
    resolved = Path(path).expanduser().resolve(strict=False)
    exists = resolved.exists()
    if kind == "file":
        if required and (not exists or not resolved.is_file()):
            raise ValueError(f"identity file does not exist or is not a file: {path}")
        digest: str | None = None
        if hash_content and resolved.is_file():
            digest_hash = hashlib.sha256()
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8192), b""):
                    digest_hash.update(chunk)
            digest = digest_hash.hexdigest()
        return {
            "path": str(resolved),
            "kind": "file",
            "exists": exists,
            "sha256": digest,
        }
    if kind == "directory":
        if required and (not exists or not resolved.is_dir()):
            raise ValueError(
                f"identity directory does not exist or is not a directory: {path}"
            )
        return {"path": str(resolved), "kind": "directory", "exists": exists}
    raise ValueError(f"unsupported path identity kind: {kind}")


def _attribute(value: object, name: str) -> Any:
    """Read a structural option/policy attribute without stringifying it."""
    return getattr(value, name)


def _policy_payload(
    policy: object, *, legacy_paths: bool = False
) -> dict[str, JsonValue]:
    """Build the SSMD policy payload without hashing directory contents."""
    pause = getattr(policy, "pause_overrides", None)
    pause_payload: dict[str, JsonValue] | None = None
    if pause is not None:
        pause_payload = {
            "enabled": _attribute(pause, "enabled"),
            "sentence": _attribute(pause, "sentence"),
            "paragraph": _attribute(pause, "paragraph"),
            "voice_change": _attribute(pause, "voice_change"),
        }
    bindings = {
        str(provider): {
            str(reference): str(target)
            for reference, target in sorted(provider_bindings.items())
        }
        for provider, provider_bindings in sorted(
            getattr(policy, "voice_bindings", {}).items()
        )
    }
    return {
        "parse_header": _attribute(policy, "parse_header"),
        "unknown_header": _attribute(policy, "unknown_header"),
        "missing_voice": _attribute(policy, "missing_voice"),
        "validate_profile": _attribute(policy, "validate_profile"),
        "emphasis_mode": _attribute(policy, "emphasis_mode"),
        "fail_on_warning": _attribute(policy, "fail_on_warning"),
        "voice_bindings": bindings,
        "pause_overrides": pause_payload,
        "audio_root": (
            _legacy_path_identity(_attribute(policy, "audio_root"))
            if legacy_paths
            else path_identity(
                _attribute(policy, "audio_root"),
                kind="directory",
                hash_content=False,
            )
        ),
        "allow_remote_audio": _attribute(policy, "allow_remote_audio"),
        "audio_timeout_s": _attribute(policy, "audio_timeout_s"),
        "audio_max_bytes": _attribute(policy, "audio_max_bytes"),
        "audio_max_duration_s": _attribute(policy, "audio_max_duration_s"),
        "renderer_contract": renderer_contract_payload(),
    }


def _common_generation_payload(
    options: object,
    *,
    resolved_sentence_models: Mapping[str, str],
    resolved_g2p_models: Mapping[str, str],
    legacy_paths: bool = False,
) -> dict[str, JsonValue]:
    """Build the explicit field list shared by current and legacy identity."""

    def file_value(value: Any, *, required: bool = False) -> JsonValue:
        if legacy_paths:
            return cast(JsonValue, _legacy_path_identity(value))
        return path_identity(value, required=required)

    text_options = _attribute(options, "text_postprocess_options")
    payload: dict[str, JsonValue] = {
        "voice": _attribute(options, "voice"),
        "voice_blend": _attribute(options, "voice_blend"),
        "voice_database": file_value(
            _attribute(options, "voice_database"), required=True
        ),
        "language": _attribute(options, "language"),
        "lang": _attribute(options, "lang"),
        "speed": _attribute(options, "speed"),
        "output_format": _attribute(options, "output_format"),
        "use_gpu": _attribute(options, "use_gpu"),
        "onnx_provider": _attribute(options, "effective_onnx_provider")(),
        "model_quality": str(_attribute(options, "model_quality")),
        "model_source": str(_attribute(options, "model_source")),
        "model_variant": str(_attribute(options, "model_variant")),
        "model_path": file_value(_attribute(options, "model_path"), required=True),
        "voices_path": file_value(_attribute(options, "voices_path"), required=True),
        "silence_between_chapters": _attribute(options, "silence_between_chapters"),
        "pause_clause": _attribute(options, "pause_clause"),
        "pause_sentence": _attribute(options, "pause_sentence"),
        "pause_paragraph": _attribute(options, "pause_paragraph"),
        "pause_variance": _attribute(options, "pause_variance"),
        "random_seed": _attribute(options, "random_seed"),
        "pause_mode": _attribute(options, "pause_mode"),
        "enable_short_sentence": _attribute(options, "enable_short_sentence"),
        "short_sentence": _attribute(options, "short_sentence"),
        "use_mixed_language": _attribute(options, "use_mixed_language"),
        "mixed_language_primary": _attribute(options, "mixed_language_primary"),
        "mixed_language_allowed": _attribute(options, "mixed_language_allowed"),
        "mixed_language_confidence": _attribute(options, "mixed_language_confidence"),
        "phoneme_dictionary": file_value(
            _attribute(options, "phoneme_dictionary_path"), required=True
        ),
        "phoneme_dict_case_sensitive": _attribute(
            options, "phoneme_dict_case_sensitive"
        ),
        "spacy": {
            "policy": "highest-installed-v1",
            "use_spacy": _attribute(options, "use_spacy"),
            "requested_model": _attribute(options, "spacy_model"),
            "requested_size": _attribute(options, "spacy_model_size"),
            "resolved_sentence_models": dict(sorted(resolved_sentence_models.items())),
            "resolved_g2p_models": dict(sorted(resolved_g2p_models.items())),
        },
        "announce_chapters": _attribute(options, "announce_chapters"),
        "chapter_pause_after_title": _attribute(options, "chapter_pause_after_title"),
        "split_mode": _attribute(options, "split_mode"),
        "conversion_unit": _attribute(options, "conversion_unit"),
        "paragraph_output_schema": PARAGRAPH_OUTPUT_SCHEMA,
        "paragraph_pause_ownership": PARAGRAPH_PAUSE_OWNERSHIP,
        "generate_ssmd_only": _attribute(options, "generate_ssmd_only"),
        "detect_emphasis": _attribute(options, "detect_emphasis"),
        "epub_content_mode": _attribute(options, "epub_content_mode"),
        "epub_heading_policy": "minimum_body_heading_level=2",
        "epub_scene_break_policy": "preserve",
        "text_postprocess_options": {
            "subchapter_markers": list(_attribute(text_options, "subchapter_markers"))
        },
        "ssmd_policy": _policy_payload(
            _attribute(options, "ssmd_policy"), legacy_paths=legacy_paths
        ),
        "prosody_policy": cast(
            JsonValue, prosody_policy_payload(_attribute(options, "prosody_policy"))
        ),
    }
    return payload


def build_generation_identity(
    options: object,
    *,
    resolved_sentence_models: Mapping[str, str],
    resolved_g2p_models: Mapping[str, str],
) -> GenerationIdentity:
    """Build the current strict generation identity for a conversion."""
    payload = canonicalize_json(
        _common_generation_payload(
            options,
            resolved_sentence_models=resolved_sentence_models,
            resolved_g2p_models=resolved_g2p_models,
        )
    )
    if not isinstance(payload, dict):  # pragma: no cover - builder invariant
        raise TypeError("generation identity payload must be a mapping")
    return GenerationIdentity(
        schema=GENERATION_IDENTITY_SCHEMA,
        payload=payload,
        fingerprint=generation_fingerprint(payload),
    )


def _legacy_path_identity(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    path = Path(value)
    digest = ""
    if path.is_file():
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8192), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()[:12]
    return {"path": str(path), "sha256": digest}


def build_generation_identity_v1_legacy(
    options: object,
    *,
    resolved_sentence_models: Mapping[str, str],
    resolved_g2p_models: Mapping[str, str],
) -> dict[str, JsonValue]:
    """Reproduce the pre-schema-2 payload used by version-6 state files."""
    return _common_generation_payload(
        options,
        resolved_sentence_models=resolved_sentence_models,
        resolved_g2p_models=resolved_g2p_models,
        legacy_paths=True,
    )


def generation_fingerprint_v1_legacy(payload: Mapping[str, JsonValue]) -> str:
    """Hash the legacy payload with the old stable JSON representation."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def diff_generation_identity(
    saved: Mapping[str, JsonValue], current: Mapping[str, JsonValue]
) -> tuple[IdentityDifference, ...]:
    """Return deterministic recursive differences using dotted paths."""
    differences: list[IdentityDifference] = []

    def walk(saved_value: JsonValue, current_value: JsonValue, path: str) -> None:
        if isinstance(saved_value, dict) and isinstance(current_value, dict):
            keys = sorted(set(saved_value) | set(current_value))
            for key in keys:
                child_path = f"{path}.{key}" if path else key
                walk(saved_value.get(key), current_value.get(key), child_path)
            return
        if isinstance(saved_value, list) and isinstance(current_value, list):
            for index in range(max(len(saved_value), len(current_value))):
                saved_item = saved_value[index] if index < len(saved_value) else None
                current_item = (
                    current_value[index] if index < len(current_value) else None
                )
                walk(saved_item, current_item, f"{path}[{index}]")
            return
        if saved_value != current_value:
            differences.append(
                IdentityDifference(path=path, saved=saved_value, current=current_value)
            )

    walk(dict(saved), dict(current), "")
    return tuple(differences)


def validate_saved_generation_identity(
    *,
    schema: int,
    payload: Mapping[str, JsonValue],
    fingerprint: str,
) -> bool:
    """Check that a persisted current identity is self-consistent."""
    if schema != GENERATION_IDENTITY_SCHEMA:
        return False
    try:
        return generation_fingerprint(payload) == fingerprint
    except (TypeError, ValueError):
        return False
