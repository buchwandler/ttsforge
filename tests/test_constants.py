from ttsforge.constants import (
    DEFAULT_CONFIG,
    LANGUAGE_DESCRIPTIONS,
    SUPPORTED_OUTPUT_FORMATS,
)


def test_default_config_uses_canonical_language_and_provider() -> None:
    assert DEFAULT_CONFIG["default_language"] == "auto"
    assert DEFAULT_CONFIG["onnx_provider"] == "cpu"
    assert "use_gpu" not in DEFAULT_CONFIG


def test_language_descriptions_are_canonical() -> None:
    assert set(LANGUAGE_DESCRIPTIONS) == {
        "en-us",
        "en-gb",
        "de",
        "es",
        "fr-fr",
        "hi",
        "it",
        "ja",
        "pt-br",
        "zh",
    }


def test_output_formats_are_supported() -> None:
    assert {"wav", "mp3", "flac", "opus", "m4b"}.issubset(SUPPORTED_OUTPUT_FORMATS)
