"""Compatibility checks for the Readio public API used by TTSForge."""

from __future__ import annotations

from dataclasses import fields, is_dataclass

import readio.api as readio_api


def test_required_public_api_symbols_are_available() -> None:
    required = {
        "PUBLIC_API_VERSION",
        "Readio",
        "ReadioEvent",
        "AudiobookInspection",
        "EngineInfo",
        "EngineCapabilities",
        "ModelInfo",
        "VoiceInfo",
        "LexiconInfo",
        "DiscoveryOptions",
        "ModelQuery",
        "VoiceQuery",
        "LexiconQuery",
        "G2P_FALLBACKS",
        "LEXICON_DATA_POLICIES",
        "SHORT_SENTENCE_POLICIES",
        "SPACY_POLICIES",
        "VOICE_LEVEL_MODES",
        "AudiobookProjectDescription",
        "AudiobookProjectChapter",
        "SynthesisResolution",
        "AudiobookExportOptions",
        "AudiobookExportResult",
        "AUDIOBOOK_EXPORT_FORMAT",
        "SUPPORTED_AUDIOBOOK_FORMATS",
        "SUPPORTED_AUDIO_FORMATS",
        "SynthesisRequest",
        "CompositionOptions",
        "ExportOptions",
        "ProjectBuildRequest",
        "ProjectSettings",
        "ProjectSynthesisSettings",
    }
    missing = sorted(name for name in required if not hasattr(readio_api, name))
    assert not missing, (
        "The installed Readio does not provide TTSForge's required public API: "
        f"{', '.join(missing)}. Install Readio >=0.4.0,<0.5 "
    )
    assert readio_api.PUBLIC_API_VERSION == 1


def test_expanded_synthesis_resolution_and_request_fields_are_public() -> None:
    request_fields = {field.name for field in fields(readio_api.SynthesisRequest)}
    resolution_fields = {field.name for field in fields(readio_api.SynthesisResolution)}
    assert {
        "lexicons",
        "clear_lexicons",
        "auto_lexicons",
        "spacy",
        "short_sentence",
        "g2p_fallback",
        "lexicon_data_policy",
        "allow_experimental",
        "speed",
        "voice_level",
        "pause_mode",
        "unit",
        "engine",
    } <= request_fields
    assert {
        "lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
        "allow_experimental",
        "short_sentence",
        "voice_level",
        "pause_mode",
        "unit",
        "spacy",
    } <= resolution_fields


def test_m4b_is_a_distinct_public_audiobook_export_contract() -> None:
    assert readio_api.AUDIOBOOK_EXPORT_FORMAT == "m4b"
    assert readio_api.SUPPORTED_AUDIOBOOK_FORMATS == ("m4b",)
    assert "m4b" not in readio_api.SUPPORTED_AUDIO_FORMATS
    assert set(readio_api.SUPPORTED_AUDIO_FORMATS) >= {
        "wav",
        "flac",
        "mp3",
        "m4a",
        "ogg",
        "opus",
    }

    options = readio_api.AudiobookExportOptions
    assert is_dataclass(options)
    assert {
        "format",
        "output",
        "title",
        "author",
        "cover",
        "bitrate",
        "force",
    } <= {field.name for field in fields(options)}


def test_public_services_support_composition_then_audiobook_export() -> None:
    request = readio_api.ProjectBuildRequest(
        target="composition",
        synthesis=readio_api.SynthesisRequest(
            language="en-us",
            voice="af_heart",
            model="kokoro-v1",
            model_source="github",
            quality="fp32",
        ),
        composition=readio_api.CompositionOptions(target_lufs=-18.0),
    )
    assert request.target == "composition"
    assert request.synthesis.voice == "af_heart"
    assert request.synthesis.model == "kokoro-v1"
    assert request.synthesis.model_source == "github"
    assert request.synthesis.quality == "fp32"

    app = readio_api.Readio()
    assert callable(app.audiobooks.inspect)
    assert callable(app.audiobooks.create_project_result)
    assert callable(app.audiobooks.export)
    assert callable(app.projects.status)
    assert callable(app.projects.build)
    assert callable(app.audiobooks.describe_project)
    assert callable(app.projects.resolve_synthesis)
    assert callable(app.projects.preview)
    assert callable(app.projects.settings)
    assert callable(app.projects.configure)


def test_readio_04_catalog_dto_fields_and_canonical_engine_ids() -> None:
    model_fields = {field.name for field in fields(readio_api.ModelInfo)}
    voice_fields = {field.name for field in fields(readio_api.VoiceInfo)}

    assert "engine" in model_fields
    assert "backend" not in model_fields
    assert {"ref", "engine"} <= voice_fields
    assert "selector" not in voice_fields
    assert hasattr(readio_api.VoiceInfo, "target_id")
    assert hasattr(readio_api.VoiceInfo, "qualified_id")

    catalog = readio_api.Readio().catalog
    engines = ("kokoro", "piper", "pocket", "supertonic", "kitten")
    assert tuple(catalog.normalize_engine(engine) for engine in engines) == engines
    assert catalog.normalize_engine("pykokoro") == "kokoro"


def test_catalog_presentation_uses_readio_04_model_engine_and_voice_ref() -> None:
    from ttsforge.ui.catalog import model_item, voice_item

    model = readio_api.ModelInfo(
        id="v1.0",
        source="github",
        languages=("en-us",),
        voices=("af_heart",),
        default_voice="af_heart",
        qualities=("fp32",),
        g2p_backend=None,
        lexicons=(),
        frontend="kokoro",
        status="ready",
        experimental=False,
        runtime_available=True,
        redistribution_allowed=True,
        engine="kokoro",
    )
    voice = readio_api.VoiceInfo(
        ref="kokoro:v1.0/af_heart",
        id="af_heart",
        gender="female",
        language="en",
        locale="en-us",
        language_label="English",
        model="v1.0",
        source="github",
        default=True,
        status="ready",
        experimental=False,
        runtime_available=True,
        engine="kokoro",
    )

    assert "engine: kokoro" in model_item(model).details
    assert "ref: kokoro:v1.0/af_heart" in voice_item(voice).details
