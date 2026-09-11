"""Canonical document-language helpers used at TTSForge boundaries."""

LEGACY_LANGUAGE_CODES = {
    "a": "en-us",
    "b": "en-gb",
    "d": "de",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "zh",
}

LANGUAGE_ALIASES = {
    "en": "en-us",
    "en-au": "en-gb",
    "de-de": "de",
    "es-es": "es",
    "es-mx": "es",
    "fr": "fr-fr",
    "fr-ca": "fr-fr",
    "pt": "pt-br",
    "pt-pt": "pt-br",
    "zh-cn": "zh",
    "zh-tw": "zh",
}


def canonicalize_language(language: str | None) -> str:
    """Return the canonical BCP-47 value accepted by PyKokoro."""
    if not language or language.strip().lower() == "auto":
        return "auto"
    value = language.strip().lower().replace("_", "-")
    value = LEGACY_LANGUAGE_CODES.get(value, value)
    return LANGUAGE_ALIASES.get(value, value)


def get_pykokoro_language(language: str) -> str:
    """Convert a legacy or canonical value to a PyKokoro language."""
    value = canonicalize_language(language)
    return "en-us" if value == "auto" else value


def get_onnx_lang_code(language: str) -> str:
    """Compatibility alias for the canonical PyKokoro language value."""
    return get_pykokoro_language(language)
