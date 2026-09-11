"""Provider-aware CLI configuration helpers.

The module itself is safe to import without an ONNX Runtime provider. Backend
catalogues are loaded only when a command needs to render or download assets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
) -> str:
    """Resolve one canonical provider without importing ONNX Runtime."""
    if provider_override is not None:
        return _normalize_onnx_provider(provider_override)

    runtime = config.get("runtime") if config.get("schema_version") == 2 else config
    configured = runtime.get("provider") if isinstance(runtime, Mapping) else None
    if configured is None and isinstance(runtime, Mapping):
        configured = runtime.get("onnx_provider")
    if configured is not None and str(configured).strip():
        return _normalize_onnx_provider(configured)

    return "cpu"


@dataclass(frozen=True)
class ResolvedPipelineDefaults:
    """Concrete pipeline values resolved from PyKokoro metadata.

    Automatic (``None``) requests are filled with the values the PyKokoro
    runtime would use; explicit requests are preserved as supplied.
    """

    language: str
    model_source: str
    model_variant: str
    model_quality: str
    voice: str | None


def resolve_pykokoro_pipeline_defaults(
    *,
    ttsforge_language: str,
    voice: str | None = None,
    model_source: str | None = None,
    model_variant: str | None = None,
    model_quality: str | None = None,
    provider: str | None = None,
) -> ResolvedPipelineDefaults:
    """Resolve concrete pipeline defaults through the public PyKokoro API.

    Metadata-only: this never constructs an ONNX session or the synthesis
    pipeline, so preflight, status, and dry-run paths can share the exact
    default policy used by the runtime (``pykokoro.resolve_pipeline_config``).
    """
    from ..kokoro_lang import get_pykokoro_language
    from ..pykokoro_adapter import resolve_pipeline_config

    resolved = resolve_pipeline_config(
        language=get_pykokoro_language(ttsforge_language),
        voice=voice,
        model_source=model_source,
        model_variant=model_variant,
        model_quality=model_quality,
        provider=provider,
    )
    return ResolvedPipelineDefaults(
        language=resolved.generation.lang,
        model_source=resolved.model_source,
        model_variant=resolved.model_variant,
        model_quality=resolved.model_quality,
        voice=resolved.voice,
    )


def resolve_model_source_and_variant(
    config: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve explicit model choices without importing ONNX Runtime.

    Automatic values (both unset) stay ``None`` so callers resolve them
    through :func:`resolve_pykokoro_pipeline_defaults`.  Explicit variants
    are validated through the public resolver instead of private upstream
    model-profile modules.
    """
    if config.get("schema_version") == 2:
        model = config.get("model", {})
        raw_source = model.get("source") if isinstance(model, Mapping) else None
        raw_variant = model.get("id") if isinstance(model, Mapping) else None
    else:
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
        resolve_pykokoro_pipeline_defaults(
            ttsforge_language="a",
            model_source=source,
            model_variant=variant,
        )
    except ValueError as exc:
        raise ValueError(f"Unknown model profile: {source}/{variant}") from exc
    return source, variant


def resolve_model_source_variant_quality(
    config: Mapping[str, Any],
) -> tuple[str, str, str]:
    """Resolve concrete model source, variant, and quality.

    Automatic (``None``) values are filled through the public PyKokoro
    resolver so ``config --show`` and download/asset paths receive the same
    defaults the runtime uses.
    """
    raw_source, raw_variant = resolve_model_source_and_variant(config)
    if config.get("schema_version") == 2:
        model = config.get("model", {})
        raw_quality = model.get("quality") if isinstance(model, Mapping) else None
    else:
        raw_quality = config.get("model_quality")
    needs_automatic = raw_source is None or raw_variant is None or raw_quality is None
    if needs_automatic:
        resolved = resolve_pykokoro_pipeline_defaults(
            ttsforge_language=(
                config.get("tts", {}).get("language", "auto")
                if config.get("schema_version") == 2
                else config.get("default_language", "auto")
            ),
            model_source=raw_source,
            model_variant=raw_variant,
            model_quality=str(raw_quality) if raw_quality is not None else None,
        )
        source = raw_source or resolved.model_source
        variant = raw_variant or resolved.model_variant
        if raw_quality is not None:
            quality = str(raw_quality)
        else:
            quality = resolved.model_quality
    else:
        source = raw_source
        variant = raw_variant
        quality = str(raw_quality)
    return source, variant, quality


def resolve_voice_names(
    model_source: str | None = None, model_variant: str | None = None
) -> list[str]:
    """Return voices from PyKokoro's metadata-only model discovery."""
    from ..pykokoro_adapter import discover_models

    inventory = discover_models()
    voices: list[str] = []
    for model in inventory.models:
        if model_source is not None and model.source != model_source:
            continue
        if model_variant is not None and model.model_id != model_variant:
            continue
        voices.extend(model.voices)
    return list(dict.fromkeys(voices))


def resolve_voice_languages(
    model_source: str | None = None, model_variant: str | None = None
) -> dict[str, tuple[str, ...]]:
    """Return discovery-backed BCP-47 languages for each discovered voice."""
    from ..kokoro_lang import canonicalize_language
    from ..pykokoro_adapter import discover_models

    result: dict[str, set[str]] = {}
    for model in discover_models().models:
        if model_source is not None and model.source != model_source:
            continue
        if model_variant is not None and model.model_id != model_variant:
            continue
        languages = tuple(
            canonicalize_language(str(value)) for value in (model.languages or ())
        )
        for voice in model.voices:
            result.setdefault(voice, set()).update(languages)
    return {voice: tuple(sorted(languages)) for voice, languages in result.items()}
