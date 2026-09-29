"""The single, public-API integration seam between TTSForge and Readio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal, cast

from readio.api import (
    AUDIOBOOK_EXPORT_FORMAT,
    AudiobookExportOptions,
    AudioFormat,
    CompositionOptions,
    ExportOptions,
    ProjectBuildRequest,
    ProjectSettings,
    ProjectSynthesisSettings,
    Readio,
    ReadioEvent,
    SynthesisRequest,
    SynthesisResolution,
)

from .options import AudiobookOptions

BuildTarget = Literal["composition", "export"]


def create_readio(
    on_event: Callable[[ReadioEvent], None] | None = None,
) -> Readio:
    """Construct one Readio application instance for a CLI invocation."""
    return Readio(on_event=on_event)


def synthesis_request(options: AudiobookOptions) -> SynthesisRequest:
    """Translate the small audiobook UX model to Readio synthesis options."""
    return SynthesisRequest(
        language=options.language,
        model=options.model,
        model_source=options.model_source,
        quality=options.quality,
        voice=options.voice,
        lexicons=options.lexicons,
        clear_lexicons=options.clear_lexicons,
        auto_lexicons=options.auto_lexicons,
        spacy=options.spacy,
        short_sentence=options.short_sentence,
        g2p_fallback=options.g2p_fallback,
        lexicon_data_policy=options.lexicon_data_policy,
        allow_experimental=options.allow_experimental,
        speed=options.speed,
        voice_level=options.voice_level,
        pause_mode=options.pause_mode,
        unit=options.unit,
        offline=options.offline,
        refresh=options.refresh,
        engine=options.engine,
    )


def project_settings(
    options: AudiobookOptions,
    resolution: SynthesisResolution,
) -> ProjectSettings:
    """Materialize frontend choices as durable Readio project settings."""
    lexicons: tuple[str, ...] | None
    clear_lexicons: bool
    auto_lexicons: bool
    if options.auto_lexicons:
        lexicons = None
        clear_lexicons = False
        auto_lexicons = True
    elif options.clear_lexicons:
        lexicons = ()
        clear_lexicons = True
        auto_lexicons = False
    elif options.lexicons is not None:
        lexicons = options.lexicons
        clear_lexicons = False
        auto_lexicons = False
    elif resolution.lexicons is not None:
        lexicons = resolution.lexicons
        clear_lexicons = False
        auto_lexicons = False
    else:
        lexicons = ()
        clear_lexicons = True
        auto_lexicons = False

    synthesis = ProjectSynthesisSettings(
        language=resolution.language,
        engine=resolution.engine,
        model=resolution.model,
        model_source=resolution.model_source,
        quality=resolution.quality,
        voice=resolution.voice,
        speed=resolution.speed,
        spacy=resolution.spacy,
        short_sentence=resolution.short_sentence,
        lexicons=lexicons,
        clear_lexicons=clear_lexicons,
        auto_lexicons=auto_lexicons,
        g2p_fallback=resolution.g2p_fallback,
        lexicon_data_policy=resolution.lexicon_data_policy,
        allow_experimental=resolution.allow_experimental,
        voice_level=resolution.voice_level,
        pause_mode=resolution.pause_mode,
        unit=resolution.unit,
        offline=options.offline,
    )
    if options.format.lower() == AUDIOBOOK_EXPORT_FORMAT:
        return ProjectSettings(
            synthesis=synthesis,
            composition=composition_options(options),
            audiobook_export=AudiobookExportOptions(
                format=AUDIOBOOK_EXPORT_FORMAT,
                output=options.output,
                title=options.title,
                author=options.author,
                cover=options.cover,
                bitrate=options.bitrate,
                force=False,
            ),
        )
    return ProjectSettings(
        synthesis=synthesis,
        composition=composition_options(options),
        export=ExportOptions(
            format=cast(AudioFormat, options.format.lower()),
            output=options.output,
            bitrate=options.bitrate,
            force=False,
        ),
    )


def apply_project_settings(
    options: AudiobookOptions,
    settings: ProjectSettings,
) -> AudiobookOptions:
    """Apply durable Readio settings without changing invocation-only flags."""
    updates: dict[str, Any] = {}
    synthesis = settings.synthesis
    if synthesis is not None:
        for name in (
            "language",
            "engine",
            "model",
            "model_source",
            "quality",
            "voice",
            "speed",
            "spacy",
            "short_sentence",
            "g2p_fallback",
            "lexicon_data_policy",
            "voice_level",
            "pause_mode",
            "unit",
            "offline",
            "allow_experimental",
        ):
            value = getattr(synthesis, name)
            if value is not None:
                updates[name] = value
        if synthesis.auto_lexicons is True:
            updates.update(lexicons=None, clear_lexicons=False, auto_lexicons=True)
        elif synthesis.clear_lexicons is True:
            updates.update(lexicons=(), clear_lexicons=True, auto_lexicons=False)
        elif synthesis.lexicons is not None:
            updates.update(
                lexicons=synthesis.lexicons,
                clear_lexicons=False,
                auto_lexicons=False,
            )
    if settings.composition is not None:
        updates["target_lufs"] = settings.composition.target_lufs
    if settings.audiobook_export is not None:
        export = settings.audiobook_export
        updates.update(
            format=export.format,
            output=export.output,
            title=export.title,
            author=export.author,
            cover=export.cover,
            bitrate=export.bitrate,
        )
    elif settings.export is not None:
        export = settings.export
        updates.update(
            format=export.format,
            output=export.output,
            bitrate=export.bitrate,
        )
    return replace(options, **updates)


SYNTHESIS_SETUP_FIELDS = frozenset(
    {
        "language",
        "engine",
        "model",
        "model_source",
        "quality",
        "voice",
        "speed",
        "spacy",
        "short_sentence",
        "lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
        "allow_experimental",
        "voice_level",
        "pause_mode",
        "unit",
        "offline",
    }
)


def has_synthesis_setup(settings: ProjectSettings) -> bool:
    """Whether saved settings contain a resolved, resumable synthesis profile."""
    synthesis = settings.synthesis
    if synthesis is None:
        return False
    return all(
        getattr(synthesis, field) is not None
        for field in ("language", "engine", "speed", "unit", "pause_mode")
    )


def project_setting_sources(settings: ProjectSettings) -> frozenset[str]:
    """Return frontend field names represented by public Readio settings."""
    fields: set[str] = set()
    synthesis = settings.synthesis
    if synthesis is not None:
        if has_synthesis_setup(settings):
            fields.update(SYNTHESIS_SETUP_FIELDS)
        else:
            for name in SYNTHESIS_SETUP_FIELDS - {"lexicons"}:
                if getattr(synthesis, name) is not None:
                    fields.add(name)
            if (
                synthesis.lexicons is not None
                or synthesis.clear_lexicons is not None
                or synthesis.auto_lexicons is not None
            ):
                fields.add("lexicons")
    if (
        settings.composition is not None
        and settings.composition.target_lufs is not None
    ):
        fields.add("target_lufs")
    if settings.audiobook_export is not None:
        fields.update({"format", "output", "bitrate", "title", "author", "cover"})
    elif settings.export is not None:
        fields.update({"format", "output", "bitrate"})
    return frozenset(fields)


def composition_options(options: AudiobookOptions) -> CompositionOptions:
    """Map composition preferences without implementing audio processing."""
    return CompositionOptions(target_lufs=options.target_lufs)


def generic_export_options(options: AudiobookOptions) -> ExportOptions:
    """Create Readio's generic audio export request."""
    if options.format == AUDIOBOOK_EXPORT_FORMAT:
        raise ValueError("M4B uses audiobook_export_options(), not generic export.")
    return ExportOptions(
        format=cast(AudioFormat, options.format),
        output=options.output,
        bitrate=options.bitrate,
        force=options.force,
    )


def audiobook_export_options(options: AudiobookOptions) -> AudiobookExportOptions:
    """Create Readio's distinct M4B/audiobook export request."""
    return AudiobookExportOptions(
        format=AUDIOBOOK_EXPORT_FORMAT,
        output=options.output,
        title=options.title,
        author=options.author,
        cover=options.cover,
        bitrate=options.bitrate,
        force=options.force,
    )


def project_build_request(
    options: AudiobookOptions,
    *,
    target: BuildTarget,
    synthesis: SynthesisRequest | None = None,
) -> ProjectBuildRequest:
    """Build the public project request for composition or generic export."""
    resolved_synthesis = synthesis or synthesis_request(options)
    if target == "composition":
        return ProjectBuildRequest(
            target=target,
            selection="all",
            synthesis=resolved_synthesis,
            composition=composition_options(options),
        )
    return ProjectBuildRequest(
        target=target,
        selection="all",
        synthesis=resolved_synthesis,
        composition=composition_options(options),
        export=generic_export_options(options),
    )
