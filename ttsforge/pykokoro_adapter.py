"""TTSForge's PyKokoro 0.9 integration boundary."""

from __future__ import annotations

from typing import Any

from pykokoro import GenerationConfig, KokoroPipeline, PipelineConfig
from pykokoro.pipeline import build_pipeline


def build_standard_pipeline(
    *,
    voice: Any,
    generation: GenerationConfig,
    model_quality: Any = None,
    model_source: Any = None,
    model_variant: Any = None,
    model_path: Any = None,
    voices_path: Any = None,
    provider: str | None = None,
    tokenizer_config: Any = None,
    short_sentence_config: Any = None,
    ssmd: Any = None,
    prosody: Any = None,
) -> KokoroPipeline:
    """Build a normal pipeline with backend and stages owned by PyKokoro."""
    if not generation.lang:
        raise ValueError(
            "A document language is required before text preparation. "
            "Pass generation.lang=... or run(..., lang=...)."
        )
    values: dict[str, Any] = {
        "voice": voice,
        "generation": generation,
        "model_quality": model_quality,
        "model_source": model_source,
        "model_variant": model_variant,
        "model_path": model_path,
        "voices_path": voices_path,
        "provider": provider,
        "tokenizer_config": tokenizer_config,
        "short_sentence_config": short_sentence_config,
        "return_trace": True,
        "retain_segment_audio": False,
    }
    if ssmd is not None:
        values["ssmd"] = ssmd
    if prosody is not None:
        values["prosody"] = prosody
    return build_pipeline(config=PipelineConfig(**values), eager=True)
