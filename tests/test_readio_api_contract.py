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
        "AudiobookExportOptions",
        "AudiobookExportResult",
        "AUDIOBOOK_EXPORT_FORMAT",
        "SUPPORTED_AUDIOBOOK_FORMATS",
        "SUPPORTED_AUDIO_FORMATS",
        "SynthesisRequest",
        "CompositionOptions",
        "ExportOptions",
        "ProjectBuildRequest",
    }
    missing = sorted(name for name in required if not hasattr(readio_api, name))
    assert not missing, (
        "The installed Readio does not provide TTSForge's required public API: "
        f"{', '.join(missing)}. Install the development Readio checkout; do not "
        "infer a published minimum version until a compatible release exists."
    )
    assert readio_api.PUBLIC_API_VERSION == 1


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
        synthesis=readio_api.SynthesisRequest(language="en-us", voice="af_heart"),
        composition=readio_api.CompositionOptions(target_lufs=-18.0),
    )
    assert request.target == "composition"
    assert request.synthesis.voice == "af_heart"

    app = readio_api.Readio()
    assert callable(app.audiobooks.inspect)
    assert callable(app.audiobooks.create_project_result)
    assert callable(app.audiobooks.export)
    assert callable(app.projects.status)
    assert callable(app.projects.build)
    assert callable(app.projects.preview)
