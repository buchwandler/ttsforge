"""
ttsforge - Generate audiobooks from EPUB files with TTS.

A CLI tool for converting EPUB books to audiobooks using Kokoro ONNX TTS.
"""

from .constants import DEFAULT_CONFIG, SUPPORTED_OUTPUT_FORMATS
from .conversion_plan import ConversionPlan, ConversionRequest
from .utils import (
    load_config,
    save_config,
)
from .prosody_support import ProsodyPolicy
from .cli.helpers import DEFAULT_SAMPLE_TEXT

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "Chapter": ("ttsforge.conversion", "Chapter"),
    "ConversionOptions": ("ttsforge.conversion", "ConversionOptions"),
    "RuntimeOptions": ("ttsforge.conversion", "RuntimeOptions"),
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
    """Load TTSForge-owned lazy exports on demand."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_SAMPLE_TEXT",
    "FORMAT_VERSION",
    "SUPPORTED_OUTPUT_FORMATS",
    "Chapter",
    "ConversionOptions",
    "ConversionPlan",
    "ConversionProgress",
    "ConversionRequest",
    "ConversionResult",
    "PhonemeBook",
    "PhonemeChapter",
    "PhonemeSegment",
    "ProsodyPolicy",
    "RuntimeOptions",
    "TTSConverter",
    "create_phoneme_book_from_chapters",
    "load_config",
    "phonemize_text_list",
    "save_config",
]

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"
