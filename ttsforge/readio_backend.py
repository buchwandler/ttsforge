"""The single, public-API integration seam between TTSForge and Readio."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, cast

from readio.api import (
    AUDIOBOOK_EXPORT_FORMAT,
    AudiobookExportOptions,
    AudioFormat,
    CompositionOptions,
    ExportOptions,
    ProjectBuildRequest,
    Readio,
    ReadioEvent,
    SynthesisRequest,
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
        engine=options.engine,
        speed=options.speed,
        offline=options.offline,
        refresh=options.refresh,
    )


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
