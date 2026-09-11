"""TTSForge's PyKokoro 0.9 integration boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# PyKokoro imports are intentionally lazy. Configuration inspection and
# metadata-only resolution must not initialize ONNX Runtime.
if TYPE_CHECKING:
    from pykokoro import GenerationConfig, KokoroPipeline


_CONFIG_TYPE_NAMES = {
    "DEFAULT_MODEL_SOURCE",
    "DEFAULT_MODEL_VARIANT",
    "ModelQuality",
    "ModelSource",
    "ModelVariant",
}
_CORE_TYPE_NAMES = {
    "GenerationConfig",
    "KokoroPipeline",
    "PipelineConfig",
    "ProsodyConfig",
    "SSMDPauseOverrides",
    "SSMDRenderConfig",
}
_BACKEND_NAMES = {
    "DEFAULT_MODEL_QUALITY",
    "Kokoro",
    "VoiceBlend",
    "are_models_downloaded",
    "download_all_models",
    "download_all_models_github",
    "download_all_voices",
    "download_config",
    "download_model",
    "download_model_github",
    "download_voices_github",
    "is_config_downloaded",
}
_SHORT_SENTENCE_NAMES = {
    "SHORT_SENTENCE_META_KEY",
    "PhraseResolveMode",
    "RandomizedPhraseResolveMode",
    "ShortSentenceConfig",
    "WrapResolveMode",
}
_STAGE_NAMES = {
    "OnnxAudioGenerationAdapter": "pykokoro.stages.audio_generation.onnx",
    "OnnxAudioPostprocessingAdapter": "pykokoro.stages.audio_postprocessing.onnx",
    "OnnxPhonemeProcessorAdapter": "pykokoro.stages.phoneme_processing.onnx",
}


def __getattr__(name: str) -> Any:
    """Load a backend symbol only when a rendering or download path needs it."""
    if name in _CONFIG_TYPE_NAMES:
        from pykokoro import config_types

        value = getattr(config_types, name)
    elif name in _CORE_TYPE_NAMES:
        import pykokoro

        value = getattr(pykokoro, name)
    elif name in _BACKEND_NAMES:
        from pykokoro import onnx_backend

        value = getattr(onnx_backend, name)
    elif name in _SHORT_SENTENCE_NAMES:
        from pykokoro import short_sentence_handler

        value = getattr(short_sentence_handler, name)
    elif name in _STAGE_NAMES:
        import importlib

        value = getattr(importlib.import_module(_STAGE_NAMES[name]), name)
    elif name == "Tokenizer":
        from pykokoro.tokenizer import Tokenizer

        value = Tokenizer
    elif name == "TokenizerConfig":
        from pykokoro.tokenizer import TokenizerConfig

        value = TokenizerConfig
    elif name == "SSMDDocumentError":
        from pykokoro.exceptions import SSMDDocumentError

        value = SSMDDocumentError
    elif name == "parse_ssmd_document":
        from pykokoro.ssmd_parser import parse_ssmd_document

        value = parse_ssmd_document
    elif name == "build_pipeline":
        from pykokoro.pipeline import build_pipeline

        value = build_pipeline
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value


def get_model_asset_paths(*args: Any, **kwargs: Any) -> Any:
    """Return model assets through the PyKokoro asset API."""
    from pykokoro.model_assets import get_model_asset_paths as get

    return get(*args, **kwargs)


def resolve_pipeline_config(
    *,
    language: str,
    voice: Any = None,
    model_source: Any = None,
    model_variant: Any = None,
    model_quality: Any = None,
    provider: str | None = None,
) -> Any:
    """Resolve PyKokoro defaults without exposing its configuration types."""
    from pykokoro import GenerationConfig, PipelineConfig

    requested = PipelineConfig(
        generation=GenerationConfig(lang=language),
        voice=voice,
        model_source=model_source,
        model_variant=model_variant,
        model_quality=model_quality,
        provider=provider,
    )
    from pykokoro import resolve_pipeline_config as resolve

    return resolve(requested)


def discover_models() -> Any:
    """Return PyKokoro's metadata discovery result."""
    from pykokoro import discover_models as discover

    return discover()


def get_available_execution_providers() -> Any:
    """Return providers exposed by the installed ONNX Runtime."""
    from pykokoro.onnx_session import get_available_execution_providers as get

    return get()


def resolve_execution_provider(provider: str) -> str:
    """Resolve a provider alias using PyKokoro's runtime contract."""
    from pykokoro.onnx_session import resolve_execution_provider as resolve

    return resolve(provider)


def get_sound_device_player() -> Any:
    """Return PyKokoro's optional sound-device player class."""
    from pykokoro.playback import SoundDevicePlayer

    return SoundDevicePlayer


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
    from pykokoro import PipelineConfig
    from pykokoro.pipeline import build_pipeline

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
