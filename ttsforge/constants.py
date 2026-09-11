"""Constants for ttsforge - voices, languages, and formats."""

# Keep these values local so importing configuration and CLI metadata does not
# import pykokoro's ONNX backend (and therefore does not require a provider).
DEFAULT_MODEL_SOURCE = "huggingface"
SAMPLE_RATE = 24000

# pykokoro's v1.0 voice catalogue is data, not backend functionality. Keeping
# the catalogue here keeps CLI option construction and lightweight help
# provider-independent.

# Program Information
PROGRAM_NAME = "ttsforge"
PROGRAM_DESCRIPTION = "Generate audiobooks from EPUB files using Kokoro ONNX TTS."

# Language code to description mapping
LANGUAGE_DESCRIPTIONS = {
    "en-us": "American English",
    "en-gb": "British English",
    "de": "German",
    "es": "Spanish",
    "fr-fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "pt-br": "Brazilian Portuguese",
    "zh": "Mandarin Chinese",
}

# ISO language code to ttsforge language code mapping

# Voice prefix to language code mapping


# Supported output audio formats
SUPPORTED_OUTPUT_FORMATS = [
    "wav",
    "mp3",
    "flac",
    "opus",
    "m4b",
]

# Formats that require ffmpeg
FFMPEG_FORMATS = ["m4b", "opus"]

# Formats supported by soundfile directly
SOUNDFILE_FORMATS = ["wav", "mp3", "flac"]

# Default configuration values
# None lets PyKokoro 0.9 resolve a language-aware voice profile.
DEFAULT_CONFIG = {
    "default_voice": None,
    "default_language": "auto",
    "default_speed": 1.0,
    "default_format": "m4b",
    "onnx_provider": "cpu",
    # spaCy policy: unset model and tier select the highest installed compatible
    # local model through the released phrasplit/PyKokoro APIs.
    "use_spacy": None,
    "spacy_model": None,
    "spacy_model_size": None,
    # Model quality: fp32, fp16, q8, q8f16, q4, q4f16, uint8, uint8f16
    "model_quality": None,
    "model_source": None,
    "model_variant": None,
    "silence_between_chapters": 2.0,
    "save_chapters_separately": False,
    "merge_at_end": True,
    "default_split_mode": "auto",
    "default_content_mode": "chapters",  # Content mode for read: chapters or pages
    "default_page_size": 2000,  # Synthetic page size in characters for pages mode
    "pause_clause": 0.3,
    "pause_sentence": 0.5,
    "pause_paragraph": 0.9,
    "pause_variance": 0.05,
    "pause_mode": "auto",  # "tts", "manual", or "auto
    "enable_short_sentence": None,
    "subchapter_markers": [],
    "short_sentence": "mode=randomized,threshold=30,selection=auto,max-tries=5",
    # Language override for phonemization (e.g., 'de', 'fr', 'en-us')
    # Chapter announcement settings
    "announce_chapters": True,  # Read chapter titles aloud before content
    "chapter_pause_after_title": 2.0,  # Pause after chapter title (seconds)
    "output_filename_template": "{book_title}",
    "chapter_filename_template": "{chapter_num:03d}_{book_title}_{chapter_title}",
    "phoneme_export_template": "{book_title}",
    # Fallback title when metadata is missing
    "default_title": "Untitled",
    # Mixed-language changes are represented by explicit SSMD lang spans.
    # SSMD 0.8 rendering policies.  Pause values above remain pipeline
    # defaults; they are intentionally not implicit SSMD header overrides.
    "ssmd_parse_header": True,
    "ssmd_unknown_header": "warn",
    "ssmd_missing_voice": "error",
    "ssmd_validate_profile": True,
    "ssmd_emphasis_mode": "plain",
    # None means the friendly level is not configured; use the legacy policy.
    "emphasis_level": None,
    "detect_emphasis": True,
    "epub_content_mode": "markdown",
    "prosody_method": "wsola",
    "prosody_fallback_methods": ["wsola", "phase_vocoder"],
    "prosody_strict": False,
    "prosody_clip": False,
    "prosody_n_fft": 2048,
    "prosody_hop_length": None,
    "prosody_filter_width": 32,
    "prosody_rolloff": 0.945,
    "prosody_boundary_blend_ms": 5.0,
    "ssmd_fail_on_warning": False,
    "ssmd_voice_bindings": {},
    "ssmd_audio_allow_remote": False,
    "ssmd_audio_max_bytes": 20_000_000,
    "ssmd_audio_max_duration_s": 120.0,
    "ssmd_audio_root": None,
    "embed_ssmd_voice_bindings": False,
    "embed_ssmd_pause_defaults": False,
}

