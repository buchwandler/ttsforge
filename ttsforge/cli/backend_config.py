"""Provider-aware CLI configuration helpers.

The module itself is safe to import without an ONNX Runtime provider. Backend
catalogues are loaded only when a command needs to render or download assets.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..utils import validate_config_value

DEFAULT_MODEL_VARIANT = None


def _normalize_onnx_provider(value: Any) -> str:
    """Normalize and validate a provider before handing it to PyKokoro."""
    if not isinstance(value, str):
        raise TypeError("Invalid ONNX provider: expected a non-empty string")

    provider = value.strip()
    try:
        validate_config_value("onnx_provider", provider)
    except ValueError as exc:
        raise ValueError(f"Invalid ONNX provider {value!r}: {exc}") from exc
    return provider


def resolve_onnx_provider(
    config: Mapping[str, Any],
    *,
    provider_override: str | None,
    use_gpu_override: bool | None,
) -> str:
    """Resolve CLI and config provider inputs without importing ONNX Runtime."""
    if provider_override is not None and use_gpu_override is not None:
        raise ValueError("--provider cannot be combined with --gpu or --no-gpu")

    if provider_override is not None:
        return _normalize_onnx_provider(provider_override)

    if use_gpu_override is not None:
        return "auto" if use_gpu_override else "cpu"

    configured = config.get("onnx_provider")
    if configured is not None and str(configured).strip():
        return _normalize_onnx_provider(configured)

    return "auto" if bool(config.get("use_gpu", False)) else "cpu"


def resolve_model_source_and_variant(
    config: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve explicit model choices without importing ONNX Runtime."""
    raw_source = config.get("model_source")
    raw_variant = config.get("model_variant")
    if raw_source is None and raw_variant is None:
        return None, None
    source = str(raw_source) if raw_source is not None else "github"
    variant = str(raw_variant) if raw_variant is not None else None
    if source not in {"huggingface", "github"}:
        raise ValueError(f"Unknown model source: {source!r}")
    if variant is None:
        return source, None
    try:
        from pykokoro.model_profiles import get_model_profile

        get_model_profile(variant, source)
    except (ImportError, ValueError) as exc:
        raise ValueError(f"Unknown model profile: {source}/{variant}") from exc
    return source, variant


def resolve_voice_names(
    model_source: str | None = None, model_variant: str | None = None
) -> list[str]:
    """Return voices from PyKokoro's metadata-only model discovery."""
    from pykokoro import discover_models

    inventory = discover_models()
    voices: list[str] = []
    for model in inventory.models:
        if model_source is not None and model.source != model_source:
            continue
        if model_variant is not None and model.model_id != model_variant:
            continue
        voices.extend(model.voices)
    return list(dict.fromkeys(voices))
