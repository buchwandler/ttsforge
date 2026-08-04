"""Constants for ttsforge - voices, languages, and formats."""

# Keep these values local so importing configuration and CLI metadata does not
# import pykokoro's ONNX backend (and therefore does not require a provider).
DEFAULT_MODEL_SOURCE = "huggingface"
SAMPLE_RATE = 24000

# pykokoro's v1.0 voice catalogue is data, not backend functionality. Keeping
# the catalogue here keeps CLI option construction and lightweight help
# provider-independent.
VOICES = [
    "af",
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
    "ef_dora",
    "em_alex",
    "em_santa",
    "ff_siwis",
    "hf_alpha",
    "hf_beta",
    "hm_omega",
    "hm_psi",
    "if_sara",
    "im_nicola",
    "jf_alpha",
    "jf_gongitsune",
    "jf_nezumi",
    "jf_tebukuro",
    "jm_kumo",
    "pf_dora",
    "pm_alex",
    "pm_santa",
    "zf_xiaobei",
    "zf_xiaoni",
    "zf_xiaoxiao",
    "zm_yunjian",
    "zm_yunxi",
    "zm_yunxia",
    "zm_yunyang",
]

# Program Information
PROGRAM_NAME = "ttsforge"
PROGRAM_DESCRIPTION = "Generate audiobooks from EPUB files using Kokoro ONNX TTS."

# Language code to description mapping
LANGUAGE_DESCRIPTIONS = {
    "a": "American English",
    "b": "British English",
    "d": "German",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "j": "Japanese",
    "p": "Brazilian Portuguese",
    "z": "Mandarin Chinese",
}

# ISO language code to ttsforge language code mapping
ISO_TO_LANG_CODE = {
    "de": "d",
    "de-de": "d",
    "en": "a",  # Default to American English
    "en-us": "a",
    "en-gb": "b",
    "en-au": "b",
    "es": "e",
    "es-es": "e",
    "es-mx": "e",
    "fr": "f",
    "fr-fr": "f",
    "fr-ca": "f",
    "hi": "h",
    "it": "i",
    "ja": "j",
    "pt": "p",
    "pt-br": "p",
    "pt-pt": "p",
    "zh": "z",
    "zh-cn": "z",
    "zh-tw": "z",
}

# Voice prefix to language code mapping
VOICE_PREFIX_TO_LANG = {
    "af": "a",  # American Female
    "am": "a",  # American Male
    "bf": "b",  # British Female
    "bm": "b",  # British Male
    "df": "d",  # German Female
    "dm": "d",  # German Male
    "ef": "e",  # Spanish Female
    "em": "e",  # Spanish Male
    "ff": "f",  # French Female
    "fm": "f",  # French Male
    "hf": "h",  # Hindi Female
    "hm": "h",  # Hindi Male
    "if": "i",  # Italian Female
    "im": "i",  # Italian Male
    "jf": "j",  # Japanese Female
    "jm": "j",  # Japanese Male
    "pf": "p",  # Portuguese Female
    "pm": "p",  # Portuguese Male
    "zf": "z",  # Chinese Female
    "zm": "z",  # Chinese Male
}

# Language code to default voice mapping
DEFAULT_VOICE_FOR_LANG = {
    "a": "af_heart",
    "b": "bf_emma",
    "d": "df_eva",
    "e": "ef_dora",
    "f": "ff_siwis",
    "h": "hf_alpha",
    "i": "if_sara",
    "j": "jf_alpha",
    "p": "pf_dora",
    "z": "zf_xiaoxiao",
}

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
DEFAULT_CONFIG = {
    "default_voice": "af_heart",
    "default_language": "a",
    "default_speed": 1.0,
    "default_format": "m4b",
    "onnx_provider": "cpu",
    "use_gpu": False,  # Legacy compatibility key; use onnx_provider instead.
    # spaCy policy: unset model and tier select the highest installed compatible
    # local model through the released phrasplit/PyKokoro APIs.
    "use_spacy": True,
    "spacy_model": None,
    "spacy_model_size": None,
    # Model quality: fp32, fp16, q8, q8f16, q4, q4f16, uint8, uint8f16
    "model_quality": "fp32",
    "model_source": DEFAULT_MODEL_SOURCE,
    "model_variant": "v1.0",
    "silence_between_chapters": 2.0,
    "save_chapters_separately": False,
    "merge_at_end": True,
    "auto_detect_language": True,
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
    # If None, language is determined from voice prefix
    "phonemization_lang": None,
    # Chapter announcement settings
    "announce_chapters": True,  # Read chapter titles aloud before content
    "chapter_pause_after_title": 2.0,  # Pause after chapter title (seconds)
    "output_filename_template": "{book_title}",
    "chapter_filename_template": "{chapter_num:03d}_{book_title}_{chapter_title}",
    "phoneme_export_template": "{book_title}",
    # Fallback title when metadata is missing
    "default_title": "Untitled",
    # Mixed-language phonemization settings (disabled by default)
    "use_mixed_language": False,  # Enable automatic language detection
    "mixed_language_primary": None,  # Primary language (None = use current lang)
    "mixed_language_allowed": None,  # List of allowed languages (required if enabled)
    "mixed_language_confidence": 0.7,  # Detection confidence threshold (0.0-1.0)
    # SSMD 0.8 rendering policies.  Pause values above remain pipeline
    # defaults; they are intentionally not implicit SSMD header overrides.
    "ssmd_parse_header": True,
    "ssmd_unknown_header": "warn",
    "ssmd_missing_voice": "error",
    "ssmd_validate_profile": True,
    "ssmd_emphasis_mode": "plain",
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

# Audio settings
# SAMPLE_RATE is imported from pykokoro at top of file
AUDIO_CHANNELS = 1

# Sample texts for voice preview (per language)
SAMPLE_TEXTS = {
    "a": "This is a sample of the selected voice.",
    "b": "This is a sample of the selected voice.",
    "d": "Dies ist ein Beispiel für die ausgewählte Stimme.",
    "e": "Este es una muestra de la voz seleccionada.",
    "f": "Ceci est un exemple de la voix sélectionnée.",
    "h": "यह चयनित आवाज़ का एक नमूना है।",  # noqa: E501
    "i": "Questo è un esempio della voce selezionata.",
    "j": "これは選択した声のサンプルです。",  # noqa: E501
    "p": "Este é um exemplo da voz selecionada.",
    "z": "这是所选语音的示例。",
}
