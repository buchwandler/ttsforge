"""Provider-aware CLI configuration helpers.

The module itself is safe to import without an ONNX Runtime provider. Backend
catalogues are loaded only when a command needs to render or download assets.
"""

from __future__ import annotations

from typing import Any

from ..constants import DEFAULT_MODEL_SOURCE, VOICES

DEFAULT_MODEL_VARIANT = "v1.0"


def resolve_model_source_and_variant(config: dict[str, Any]) -> tuple[str, str]:
    source = str(config.get("model_source", DEFAULT_MODEL_SOURCE))
    variant = str(config.get("model_variant", DEFAULT_MODEL_VARIANT))
    if source not in {"huggingface", "github"}:
        source = DEFAULT_MODEL_SOURCE
    if variant not in {"v1.0", "v1.1-zh", "v1.1-de"}:
        variant = DEFAULT_MODEL_VARIANT
    return source, variant


def resolve_voice_names(
    model_source: str = "huggingface", model_variant: str = "v1.0"
) -> list[str]:
    # The v1.0 catalogue is sufficient to construct Click options without
    # importing the backend. Runtime commands validate provider-specific names.
    return list(VOICES)
