"""
ttsforge - Generate audiobooks from EPUB files with TTS.

A CLI tool for converting EPUB books to audiobooks using Kokoro ONNX TTS.
"""

from .constants import (
    DEFAULT_CONFIG,
    LANGUAGE_DESCRIPTIONS,
    SUPPORTED_OUTPUT_FORMATS,
    VOICES,
)
from .utils import (
    load_config,
    save_config,
)
from .prosody_support import ProsodyPolicy
from .cli.helpers import DEFAULT_SAMPLE_TEXT

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "GenerationConfig": ("pykokoro", "GenerationConfig"),
    "KokoroPipeline": ("pykokoro", "KokoroPipeline"),
    "PipelineConfig": ("pykokoro", "PipelineConfig"),
    "VoiceBlend": ("pykokoro.onnx_backend", "VoiceBlend"),
    "are_models_downloaded": ("pykokoro.onnx_backend", "are_models_downloaded"),
    "download_all_models": ("pykokoro.onnx_backend", "download_all_models"),
    "download_model": ("pykokoro.onnx_backend", "download_model"),
    "get_model_dir": ("pykokoro.onnx_backend", "get_model_dir"),
    "EspeakConfig": ("pykokoro.tokenizer", "EspeakConfig"),
    "MAX_PHONEME_LENGTH": ("pykokoro.tokenizer", "MAX_PHONEME_LENGTH"),
    "Tokenizer": ("pykokoro.tokenizer", "Tokenizer"),
    "SUPPORTED_LANGUAGES": ("pykokoro.constants", "SUPPORTED_LANGUAGES"),
    "VOICE_NAMES_BY_VARIANT": ("pykokoro.onnx_backend", "VOICE_NAMES_BY_VARIANT"),
    "SAMPLE_RATE": ("ttsforge.constants", "SAMPLE_RATE"),
    "Chapter": ("ttsforge.conversion", "Chapter"),
    "ConversionOptions": ("ttsforge.conversion", "ConversionOptions"),
    "ConversionProgress": ("ttsforge.conversion", "ConversionProgress"),
    "ConversionResult": ("ttsforge.conversion", "ConversionResult"),
    "TTSConverter": ("ttsforge.conversion", "TTSConverter"),
    "FORMAT_VERSION": ("ttsforge.phonemes", "FORMAT_VERSION"),
    "PhonemeBook": ("ttsforge.phonemes", "PhonemeBook"),
    "PhonemeChapter": ("ttsforge.phonemes", "PhonemeChapter"),
    "PhonemeSegment": ("ttsforge.phonemes", "PhonemeSegment"),
    "create_phoneme_book_from_chapters": (
        "ttsforge.phonemes",
        "create_phoneme_book_from_chapters",
    ),
    "phonemize_text_list": ("ttsforge.phonemes", "phonemize_text_list"),
}


def __getattr__(name: str) -> Any:
    """Load backend-dependent compatibility exports only when requested."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    # Constants
    "DEFAULT_CONFIG",
    "LANGUAGE_DESCRIPTIONS",
    "SUPPORTED_OUTPUT_FORMATS",
    "VOICES",
    "VOICE_NAMES_BY_VARIANT",
    # Conversion
    "Chapter",
    "ConversionOptions",
    "ConversionProgress",
    "ConversionResult",
    "TTSConverter",
    # Pipeline (from pykokoro)
    "GenerationConfig",
    "KokoroPipeline",
    "PipelineConfig",
    "VoiceBlend",
    "are_models_downloaded",
    "download_all_models",
    "download_model",
    "get_model_dir",
    # Tokenizer (from pykokoro)
    "EspeakConfig",
    "MAX_PHONEME_LENGTH",
    "SAMPLE_RATE",
    "SUPPORTED_LANGUAGES",
    "Tokenizer",
    # Phonemes
    "FORMAT_VERSION",
    "PhonemeBook",
    "PhonemeChapter",
    "PhonemeSegment",
    "create_phoneme_book_from_chapters",
    "phonemize_text_list",
    # Utils
    "load_config",
    "save_config",
    "ProsodyPolicy",
    # herlpers
    "DEFAULT_SAMPLE_TEXT",
]

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"
