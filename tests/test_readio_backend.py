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
    ProjectSettings,
    ProjectSynthesisSettings,
    SynthesisResolution,
)

from ttsforge.audiobook import AudiobookConverter
from ttsforge.options import AudiobookOptions
from ttsforge.readio_backend import (
    apply_project_settings,
    audiobook_export_options,
    composition_options,
    generic_export_options,
    project_build_request,
    project_settings,
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


def _resolution() -> SynthesisResolution:
    return SynthesisResolution(
        engine="pykokoro",
        language="en-us",
        voice="af_heart",
        model="v1.0",
        model_source="github",
        quality="fp32",
        speed=1.0,
        unit="sentence",
        pause_mode="auto",
        voice_level="calibrated",
        spacy="auto",
        short_sentence="phrase",
        lexicons=("crane", "beta"),
        g2p_fallback="espeak",
        lexicon_data_policy="installed-only",
        allow_experimental=True,
    )


def test_project_settings_materialize_synthesis_and_m4b_choices() -> None:
    options = _options()
    settings = project_settings(options, _resolution())

    assert isinstance(settings, ProjectSettings)
    assert isinstance(settings.synthesis, ProjectSynthesisSettings)
    assert settings.synthesis is not None
    assert (
        settings.synthesis.engine,
        settings.synthesis.model,
        settings.synthesis.voice,
        settings.synthesis.quality,
        settings.synthesis.speed,
    ) == ("pykokoro", "v1.0", "af_heart", "fp32", 1.0)
    assert settings.synthesis.language == "en-us"
    assert settings.synthesis.lexicons == ("crane", "beta")
    assert settings.synthesis.g2p_fallback == "espeak"
    assert settings.synthesis.lexicon_data_policy == "installed-only"
    assert settings.synthesis.spacy == "auto"
    assert settings.synthesis.short_sentence == "phrase"
    assert settings.synthesis.allow_experimental is True
    assert settings.synthesis.voice_level == "calibrated"
    assert settings.synthesis.pause_mode == "auto"
    assert settings.synthesis.unit == "sentence"
    assert settings.synthesis.offline is True
    assert settings.composition is not None
    assert settings.composition.target_lufs == -18.0
    assert settings.audiobook_export is not None
    assert settings.audiobook_export.format == "m4b"
    assert settings.audiobook_export.output == Path("book.m4b")
    assert settings.audiobook_export.bitrate == "128k"
    assert settings.audiobook_export.title == "Book title"
    assert settings.audiobook_export.author == "Book author"
    assert settings.audiobook_export.cover == Path("cover.jpg")


def test_project_settings_do_not_persist_refresh_or_force() -> None:
    settings = project_settings(_options(), _resolution())

    assert settings.synthesis is not None
    assert not hasattr(settings.synthesis, "refresh")
    assert settings.audiobook_export is not None
    assert settings.audiobook_export.force is False

    generic = project_settings(
        replace(_options(), format="flac", output=Path("book.flac")), _resolution()
    )
    assert generic.export is not None
    assert generic.export.force is False


def test_apply_project_settings_restores_durable_values_only() -> None:
    options = _options()
    settings = project_settings(options, _resolution())
    restored = apply_project_settings(
        replace(
            options,
            language=None,
            engine=None,
            model=None,
            voice=None,
            target_lufs=None,
            output=None,
            title=None,
            author=None,
            cover=None,
            refresh=False,
            force=False,
        ),
        settings,
    )

    assert restored.language == "en-us"
    assert restored.engine == "pykokoro"
    assert restored.model == "v1.0"
    assert restored.model_source == "github"
    assert restored.voice == "af_heart"
    assert restored.speed == 1.0
    assert restored.lexicons == ("crane", "beta")
    assert restored.target_lufs == -18.0
    assert restored.output == Path("book.m4b")
    assert restored.title == "Book title"
    assert restored.author == "Book author"
    assert restored.cover == Path("cover.jpg")
    assert restored.refresh is False
    assert restored.force is False


def test_project_settings_preserve_auto_lexicon_mode() -> None:
    options = replace(
        _options(), lexicons=None, clear_lexicons=False, auto_lexicons=True
    )
    settings = project_settings(options, _resolution())

    assert settings.synthesis is not None
    assert settings.synthesis.auto_lexicons is True
    assert settings.synthesis.lexicons is None
    restored = apply_project_settings(_options(), settings)
    assert restored.auto_lexicons is True
    assert restored.lexicons is None


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


def test_m4b_uses_persisted_settings_for_build_and_export() -> None:
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
    calls: list[tuple[str, object | None]] = []

    def build(project_ref, request=None):  # type: ignore[no-untyped-def]
        calls.append(("build", request))
        return composition_result

    def export(project_ref, options=None):  # type: ignore[no-untyped-def]
        calls.append(("export", options))
        return export_result

    app = SimpleNamespace(
        projects=SimpleNamespace(build=build),
        audiobooks=SimpleNamespace(export=export),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    result = converter.build_and_export(project, replace(_options(), force=False))

    assert result is export_result
    assert calls == [("build", None), ("export", None)]


def test_m4b_force_is_an_invocation_override_not_a_saved_setting() -> None:
    project = ProjectRef(Path("book.readio"), "id", "book", "audiobook", "epub")
    saved = AudiobookExportOptions(
        output=Path("book.m4b"),
        title="Book title",
        author="Book author",
        cover=Path("cover.jpg"),
        bitrate="128k",
        force=False,
    )
    export_result = AudiobookExportResult(
        project=project,
        output_path=Path("book.m4b"),
        format="m4b",
        output_sha256="digest",
        export_id="export-1",
        chapter_count=2,
    )
    calls: list[object] = []

    def export(project_ref, options=None):  # type: ignore[no-untyped-def]
        calls.append(options)
        return export_result

    app = SimpleNamespace(
        projects=SimpleNamespace(
            build=lambda project_ref: ProjectBuildResult(project, operations=()),
            settings=lambda project_ref: ProjectSettings(audiobook_export=saved),
        ),
        audiobooks=SimpleNamespace(export=export),
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]

    converter.build_and_export(project, _options())

    assert len(calls) == 1
    assert isinstance(calls[0], AudiobookExportOptions)
    assert calls[0].force is True
    assert saved.force is False


def test_generic_formats_use_persisted_project_export_settings() -> None:
    project = ProjectRef(Path("book.readio"), "id", "book", "audiobook", "epub")
    build_result = ProjectBuildResult(
        project, operations=(), output_path=Path("book.flac")
    )
    calls: list[object | None] = []

    def build(project_ref, request=None):  # type: ignore[no-untyped-def]
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
        project,
        replace(_options(), format="flac", output=Path("book.flac"), force=False),
    )

    assert result is build_result
    assert calls == [None]
