"""TTSForge request mapping tests for Readio's public API."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import (
    AudiobookExportOptions,
    AudiobookExportResult,
    ExportOptions,
    ProjectBuildRequest,
    ProjectBuildResult,
    ProjectRef,
)

from ttsforge.audiobook import AudiobookConverter
from ttsforge.options import AudiobookOptions
from ttsforge.readio_backend import (
    audiobook_export_options,
    composition_options,
    generic_export_options,
    project_build_request,
    synthesis_request,
)


def _options() -> AudiobookOptions:
    return AudiobookOptions(
        source=Path("book.epub"),
        project=Path("book.readio"),
        chapters="2-4,8",
        output=Path("book.m4b"),
        format="m4b",
        language="en-us",
        voice="af_heart",
        engine="kokoro",
        model="kokoro-v1",
        model_source="github",
        quality="fp32",
        speed=1.1,
        lexicons=("crane", "beta"),
        clear_lexicons=False,
        auto_lexicons=False,
        g2p_fallback="espeak",
        lexicon_data_policy="installed-only",
        spacy="lg",
        short_sentence="phrase",
        allow_experimental=True,
        voice_level="calibrated",
        pause_mode="manual",
        unit="paragraph",
        bitrate="128k",
        target_lufs=-18.0,
        offline=True,
        refresh=True,
        title="Book title",
        author="Book author",
        cover=Path("cover.jpg"),
        force=True,
    )


def test_synthesis_and_composition_options_map_to_public_readio_types() -> None:
    options = _options()

    synthesis = synthesis_request(options)
    shared = project_build_request(options, target="composition", synthesis=synthesis)
    assert shared.synthesis is synthesis
    assert synthesis.language == "en-us"
    assert synthesis.voice == "af_heart"
    assert synthesis.model == "kokoro-v1"
    assert synthesis.model_source == "github"
    assert synthesis.quality == "fp32"
    assert synthesis.engine == "kokoro"
    assert synthesis.speed == 1.1
    assert synthesis.offline is True
    assert synthesis.refresh is True
    assert synthesis.lexicons == ("crane", "beta")
    assert synthesis.clear_lexicons is False
    assert synthesis.auto_lexicons is False
    assert synthesis.g2p_fallback == "espeak"
    assert synthesis.lexicon_data_policy == "installed-only"
    assert synthesis.spacy == "lg"
    assert synthesis.short_sentence == "phrase"
    assert synthesis.allow_experimental is True
    assert synthesis.voice_level == "calibrated"
    assert synthesis.pause_mode == "manual"
    assert synthesis.unit == "paragraph"

    composition = composition_options(options)
    assert composition.target_lufs == -18.0


def test_generic_export_maps_only_to_generic_export_options() -> None:
    options = replace(_options(), format="flac", output=Path("book.flac"))

    exported = generic_export_options(options)
    assert isinstance(exported, ExportOptions)
    assert (exported.format, exported.output, exported.bitrate, exported.force) == (
        "flac",
        Path("book.flac"),
        "128k",
        True,
    )

    request = project_build_request(options, target="export")
    assert isinstance(request, ProjectBuildRequest)
    assert request.target == "export"
    assert request.export == exported


def test_m4b_uses_composition_build_and_separate_audiobook_export_options() -> None:
    options = _options()

    request = project_build_request(options, target="composition")
    export = audiobook_export_options(options)

    assert request.target == "composition"
    assert request.export.format != "m4b"
    assert export.format == "m4b"
    assert export.output == Path("book.m4b")
    assert export.title == "Book title"
    assert export.author == "Book author"
    assert export.cover == Path("cover.jpg")
    assert export.bitrate == "128k"
    assert export.force is True


def test_m4b_is_rejected_by_generic_export_mapping() -> None:
    with pytest.raises(ValueError, match="M4B uses audiobook_export_options"):
        generic_export_options(_options())


def test_audiobook_converter_inspects_through_the_public_service() -> None:
    source = Path("book.epub")
    inspection = object()
    calls: list[Path] = []
    app = SimpleNamespace(
        audiobooks=SimpleNamespace(
            inspect=lambda path: calls.append(path) or inspection,
        ),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    result = converter.inspect(source)

    assert result is inspection
    assert calls == [source]


def test_m4b_builds_composition_then_calls_audiobook_export() -> None:
    project = ProjectRef(Path("book.readio"), "id", "book", "audiobook", "epub")
    composition_result = ProjectBuildResult(project, operations=())
    export_result = AudiobookExportResult(
        project=project,
        output_path=Path("book.m4b"),
        format="m4b",
        output_sha256="digest",
        export_id="export-1",
        chapter_count=2,
    )
    calls: list[tuple[str, object]] = []

    def build(project_ref, request):  # type: ignore[no-untyped-def]
        calls.append(("build", request))
        return composition_result

    def export(project_ref, options):  # type: ignore[no-untyped-def]
        calls.append(("export", options))
        return export_result

    app = SimpleNamespace(
        projects=SimpleNamespace(build=build),
        audiobooks=SimpleNamespace(export=export),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    result = converter.build_and_export(project, _options())

    assert result is export_result
    assert [name for name, _ in calls] == ["build", "export"]
    request = calls[0][1]
    assert isinstance(request, ProjectBuildRequest)
    assert request.target == "composition"
    export_options = calls[1][1]
    assert isinstance(export_options, AudiobookExportOptions)
    assert export_options.title == "Book title"
    assert export_options.cover == Path("cover.jpg")


def test_generic_formats_use_the_generic_project_export_branch() -> None:
    project = ProjectRef(Path("book.readio"), "id", "book", "audiobook", "epub")
    build_result = ProjectBuildResult(
        project, operations=(), output_path=Path("book.flac")
    )
    calls: list[ProjectBuildRequest] = []

    def build(project_ref, request):  # type: ignore[no-untyped-def]
        calls.append(request)
        return build_result

    app = SimpleNamespace(
        projects=SimpleNamespace(build=build),
        audiobooks=SimpleNamespace(
            export=lambda *args, **kwargs: pytest.fail("M4B API must not be used")
        ),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    result = converter.build_and_export(
        project, replace(_options(), format="flac", output=Path("book.flac"))
    )

    assert result is build_result
    assert len(calls) == 1
    assert calls[0].target == "export"
    assert calls[0].export is not None
    assert calls[0].export.format == "flac"
