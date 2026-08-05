"""Conversion commands for ttsforge CLI.

Commands for converting EPUB/text files to audiobooks:
- convert: Main EPUB to audiobook conversion
- list: List chapters in a file
- info: Show file metadata
- sample: Generate TTS samples
- read: Interactive read command
"""

import logging
import re
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import FrameType
from typing import Any, Literal, TypedDict, cast

import numpy as np
import typer
from pykokoro.config_types import ModelQuality
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm
from rich.table import Table
from typing_extensions import NotRequired

from ..chapter_selection import parse_chapter_selection, resolve_chapter_selection
from ..constants import (
    DEFAULT_CONFIG,
    LANGUAGE_DESCRIPTIONS,
    VOICE_PREFIX_TO_LANG,
)
from ..conversion import (
    Chapter,
    ConversionOptions,
    ConversionProgress,
    TTSConverter,
    detect_language_from_iso,
    get_default_voice_for_language,
    validate_generation_ranges,
)
from ..paragraph_output import ensure_owned_directory, paragraph_directory
from ..prosody_support import (
    ProsodyPolicy,
    build_pykokoro_prosody_config,
)
from ..render_units import validate_conversion_unit
from ..resume_identity import IdentityDifference, JsonValue
from ..short_sentence_config import (
    DEFAULT_SHORT_SENTENCE,
    resolve_short_sentence_config,
    short_sentence_fallback_note,
    validate_short_sentence_config,
)
from ..short_sentence_stats import format_short_sentence_stats
from ..ssmd_support import SSMDPauseOverrideOptions, SSMDPolicy
from ..text_postprocessing import (
    postprocess_extracted_text,
    resolve_text_postprocess_options,
)
from ..utils import (
    format_chapters_range,
    format_filename_template,
    format_size,
    load_config,
    resolve_conversion_defaults,
)
from .backend_config import (
    resolve_model_source_and_variant as _resolve_model_source_and_variant,
)
from .backend_config import (
    resolve_onnx_provider,
)
from .backend_config import (
    resolve_voice_names as _resolve_voice_names,
)
from .helpers import DEFAULT_SAMPLE_TEXT, console, parse_voice_parameter

DEFAULT_MODEL_QUALITY: ModelQuality = "fp32"
_DEFAULT_PROSODY_POLICY = ProsodyPolicy()


def _resolve_ssmd_emphasis_mode(
    *,
    configured: object,
    explicit: str | None,
    enable_approximation: bool,
) -> str:
    """Resolve explicit CLI emphasis controls over persistent configuration."""
    if enable_approximation and explicit is not None:
        raise typer.BadParameter(
            "--enable-ssmd-emphasis cannot be combined with --ssmd-emphasis"
        )
    if enable_approximation:
        return "approximate"
    if explicit is not None:
        return explicit
    return str(configured or "plain")


def _resolve_prosody_policy(
    config: Mapping[str, object],
    *,
    method_override: str | None = None,
    strict_override: bool | None = None,
) -> ProsodyPolicy:
    """Resolve explicit CLI prosody overrides over config and defaults."""
    method = method_override
    if method is None:
        method = str(config.get("prosody_method", DEFAULT_CONFIG["prosody_method"]))
    fallback_value = config.get(
        "prosody_fallback_methods", DEFAULT_CONFIG["prosody_fallback_methods"]
    )
    if not isinstance(fallback_value, (list, tuple)):
        raise ValueError("prosody_fallback_methods must be a list")
    strict_value = (
        strict_override
        if strict_override is not None
        else bool(config.get("prosody_strict", DEFAULT_CONFIG["prosody_strict"]))
    )
    return ProsodyPolicy(
        method=cast(
            Literal["phase_vocoder", "wsola", "esola", "td_psola", "psola"], method
        ),
        fallback_methods=cast(
            tuple[Literal["phase_vocoder", "wsola", "esola", "td_psola", "psola"], ...],
            tuple(fallback_value),
        ),
        strict=strict_value,
        clip=bool(config.get("prosody_clip", DEFAULT_CONFIG["prosody_clip"])),
        n_fft=cast(int, config.get("prosody_n_fft", DEFAULT_CONFIG["prosody_n_fft"])),
        hop_length=(
            cast(int, config["prosody_hop_length"])
            if config.get("prosody_hop_length") is not None
            else None
        ),
        filter_width=cast(
            int,
            config.get("prosody_filter_width", DEFAULT_CONFIG["prosody_filter_width"]),
        ),
        rolloff=cast(
            float, config.get("prosody_rolloff", DEFAULT_CONFIG["prosody_rolloff"])
        ),
        boundary_blend_ms=cast(
            float,
            config.get(
                "prosody_boundary_blend_ms",
                DEFAULT_CONFIG["prosody_boundary_blend_ms"],
            ),
        ),
    )


def _saved_identity_value(
    payload: Mapping[str, JsonValue], key: str, default: object
) -> object:
    """Read one saved identity field while tolerating legacy payloads."""
    return payload[key] if key in payload else default


def _saved_path(payload: Mapping[str, JsonValue], key: str) -> Path | None:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        return None
    path = value.get("path")
    return Path(path) if isinstance(path, str) else None


def _prosody_policy_from_identity(payload: Mapping[str, JsonValue]) -> ProsodyPolicy:
    raw_value = payload.get("prosody_policy")
    if not isinstance(raw_value, Mapping):
        return ProsodyPolicy()
    value = cast(Mapping[str, Any], raw_value)
    fallback = value.get("prosody_fallback_methods", ["wsola", "phase_vocoder"])
    if not isinstance(fallback, (list, tuple)):
        fallback = ["wsola", "phase_vocoder"]
    return ProsodyPolicy(
        method=cast(
            Literal["phase_vocoder", "wsola", "esola", "td_psola", "psola"],
            str(value.get("prosody_method", "wsola")),
        ),
        fallback_methods=cast(
            tuple[Literal["phase_vocoder", "wsola", "esola", "td_psola", "psola"], ...],
            tuple(str(item) for item in fallback if isinstance(item, str)),
        ),
        strict=bool(value.get("prosody_strict", False)),
        clip=bool(value.get("prosody_clip", False)),
        n_fft=int(value.get("prosody_n_fft", 2048)),
        hop_length=(
            int(value["prosody_hop_length"])
            if value.get("prosody_hop_length") is not None
            else None
        ),
        filter_width=int(value.get("prosody_filter_width", 32)),
        rolloff=float(value.get("prosody_rolloff", 0.945)),
        boundary_blend_ms=float(value.get("prosody_boundary_blend_ms", 5.0)),
    )


def _ssmd_policy_from_identity(payload: Mapping[str, JsonValue]) -> SSMDPolicy:
    raw_value = payload.get("ssmd_policy")
    if not isinstance(raw_value, Mapping):
        return SSMDPolicy()
    value = cast(Mapping[str, Any], raw_value)
    pause_value = value.get("pause_overrides")
    pause = (
        SSMDPauseOverrideOptions(
            enabled=(
                bool(pause_value.get("enabled"))
                if isinstance(pause_value, Mapping)
                and pause_value.get("enabled") is not None
                else None
            ),
            sentence=(
                str(pause_value.get("sentence"))
                if isinstance(pause_value, Mapping)
                and pause_value.get("sentence") is not None
                else None
            ),
            paragraph=(
                str(pause_value.get("paragraph"))
                if isinstance(pause_value, Mapping)
                and pause_value.get("paragraph") is not None
                else None
            ),
            voice_change=(
                str(pause_value.get("voice_change"))
                if isinstance(pause_value, Mapping)
                and pause_value.get("voice_change") is not None
                else None
            ),
        )
        if isinstance(pause_value, Mapping)
        else None
    )
    bindings_value = value.get("voice_bindings", {})
    bindings = (
        {
            str(provider): {
                str(reference): str(target)
                for reference, target in provider_bindings.items()
            }
            for provider, provider_bindings in bindings_value.items()
            if isinstance(provider_bindings, Mapping)
        }
        if isinstance(bindings_value, Mapping)
        else {}
    )
    audio_root = _saved_path(value, "audio_root")
    return SSMDPolicy(
        parse_header=bool(value.get("parse_header", True)),
        unknown_header=cast(
            Literal["warn", "error", "ignore"], value.get("unknown_header", "warn")
        ),
        missing_voice=cast(
            Literal["error", "use-default"], value.get("missing_voice", "error")
        ),
        validate_profile=bool(value.get("validate_profile", True)),
        emphasis_mode=cast(
            Literal["plain", "approximate", "warn", "error"],
            value.get("emphasis_mode", "plain"),
        ),
        fail_on_warning=bool(value.get("fail_on_warning", False)),
        voice_bindings=bindings,
        pause_overrides=pause,
        audio_root=audio_root,
        allow_remote_audio=bool(value.get("allow_remote_audio", False)),
        audio_timeout_s=float(value.get("audio_timeout_s", 10.0)),
        audio_max_bytes=int(value.get("audio_max_bytes", 20_000_000)),
        audio_max_duration_s=float(value.get("audio_max_duration_s", 120.0)),
    )


def _format_identity_differences(
    differences: tuple[IdentityDifference, ...], *, verbose: bool
) -> str:
    shown = differences if verbose else differences[:8]
    lines = [
        f"  {difference.path}: saved {difference.saved!r}, "
        f"current {difference.current!r}"
        for difference in shown
    ]
    if not verbose and len(differences) > len(shown):
        lines.append(f"  ... and {len(differences) - len(shown)} more (use --verbose)")
    return "\n".join(lines)


class ContentItem(TypedDict):
    title: str
    text: str
    index: int
    page_number: NotRequired[int]


def get_voices() -> list[str]:
    """Get the list of available voices."""
    cfg = load_config()

    model_source, model_variant = _resolve_model_source_and_variant(cfg)
    return _resolve_voice_names(model_source, model_variant)


def convert(  # noqa: C901
    ctx: typer.Context,
    epub_file: Path,
    output: Path | None,
    output_format: str | None,
    voice: str | None,
    language: str | None,
    lang: str | None,
    use_spacy: bool | None,
    spacy_model: str | None,
    spacy_model_size: str | None,
    speed: float | None,
    use_gpu: bool | None,
    provider: str | None,
    chapters: str | None,
    skip_chapters: str | None,
    silence: float | None,
    pause_clause: float | None,
    pause_sentence: float | None,
    pause_paragraph: float | None,
    pause_variance: float | None,
    random_seed: int | None,
    pause_mode: str | None,
    enable_short_sentence: bool | None,
    short_sentence: str | None,
    announce_chapters: bool | None,
    chapter_pause: float | None,
    title: str | None,
    author: str | None,
    cover: Path | None,
    yes: bool,
    verbose: bool,
    split_mode: str | None,
    conversion_unit: str | None,
    resume: bool,
    generate_ssmd_only: bool,
    detect_emphasis: bool | None,
    epub_content_mode: str | None,
    prosody_method: str | None,
    prosody_strict: bool | None,
    fresh: bool,
    keep_chapter_files: bool,
    voice_blend: str | None,
    voice_database: Path | None,
    use_mixed_language: bool | None,
    mixed_language_primary: str | None,
    mixed_language_allowed: str | None,
    mixed_language_confidence: float | None,
    phoneme_dictionary_path: str | None,
    phoneme_dict_case_sensitive: bool | None,
    subchapter_markers: tuple[str, ...],
    ssmd_header: bool | None = None,
    ssmd_unknown_header: str | None = None,
    ssmd_missing_voice: str | None = None,
    ssmd_emphasis: str | None = None,
    enable_ssmd_emphasis: bool = False,
    ssmd_profile_validation: bool | None = None,
    ssmd_fail_on_warning: bool | None = None,
    ssmd_voice: list[str] | None = None,
    ssmd_pause_defaults: bool | None = None,
    pause_voice_change: float | None = None,
    ssmd_audio_root: Path | None = None,
    ssmd_remote_audio: bool | None = None,
    ssmd_audio_max_bytes: int | None = None,
    ssmd_audio_max_duration: float | None = None,
    embed_ssmd_voice_bindings: bool | None = None,
    embed_ssmd_pause_defaults: bool | None = None,
) -> None:
    """Convert an EPUB file to an audiobook.

    EPUB_FILE is the path to the EPUB file to convert.
    """
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s [%(name)s] - %(message)s",
        )

    config = load_config()
    explicit_voice = voice
    explicit_language = language
    effective_use_spacy = (
        use_spacy
        if use_spacy is not None
        else config.get("use_spacy", DEFAULT_CONFIG["use_spacy"])
    )
    effective_spacy_model = (
        spacy_model if spacy_model is not None else config.get("spacy_model")
    )
    effective_spacy_model_size = (
        spacy_model_size
        if spacy_model_size is not None
        else config.get("spacy_model_size")
    )
    effective_detect_emphasis = (
        detect_emphasis
        if detect_emphasis is not None
        else bool(config.get("detect_emphasis", DEFAULT_CONFIG["detect_emphasis"]))
    )
    effective_epub_content_mode = (
        epub_content_mode
        if epub_content_mode is not None
        else str(config.get("epub_content_mode", DEFAULT_CONFIG["epub_content_mode"]))
    )
    if effective_epub_content_mode not in {"markdown", "plain"}:
        console.print("[red]Invalid EPUB content mode:[/red] must be markdown or plain")
        raise typer.Exit(code=2)
    try:
        effective_prosody_policy = _resolve_prosody_policy(
            config,
            method_override=prosody_method,
            strict_override=prosody_strict,
        )
    except (TypeError, ValueError) as exc:
        console.print(f"[red]Invalid prosody configuration:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    try:
        resolved_provider = resolve_onnx_provider(
            config, provider_override=provider, use_gpu_override=use_gpu
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    model_path = ctx.obj.get("model_path") if ctx.obj else None
    voices_path = ctx.obj.get("voices_path") if ctx.obj else None
    model_source, model_variant = _resolve_model_source_and_variant(config)
    model_quality = cast(
        ModelQuality, config.get("model_quality", DEFAULT_MODEL_QUALITY)
    )
    text_postprocess_options = resolve_text_postprocess_options(
        config,
        subchapter_markers=subchapter_markers,
    )
    resolved_defaults = resolve_conversion_defaults(
        config,
        {
            "voice": voice,
            "language": language,
            "speed": speed,
            "split_mode": split_mode,
            "use_gpu": use_gpu,
            "onnx_provider": resolved_provider,
            "lang": lang,
        },
    )
    effective_language = resolved_defaults["language"]
    effective_enable_short_sentence = (
        enable_short_sentence
        if enable_short_sentence is not None
        else config.get("enable_short_sentence", None)
    )
    effective_short_sentence = (
        short_sentence if short_sentence is not None else config.get("short_sentence")
    )
    _validate_short_sentence_or_abort(
        effective_short_sentence,
        effective_enable_short_sentence,
    )

    # Preserve the existing validation ordering: invalid persisted settings
    # must fail before any new interactive conversion-unit prompt.
    try:
        validate_generation_ranges(
            speed=resolved_defaults["speed"],
            mixed_language_confidence=(
                mixed_language_confidence
                if mixed_language_confidence is not None
                else config.get("mixed_language_confidence", 0.7)
            ),
            silence_between_chapters=(
                silence
                if silence is not None
                else config.get("silence_between_chapters", 2.0)
            ),
            pause_clause=(
                pause_clause
                if pause_clause is not None
                else config.get("pause_clause", 0.3)
            ),
            pause_sentence=(
                pause_sentence
                if pause_sentence is not None
                else config.get("pause_sentence", 0.5)
            ),
            pause_paragraph=(
                pause_paragraph
                if pause_paragraph is not None
                else config.get("pause_paragraph", 0.9)
            ),
            pause_variance=(
                pause_variance
                if pause_variance is not None
                else config.get("pause_variance", 0.05)
            ),
            chapter_pause_after_title=(
                chapter_pause
                if chapter_pause is not None
                else config.get("chapter_pause_after_title", 2.0)
            ),
        )
    except (TypeError, ValueError) as exc:
        console.print(f"[red]Invalid conversion configuration:[/red] {exc}.")
        raise typer.Exit(code=2) from exc

    # Get format first (needed for output path construction)
    fmt = (
        output_format
        if output_format is not None
        else config.get("default_format", "m4b")
    )

    # Load chapters from input file
    console.print(f"[bold]Loading:[/bold] {epub_file}")

    from ..input_reader import EpubReadOptions, InputReader

    # Parse input file
    try:
        reader = InputReader(
            epub_file,
            postprocess_options=text_postprocess_options,
            epub_options=EpubReadOptions(
                content_mode=cast(
                    Literal["markdown", "plain"], effective_epub_content_mode
                ),
                preserve_emphasis=effective_detect_emphasis,
            ),
        )
    except Exception as e:
        console.print(f"[red]Error loading file:[/red] {e}")
        sys.exit(1)

    # Get metadata
    metadata = reader.get_metadata()
    default_title = config.get("default_title", "Untitled")
    epub_title = metadata.title or default_title
    epub_author = metadata.authors[0] if metadata.authors else "Unknown"
    epub_language = metadata.language

    # Use CLI title/author if provided, otherwise use metadata
    effective_title = title or epub_title
    effective_author = author or epub_author

    # Extract chapters through the selected public epub2text boundary.
    with console.status("Extracting chapters..."):
        epub_chapters = reader.get_chapters()

    if not epub_chapters:
        console.print("[red]Error:[/red] No chapters found in file.")
        sys.exit(1)

    console.print(f"[green]Found {len(epub_chapters)} chapters[/green]")

    if verbose:
        from ..epub_markdown import markdown_structure_counts

        structure = {
            "headings": 0,
            "subheadings": 0,
            "moderate_spans": 0,
            "strong_spans": 0,
            "scene_breaks": 0,
        }
        diagnostic_count = 0
        for chapter in epub_chapters:
            counts = markdown_structure_counts(chapter.markdown_body or "")
            for key in structure:
                structure[key] += counts[key]
            diagnostic_count += len(chapter.extraction_diagnostics)
        console.print(
            "[dim]EPUB extraction: "
            f"{structure['headings']} headings, "
            f"{structure['subheadings']} subheadings, "
            f"{structure['moderate_spans']} italic spans, "
            f"{structure['strong_spans']} strong spans, "
            f"{structure['scene_breaks']} scene breaks, "
            f"{diagnostic_count} epub2text diagnostics[/dim]"
        )

    # Auto-detect language if not specified
    if language is None:
        if epub_language:
            language = detect_language_from_iso(epub_language)
            lang_desc = LANGUAGE_DESCRIPTIONS.get(language, language)
            console.print(f"[dim]Auto-detected language: {lang_desc}[/dim]")
        else:
            language = config.get("default_language", "a")

    # Get voice
    if voice is None:
        voice = config.get("default_voice")
        # Ensure voice matches language
        if voice and language:
            voice_lang = VOICE_PREFIX_TO_LANG.get(voice[:2], "a")
            if voice_lang != language:
                voice = get_default_voice_for_language(language)
        elif language:
            voice = get_default_voice_for_language(language)
        else:
            voice = "af_heart"

    # Ensure language has a default
    if language is None:
        language = "a"

    # Track whether the user explicitly supplied selection arguments.
    selection_is_explicit = chapters is not None or skip_chapters is not None
    output_was_explicit = output is not None

    # --- Resume discovery ---
    # Run before interactive selection to restore saved scope when the user
    # did not explicitly supply a new selection.
    from ..conversion import ResumeCandidate, discover_resume_candidate

    resume_candidate: ResumeCandidate | None = None
    if resume and not fresh and not selection_is_explicit:
        resume_candidate = discover_resume_candidate(
            source_file=epub_file,
            output_dir=output.parent if output else epub_file.parent,
            book_title=effective_title,
            chapters=[
                Chapter(
                    title=ch.title,
                    content=ch.text,
                    index=ch.index,
                    markdown_body=ch.markdown_body,
                    source_format=ch.source_format,
                    source_id=ch.source_id,
                    parent_id=ch.parent_id,
                    level=ch.level,
                    extraction_schema=ch.extraction_schema,
                    extraction_diagnostics=ch.extraction_diagnostics,
                    is_ssmd=ch.is_ssmd,
                )
                for i, ch in enumerate(epub_chapters)
            ],
        )

    saved_identity_payload: Mapping[str, JsonValue] | None = None
    saved_mixed_language_allowed: list[str] | None = None
    if resume_candidate is not None and not fresh:
        candidate_state = resume_candidate.state
        if (
            candidate_state.generation_identity_schema == 2
            and candidate_state.generation_identity
        ):
            saved_identity_payload = candidate_state.generation_identity

    # A schema-7 workspace owns the effective generation settings.  Restore
    # omitted values before constructing ConversionOptions; explicit values
    # remain in place so the shared strong validator can report differences.
    if saved_identity_payload is not None:
        saved = saved_identity_payload

        def restore(key: str, current: object, explicit: object) -> object:
            return (
                current
                if explicit is not None
                else _saved_identity_value(saved, key, current)
            )

        voice = cast(str | None, restore("voice", voice, explicit_voice))
        language = cast(str | None, restore("language", language, explicit_language))
        effective_language = language or "a"
        resolved_defaults["voice"] = voice or resolved_defaults["voice"]
        resolved_defaults["language"] = effective_language
        resolved_defaults["speed"] = restore("speed", resolved_defaults["speed"], speed)
        resolved_defaults["split_mode"] = restore(
            "split_mode", resolved_defaults["split_mode"], split_mode
        )
        resolved_defaults["lang"] = restore("lang", resolved_defaults["lang"], lang)
        if provider is None:
            resolved_provider = cast(
                str, _saved_identity_value(saved, "onnx_provider", resolved_provider)
            )
        if use_gpu is None:
            use_gpu = cast(bool, _saved_identity_value(saved, "use_gpu", use_gpu))
        model_quality = cast(
            ModelQuality,
            _saved_identity_value(saved, "model_quality", model_quality),
        )
        model_source = cast(
            str, _saved_identity_value(saved, "model_source", model_source)
        )
        model_variant = cast(
            str, _saved_identity_value(saved, "model_variant", model_variant)
        )
        if voice_blend is None:
            voice_blend = cast(str | None, saved.get("voice_blend"))
        if model_path is None:
            model_path = _saved_path(saved, "model_path")
        if voices_path is None:
            voices_path = _saved_path(saved, "voices_path")
        if voice_database is None:
            voice_database = _saved_path(saved, "voice_database")
        if phoneme_dictionary_path is None:
            dictionary_path = _saved_path(saved, "phoneme_dictionary")
            phoneme_dictionary_path = str(dictionary_path) if dictionary_path else None
        for name, explicit in (
            ("silence_between_chapters", silence),
            ("pause_clause", pause_clause),
            ("pause_sentence", pause_sentence),
            ("pause_paragraph", pause_paragraph),
            ("pause_variance", pause_variance),
            ("random_seed", random_seed),
            ("pause_mode", pause_mode),
            ("enable_short_sentence", enable_short_sentence),
            ("short_sentence", short_sentence),
            ("announce_chapters", announce_chapters),
            ("chapter_pause_after_title", chapter_pause),
            ("use_mixed_language", use_mixed_language),
            ("mixed_language_primary", mixed_language_primary),
            ("mixed_language_confidence", mixed_language_confidence),
            ("phoneme_dict_case_sensitive", phoneme_dict_case_sensitive),
        ):
            if explicit is None:
                value = _saved_identity_value(saved, name, None)
                if name == "silence_between_chapters":
                    silence = cast(float | None, value)
                elif name == "pause_clause":
                    pause_clause = cast(float | None, value)
                elif name == "pause_sentence":
                    pause_sentence = cast(float | None, value)
                elif name == "pause_paragraph":
                    pause_paragraph = cast(float | None, value)
                elif name == "pause_variance":
                    pause_variance = cast(float | None, value)
                elif name == "random_seed":
                    random_seed = cast(int | None, value)
                elif name == "pause_mode":
                    pause_mode = cast(str | None, value)
                elif name == "enable_short_sentence":
                    enable_short_sentence = cast(bool | None, value)
                elif name == "short_sentence":
                    short_sentence = cast(str | None, value)
                elif name == "announce_chapters":
                    announce_chapters = cast(bool | None, value)
                elif name == "chapter_pause_after_title":
                    chapter_pause = cast(float | None, value)
                elif name == "use_mixed_language":
                    use_mixed_language = cast(bool | None, value)
                elif name == "mixed_language_primary":
                    mixed_language_primary = cast(str | None, value)
                elif name == "mixed_language_confidence":
                    mixed_language_confidence = cast(float | None, value)
                elif name == "phoneme_dict_case_sensitive":
                    phoneme_dict_case_sensitive = cast(bool | None, value)
        saved_allowed = saved.get("mixed_language_allowed")
        if mixed_language_allowed is None and isinstance(saved_allowed, list):
            saved_mixed_language_allowed = [str(item) for item in saved_allowed]
        saved_short_enable = enable_short_sentence
        effective_enable_short_sentence = saved_short_enable
        effective_short_sentence = short_sentence
        if epub_content_mode is None:
            effective_epub_content_mode = cast(
                Literal["markdown", "plain"],
                _saved_identity_value(
                    saved, "epub_content_mode", effective_epub_content_mode
                ),
            )
        if detect_emphasis is None:
            effective_detect_emphasis = cast(
                bool,
                _saved_identity_value(
                    saved, "detect_emphasis", effective_detect_emphasis
                ),
            )
        if not subchapter_markers:
            text_options_value = saved.get("text_postprocess_options")
            if isinstance(text_options_value, Mapping):
                saved_markers = text_options_value.get("subchapter_markers")
                if isinstance(saved_markers, list):
                    text_postprocess_options = resolve_text_postprocess_options(
                        {},
                        subchapter_markers=tuple(str(item) for item in saved_markers),
                    )

    if (
        resume_candidate is not None
        and not fresh
        and saved_identity_payload is None
        and resume_candidate.state.version == 6
    ):
        # Schema 6 retained these fields directly but not the complete
        # generation payload.  Restore only values it actually persisted;
        # the converter's legacy digest check remains conservative.
        legacy_state = resume_candidate.state
        if explicit_voice is None:
            voice = legacy_state.voice
            resolved_defaults["voice"] = legacy_state.voice
        if explicit_language is None:
            language = legacy_state.language
            effective_language = language or "a"
            resolved_defaults["language"] = effective_language
        if speed is None:
            resolved_defaults["speed"] = legacy_state.speed
        if split_mode is None:
            resolved_defaults["split_mode"] = legacy_state.split_mode
        if lang is None:
            resolved_defaults["lang"] = legacy_state.lang
        if provider is None:
            resolved_provider = legacy_state.onnx_provider or resolved_provider
        if use_spacy is None:
            effective_use_spacy = legacy_state.use_spacy
        if spacy_model is None:
            effective_spacy_model = legacy_state.spacy_model
        if spacy_model_size is None:
            effective_spacy_model_size = legacy_state.spacy_model_size
        model_quality = legacy_state.model_quality
        if output_format is None:
            output_format = legacy_state.output_format
        if silence is None:
            silence = legacy_state.silence_between_chapters
        if pause_clause is None:
            pause_clause = legacy_state.pause_clause
        if pause_sentence is None:
            pause_sentence = legacy_state.pause_sentence
        if pause_paragraph is None:
            pause_paragraph = legacy_state.pause_paragraph
        if pause_variance is None:
            pause_variance = legacy_state.pause_variance
        if random_seed is None:
            random_seed = legacy_state.random_seed
        if pause_mode is None:
            pause_mode = legacy_state.pause_mode
        if enable_short_sentence is None:
            enable_short_sentence = legacy_state.enable_short_sentence
        if short_sentence is None:
            short_sentence = legacy_state.short_sentence
        if phoneme_dict_case_sensitive is None:
            phoneme_dict_case_sensitive = False
        effective_enable_short_sentence = enable_short_sentence
        effective_short_sentence = short_sentence

    if saved_identity_payload is not None:
        # Re-extract with the saved text/emphasis policy.  The initial read is
        # needed for workspace discovery, but must not become the source for
        # rendering when configuration changed between invocations.
        try:
            reader = InputReader(
                epub_file,
                postprocess_options=text_postprocess_options,
                epub_options=EpubReadOptions(
                    content_mode=cast(
                        Literal["markdown", "plain"], effective_epub_content_mode
                    ),
                    preserve_emphasis=effective_detect_emphasis,
                ),
            )
            epub_chapters = reader.get_chapters()
        except Exception as exc:
            console.print(
                f"[red]Error reloading saved conversion settings:[/red] {exc}"
            )
            raise typer.Exit(code=1) from exc

    # Conversion granularity is a workspace property. Resolve it only after
    # discovering a resumable workspace so resume never prompts.
    if resume_candidate is not None and not fresh:
        saved_unit = validate_conversion_unit(resume_candidate.state.conversion_unit)
        if conversion_unit is not None and conversion_unit != saved_unit:
            console.print(
                f"[red]This conversion workspace was created"
                f" in {saved_unit} mode.[/red]\n"
                "The conversion unit cannot be changed"
                " while resuming.\n"
                f"Use --fresh --conversion-unit"
                f" {conversion_unit} to start a new conversion."
            )
            raise typer.Exit(code=2)
        effective_conversion_unit = saved_unit
    elif conversion_unit is not None:
        try:
            effective_conversion_unit = validate_conversion_unit(conversion_unit)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--conversion-unit") from exc
    elif yes:
        effective_conversion_unit = "chapter"
    else:
        answer = (
            console.input("Conversion unit [chapter/paragraph] (chapter): ")
            .strip()
            .lower()
        )
        try:
            effective_conversion_unit = validate_conversion_unit(answer or "chapter")
        except ValueError as exc:
            console.print(f"[red]Invalid conversion unit:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    if generate_ssmd_only and effective_conversion_unit == "paragraph":
        console.print(
            "[red]--generate-ssmd cannot be combined"
            " with --conversion-unit paragraph[/red]"
        )
        raise typer.Exit(code=2)

    # --- Chapter selection with precedence ---
    #   1. Explicit --chapters / --skip-chapters (user intent wins)
    #   2. Resume candidate (restore saved selection)
    #   3. Interactive prompt (when not --yes)
    #   4. All chapters (--yes with no selection)
    selected_indices: list[int] | None = None
    if selection_is_explicit:
        try:
            selected_indices = resolve_chapter_selection(
                chapters, skip_chapters, len(epub_chapters)
            )
        except ValueError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            sys.exit(1)
    elif resume_candidate is not None:
        selected_indices = resume_candidate.selected_positions
    elif not yes:
        selected_indices = _interactive_chapter_selection(epub_chapters)

    if selected_indices is not None and len(selected_indices) == 0:
        console.print("[yellow]No chapters selected. Exiting.[/yellow]")
        return

    # --- Output path ---
    # When resuming and the user did not pass --output, restore the saved
    # output path.  Otherwise derive it from the filename template.
    if not output_was_explicit and resume_candidate is not None:
        output = resume_candidate.saved_output
    elif output is None:
        output_template = config.get("output_filename_template", "{book_title}")
        chapters_range = format_chapters_range(
            selected_indices or list(range(len(epub_chapters))),
            len(epub_chapters),
        )
        output_filename = format_filename_template(
            output_template,
            book_title=effective_title,
            author=effective_author,
            input_stem=epub_file.stem,
            chapters_range=chapters_range,
            default_title=default_title,
        )
        # Append chapters range to filename if partial selection
        if chapters_range:
            output_filename = f"{output_filename}_{chapters_range}"
        output = epub_file.parent / f"{output_filename}.{fmt}"
    elif output.is_dir():
        # If output is a directory, construct filename using template
        output_template = config.get("output_filename_template", "{book_title}")
        chapters_range = format_chapters_range(
            selected_indices or list(range(len(epub_chapters))),
            len(epub_chapters),
        )
        output_filename = format_filename_template(
            output_template,
            book_title=effective_title,
            author=effective_author,
            input_stem=epub_file.stem,
            chapters_range=chapters_range,
            default_title=default_title,
        )
        if chapters_range:
            output_filename = f"{output_filename}_{chapters_range}"
        output = output / f"{output_filename}.{fmt}"

    if resume_candidate is not None and not fresh and output is not None:
        if output.resolve() != resume_candidate.saved_output.resolve():
            console.print(
                "[red]The output path cannot change while"
                " resuming this conversion workspace.[/red]\n"
                "Use --fresh to start a new conversion"
                " at the requested output path."
            )
            raise typer.Exit(code=2)

    # Get format from output extension if not specified
    if output_format is None:
        if saved_identity_payload is not None:
            output_format = cast(
                str,
                _saved_identity_value(
                    saved_identity_payload,
                    "output_format",
                    output.suffix.lstrip(".") or config.get("default_format", "m4b"),
                ),
            )
        else:
            output_format = output.suffix.lstrip(".") or config.get(
                "default_format", "m4b"
            )

    # Parse mixed_language_allowed from comma-separated string
    parsed_mixed_language_allowed = None
    if mixed_language_allowed is not None:
        parsed_mixed_language_allowed = [
            lang.strip() for lang in mixed_language_allowed.split(",")
        ]
    elif saved_mixed_language_allowed is not None:
        parsed_mixed_language_allowed = saved_mixed_language_allowed

    effective_ssmd_emphasis = _resolve_ssmd_emphasis_mode(
        configured=config.get("ssmd_emphasis_mode", "plain"),
        explicit=ssmd_emphasis,
        enable_approximation=enable_ssmd_emphasis,
    )

    ssmd_bindings: dict[str, str] = {}
    for binding in ssmd_voice or []:
        if "=" not in binding:
            raise typer.BadParameter("--ssmd-voice must use ROLE=VOICE")
        role, target = binding.split("=", 1)
        if not role or not target or "." in role:
            raise typer.BadParameter(
                "--ssmd-voice requires a non-empty unqualified ROLE and VOICE"
            )
        if role in ssmd_bindings and ssmd_bindings[role] != target:
            raise typer.BadParameter(f"conflicting --ssmd-voice binding for {role!r}")
        ssmd_bindings[role] = target
    explicit_pause_options = SSMDPauseOverrideOptions(
        enabled=ssmd_pause_defaults,
        sentence=(f"{pause_sentence}s" if pause_sentence is not None else None),
        paragraph=(f"{pause_paragraph}s" if pause_paragraph is not None else None),
        voice_change=(
            f"{pause_voice_change}s" if pause_voice_change is not None else None
        ),
    )
    if all(
        value is None
        for value in (
            explicit_pause_options.enabled,
            explicit_pause_options.sentence,
            explicit_pause_options.paragraph,
            explicit_pause_options.voice_change,
        )
    ):
        explicit_pause: SSMDPauseOverrideOptions | None = None
    else:
        explicit_pause = explicit_pause_options
    ssmd_policy = SSMDPolicy(
        parse_header=(
            ssmd_header
            if ssmd_header is not None
            else bool(config.get("ssmd_parse_header", True))
        ),
        unknown_header=cast(
            Literal["warn", "error", "ignore"],
            ssmd_unknown_header
            if ssmd_unknown_header is not None
            else config.get("ssmd_unknown_header", "warn"),
        ),
        missing_voice=cast(
            Literal["error", "use-default"],
            ssmd_missing_voice
            if ssmd_missing_voice is not None
            else config.get("ssmd_missing_voice", "error"),
        ),
        validate_profile=(
            ssmd_profile_validation
            if ssmd_profile_validation is not None
            else bool(config.get("ssmd_validate_profile", True))
        ),
        emphasis_mode=cast(
            Literal["plain", "approximate", "warn", "error"],
            effective_ssmd_emphasis,
        ),
        fail_on_warning=(
            ssmd_fail_on_warning
            if ssmd_fail_on_warning is not None
            else bool(config.get("ssmd_fail_on_warning", False))
        ),
        voice_bindings={"kokoro": ssmd_bindings}
        if ssmd_bindings
        else {"kokoro": dict(config.get("ssmd_voice_bindings", {}))}
        if config.get("ssmd_voice_bindings") or ssmd_bindings
        else {},
        pause_overrides=explicit_pause,
        audio_root=ssmd_audio_root
        if ssmd_audio_root is not None
        else (
            Path(config["ssmd_audio_root"]) if config.get("ssmd_audio_root") else None
        ),
        allow_remote_audio=(
            ssmd_remote_audio
            if ssmd_remote_audio is not None
            else bool(config.get("ssmd_audio_allow_remote", False))
        ),
        audio_max_bytes=(
            ssmd_audio_max_bytes
            if ssmd_audio_max_bytes is not None
            else int(config.get("ssmd_audio_max_bytes", 20_000_000))
        ),
        audio_max_duration_s=(
            ssmd_audio_max_duration
            if ssmd_audio_max_duration is not None
            else float(config.get("ssmd_audio_max_duration_s", 120.0))
        ),
    )
    if saved_identity_payload is not None:
        explicit_ssmd_policy = (
            any(
                value is not None
                for value in (
                    ssmd_header,
                    ssmd_unknown_header,
                    ssmd_missing_voice,
                    ssmd_emphasis,
                    ssmd_profile_validation,
                    ssmd_fail_on_warning,
                    ssmd_voice,
                    ssmd_pause_defaults,
                    pause_voice_change,
                    ssmd_audio_root,
                    ssmd_remote_audio,
                    ssmd_audio_max_bytes,
                    ssmd_audio_max_duration,
                )
            )
            or enable_ssmd_emphasis
        )
        if not explicit_ssmd_policy:
            ssmd_policy = _ssmd_policy_from_identity(saved_identity_payload)
        if prosody_method is None and prosody_strict is None:
            effective_prosody_policy = _prosody_policy_from_identity(
                saved_identity_payload
            )

    # Validate all effective settings before showing a summary or asking for
    # confirmation. Config-derived values do not pass through Typer's bounds.
    try:
        options = ConversionOptions(
            voice=resolved_defaults["voice"],
            language=effective_language,
            speed=resolved_defaults["speed"],
            output_format=(
                output_format
                if output_format is not None
                else config.get("default_format", "m4b")
            ),
            output_dir=output.parent,
            use_gpu=use_gpu if use_gpu is not None else config.get("use_gpu", False),
            onnx_provider=resolved_provider,
            model_quality=model_quality,
            model_source=model_source,
            model_variant=model_variant,
            silence_between_chapters=(
                silence
                if silence is not None
                else config.get("silence_between_chapters", 2.0)
            ),
            lang=(lang if lang is not None else config.get("phonemization_lang")),
            use_spacy=effective_use_spacy,
            spacy_model=effective_spacy_model,
            spacy_model_size=effective_spacy_model_size,
            use_mixed_language=(
                use_mixed_language
                if use_mixed_language is not None
                else config.get("use_mixed_language", False)
            ),
            mixed_language_primary=(
                mixed_language_primary
                if mixed_language_primary is not None
                else config.get("mixed_language_primary")
            ),
            mixed_language_allowed=(
                parsed_mixed_language_allowed
                if parsed_mixed_language_allowed is not None
                else config.get("mixed_language_allowed")
            ),
            mixed_language_confidence=(
                mixed_language_confidence
                if mixed_language_confidence is not None
                else config.get("mixed_language_confidence", 0.7)
            ),
            phoneme_dictionary_path=(
                phoneme_dictionary_path
                if phoneme_dictionary_path is not None
                else config.get("phoneme_dictionary_path")
            ),
            phoneme_dict_case_sensitive=(
                phoneme_dict_case_sensitive
                if phoneme_dict_case_sensitive is not None
                else config.get("phoneme_dict_case_sensitive", False)
            ),
            pause_clause=(
                pause_clause
                if pause_clause is not None
                else config.get("pause_clause", 0.3)
            ),
            pause_sentence=(
                pause_sentence
                if pause_sentence is not None
                else config.get("pause_sentence", 0.5)
            ),
            pause_paragraph=(
                pause_paragraph
                if pause_paragraph is not None
                else config.get("pause_paragraph", 0.9)
            ),
            pause_variance=(
                pause_variance
                if pause_variance is not None
                else config.get("pause_variance", 0.05)
            ),
            random_seed=random_seed,
            pause_mode=(
                pause_mode
                if pause_mode is not None
                else config.get("pause_mode", "auto")
            ),
            enable_short_sentence=effective_enable_short_sentence,
            short_sentence=effective_short_sentence,
            announce_chapters=(
                announce_chapters
                if announce_chapters is not None
                else config.get("announce_chapters", True)
            ),
            chapter_pause_after_title=(
                chapter_pause
                if chapter_pause is not None
                else config.get("chapter_pause_after_title", 2.0)
            ),
            split_mode=resolved_defaults["split_mode"],
            conversion_unit=effective_conversion_unit,
            resume=False if fresh else resume,
            keep_chapter_files=keep_chapter_files,
            title=effective_title,
            author=effective_author,
            cover_image=cover,
            voice_blend=voice_blend,
            voice_database=voice_database,
            chapter_filename_template=config.get(
                "chapter_filename_template",
                "{chapter_num:03d}_{book_title}_{chapter_title}",
            ),
            model_path=model_path,
            voices_path=voices_path,
            generate_ssmd_only=generate_ssmd_only,
            detect_emphasis=effective_detect_emphasis,
            epub_content_mode=cast(
                Literal["markdown", "plain"], effective_epub_content_mode
            ),
            text_postprocess_options=text_postprocess_options,
            ssmd_policy=ssmd_policy,
            prosody_policy=effective_prosody_policy,
        )
    except ValueError as exc:
        console.print(f"[red]Invalid conversion configuration:[/red] {exc}.")
        raise typer.Exit(code=2) from exc

    # Strongly validate a discovered candidate before promising resume. Weak
    # discovery restores scope only; this check verifies generation identity,
    # state schema, and retained artifacts without mutating the workspace.
    if resume_candidate is not None and not fresh:
        validation_chapters = [
            Chapter(
                title=ch.title,
                content=ch.text,
                index=ch.index,
                markdown_body=ch.markdown_body,
                source_format=ch.source_format,
                source_id=ch.source_id,
                parent_id=ch.parent_id,
                level=ch.level,
                extraction_schema=ch.extraction_schema,
                extraction_diagnostics=ch.extraction_diagnostics,
                is_ssmd=ch.is_ssmd,
            )
            for i, ch in enumerate(epub_chapters)
            if selected_indices is None or i in selected_indices
        ]
        validation = TTSConverter(options).validate_resume_candidate(
            resume_candidate, validation_chapters
        )
        if not validation.reusable:
            if validation.reason == "generation-fingerprint-changed":
                console.print(
                    "[red]Saved conversion cannot be resumed:[/red] "
                    "generation settings changed."
                )
                if validation.differences:
                    console.print("\nChanged settings:")
                    console.print(
                        _format_identity_differences(
                            validation.differences, verbose=verbose
                        )
                    )
                console.print(
                    "\nRemove the conflicting override to use the saved workspace "
                    "settings, or use --fresh to start a new conversion."
                )
            elif validation.reason == "legacy-generation-identity-unverifiable":
                console.print(
                    "[red]Saved conversion cannot be resumed:[/red] the version-6 "
                    "workspace does not contain enough generation identity data "
                    "for safe verification.\n"
                    "Existing paragraph WAVs and state were preserved. Use --fresh "
                    "only if you intend to discard this workspace."
                )
            else:
                console.print(
                    "[red]Saved conversion cannot be resumed:[/red] "
                    f"{validation.reason}. Use --fresh to restart."
                )
            raise typer.Exit(code=2)

    # Show resume summary when a strongly validated candidate was found.
    if resume_candidate is not None:
        state = resume_candidate.state
        completed = state.get_completed_count()
        total = len(state.chapters)
        next_idx = state.get_next_incomplete_index()
        # Find user-visible chapter number and title for the next incomplete
        next_chapter_num = ""
        next_chapter_title = ""
        if next_idx is not None:
            for pos, ch in enumerate(epub_chapters):
                if ch.index == next_idx:
                    next_chapter_num = str(pos + 1)
                    next_chapter_title = ch.title
                    break
        sel_start = min(selected_indices) + 1 if selected_indices else 1
        sel_end = max(selected_indices) + 1 if selected_indices else len(epub_chapters)
        console.print()
        console.print("[bold green]Found resumable conversion:[/bold green]")
        console.print(f"  Output: {resume_candidate.saved_output.name}")
        console.print(f"  Selection: chapters {sel_start}-{sel_end}")
        if state.conversion_unit == "paragraph":
            next_unit = state.get_next_incomplete_unit()
            next_text = ""
            if next_unit is not None:
                next_text = (
                    f"  Next unit: chapter {next_unit.chapter_position + 1}, "
                    f"paragraph {int(next_unit.chapter_unit_index or 0) + 1}\n"
                )
            console.print(
                f"  Conversion unit: Paragraph\n"
                f"  Completed units: {state.get_completed_unit_count()}/"
                f"{state.get_total_unit_count()}\n"
                f"{next_text.rstrip()}"
            )
        else:
            console.print(
                f"  Conversion unit: Chapter\n  Progress: {completed}/{total} complete"
            )
        if next_chapter_num:
            console.print(
                f"  Next: chapter {next_chapter_num} \u2014 {next_chapter_title}"
            )
        console.print()
        console.print("[dim]Resuming conversion...[/dim]")
        console.print()

    # Show conversion summary
    _show_conversion_summary(
        epub_file=epub_file,
        output=output,
        output_format=output_format or config.get("default_format", "m4b"),
        voice=voice or "af_bella",
        language=effective_language,
        speed=options.speed,
        onnx_provider=options.effective_onnx_provider(),
        model_source=model_source,
        model_variant=model_variant,
        model_quality=model_quality,
        num_chapters=len(selected_indices) if selected_indices else len(epub_chapters),
        conversion_unit=effective_conversion_unit,
        paragraphs_dir=(
            paragraph_directory(output)
            if effective_conversion_unit == "paragraph"
            else None
        ),
        title=effective_title,
        author=effective_author,
        lang=options.lang,
        use_spacy=options.use_spacy,
        spacy_model=options.spacy_model,
        spacy_model_size=options.spacy_model_size,
        use_mixed_language=options.use_mixed_language,
        mixed_language_primary=options.mixed_language_primary,
        mixed_language_allowed=options.mixed_language_allowed,
        mixed_language_confidence=options.mixed_language_confidence,
        random_seed=random_seed,
        detect_emphasis=effective_detect_emphasis,
        epub_content_mode=effective_epub_content_mode,
        ssmd_emphasis_mode=ssmd_policy.emphasis_mode,
        prosody_policy=effective_prosody_policy,
        short_sentence=_format_short_sentence_summary(
            effective_short_sentence,
            effective_enable_short_sentence,
            effective_language,
        ),
        short_sentence_note=_format_short_sentence_note(
            effective_short_sentence,
            effective_enable_short_sentence,
            effective_language,
        ),
        short_sentence_hint=_format_short_sentence_hint(
            effective_short_sentence,
            effective_enable_short_sentence,
            effective_language,
        ),
    )

    # Confirm
    if not yes:
        if not Confirm.ask("Proceed with conversion?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Handle --fresh flag: delete existing progress using the correct
    # source-hashed workspace path.
    if fresh:
        import shutil

        from ..conversion import resolve_conversion_workspace

        workspace = resolve_conversion_workspace(
            output_dir=output.parent,
            book_title=effective_title,
            source_file=epub_file,
        )
        if effective_conversion_unit == "paragraph":
            ensure_owned_directory(
                paragraph_directory(output),
                ownership={
                    "schema_version": 1,
                    "workspace_id": workspace.work_dir.name,
                    "source_hash": workspace.source_hash,
                    "output_path": str(output.resolve()),
                    "conversion_unit": "paragraph",
                },
                fresh=True,
            )
        if workspace.work_dir.exists():
            console.print(
                f"[yellow]Removing previous progress:[/yellow] {workspace.work_dir}"
            )
            shutil.rmtree(workspace.work_dir)
        # Fresh start means we don't try to resume
        resume = False

    # Set up progress display
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    task_id: TaskID | None = None
    current_chapter_text = ""

    def progress_callback(prog: ConversionProgress) -> None:
        nonlocal task_id, current_chapter_text
        if task_id is not None:
            progress.update(task_id, completed=prog.chars_processed)
            ch = prog.current_chapter
            total = prog.total_chapters
            current_chapter_text = f"Chapter {ch}/{total}: {prog.chapter_name}"
            if prog.unit_kind == "title":
                current_chapter_text = (
                    f"Chapter {ch}/{total} · Title: {prog.chapter_name}"
                )
            elif prog.unit_kind:
                current_chapter_text = (
                    f"Chapter {ch}/{total} · Paragraph {prog.current_paragraph}/"
                    f"{prog.paragraphs_in_chapter}: {prog.chapter_name}"
                )
            progress.update(task_id, description=current_chapter_text[:50])

    def log_callback(message: str, level: str) -> None:
        if verbose:
            if level == "error":
                console.print(f"[red]{message}[/red]")
            elif level == "warning":
                console.print(f"[yellow]{message}[/yellow]")
            else:
                console.print(f"[dim]{message}[/dim]")

    # Calculate total characters for progress
    total_chars = sum(
        ch.char_count
        for i, ch in enumerate(epub_chapters)
        if selected_indices is None or i in selected_indices
    )

    # Filter chapters if selection provided
    if selected_indices:
        filtered_chapters = [
            ch for i, ch in enumerate(epub_chapters) if i in selected_indices
        ]
    else:
        filtered_chapters = epub_chapters

    # Convert input_reader.Chapter to conversion.Chapter
    chapters_to_convert: list[Chapter] = []
    for ch in filtered_chapters:
        chapters_to_convert.append(
            Chapter(
                title=ch.title,
                content=ch.text,
                index=ch.index,
                markdown_body=ch.markdown_body,
                source_format=ch.source_format,
                source_id=ch.source_id,
                parent_id=ch.parent_id,
                level=ch.level,
                extraction_schema=ch.extraction_schema,
                extraction_diagnostics=ch.extraction_diagnostics,
                is_ssmd=ch.is_ssmd,
            )
        )

    with TTSConverter(
        options=options,
        progress_callback=progress_callback,
        log_callback=log_callback,
    ) as converter:
        with progress:
            task_id = progress.add_task("Converting...", total=total_chars)

            result = converter.convert_chapters_resumable(
                chapters=chapters_to_convert,
                output_path=output,
                source_file=epub_file,
                resume=resume,
                resume_mismatch=("error" if resume_candidate is not None else "fresh"),
            )

            progress.update(task_id, completed=total_chars)

    # Show result
    if result.success:
        console.print()
        if generate_ssmd_only:
            console.print(
                Panel(
                    f"[green]SSMD files generated in:[/green]\n{result.chapters_dir}",
                    title="[bold green]SSMD Generation Complete[/bold green]",
                )
            )
        else:
            console.print(
                Panel(
                    "[green]Audiobook saved to:[/green]\n"
                    f"{result.output_path}\n"
                    + (
                        f"\n[green]Paragraph output:[/green]\n{result.paragraphs_dir}\n"
                        if result.paragraphs_dir is not None
                        else ""
                    )
                    + "\n"
                    "[bold]Short sentence handling:[/bold] "
                    f"{format_short_sentence_stats(result.short_sentence_stats)}",
                    title="[bold green]Conversion Complete[/bold green]",
                )
            )
    else:
        console.print()
        console.print(
            Panel(
                f"[red]{result.error_message}[/red]",
                title="[bold red]Conversion Failed[/bold red]",
            )
        )
        sys.exit(1)


def list_chapters(epub_file: Path) -> None:
    """List chapters in a file.

    EPUB_FILE is the path to the file (EPUB, TXT, or SSMD).
    """
    from ..input_reader import InputReader

    with console.status("Loading file..."):
        try:
            reader = InputReader(epub_file)
            chapters = reader.get_chapters()
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not chapters:
        console.print("[yellow]No chapters found in file.[/yellow]")
        return

    table = Table(title=f"Chapters in {epub_file.name}")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold")
    table.add_column("Characters", justify="right")

    total_chars = 0
    for i, ch in enumerate(chapters, 1):
        char_count = ch.char_count
        total_chars += char_count
        table.add_row(str(i), ch.title[:60], f"{char_count:,}")

    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {len(chapters)} chapters, {total_chars:,} characters"
    )


def info(epub_file: Path) -> None:
    """Show metadata and information about a file.

    EPUB_FILE is the path to the file (EPUB, TXT, or SSMD).
    """
    from ..input_reader import InputReader

    # Parse file
    with console.status("Loading file..."):
        try:
            reader = InputReader(epub_file)
            metadata = reader.get_metadata()
            chapters = reader.get_chapters()
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    total_chars = sum(ch.char_count for ch in chapters) if chapters else 0

    # Display info
    console.print(Panel(f"[bold]{epub_file.name}[/bold]", title="File Information"))

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    if metadata:
        if metadata.title:
            table.add_row("Title", metadata.title)
        if metadata.authors:
            table.add_row("Author", ", ".join(metadata.authors))
        if metadata.language:
            lang = metadata.language
            lang_desc = LANGUAGE_DESCRIPTIONS.get(detect_language_from_iso(lang), lang)
            table.add_row("Language", f"{lang} ({lang_desc})")
        if metadata.publisher:
            table.add_row("Publisher", metadata.publisher)
        if metadata.publication_year:
            table.add_row("Year", str(metadata.publication_year))

    table.add_row("Chapters", str(len(chapters)) if chapters else "0")
    table.add_row("Characters", f"{total_chars:,}")
    table.add_row("File Size", format_size(epub_file.stat().st_size))

    console.print(table)


def sample(
    ctx: typer.Context,
    text: str | None,
    output: Path | None,
    output_format: str,
    voice: str | None,
    language: str | None,
    lang: str | None,
    speed: float | None,
    random_seed: int | None,
    use_gpu: bool | None,
    provider: str | None,
    split_mode: str | None,
    play_audio: bool,
    verbose: bool,
    use_mixed_language: bool,
    mixed_language_primary: str | None,
    mixed_language_allowed: str | None,
    mixed_language_confidence: float | None,
    phoneme_dictionary_path: str | None,
    phoneme_dict_case_sensitive: bool,
) -> None:
    """Generate a sample audio file to test TTS settings.

    If no TEXT is provided, uses a default sample text.

    Examples:

        ttsforge sample

        ttsforge sample "Hello, this is a test."

        ttsforge sample --voice am_adam --speed 1.2 -o test.wav

        ttsforge sample --play  # Play directly without saving

        ttsforge sample --play -o test.wav  # Play and save to file
    """

    from ..conversion import ConversionOptions, TTSConverter

    # Get model path from global context
    model_path = ctx.obj.get("model_path") if ctx.obj else None
    voices_path = ctx.obj.get("voices_path") if ctx.obj else None

    # Use default text if none provided
    sample_text = text or DEFAULT_SAMPLE_TEXT

    # Handle output path for playback mode
    temp_dir: str | None = None
    save_output = output is not None or not play_audio

    if play_audio and output is None:
        # Create temp file for playback only
        temp_dir = tempfile.mkdtemp()
        output = Path(temp_dir) / "sample.wav"
        output_format = "wav"  # Force WAV for playback
    elif output is None:
        output = Path(f"./sample.{output_format}")
    elif output.suffix == "":
        # If no extension provided, add the format
        output = output.with_suffix(f".{output_format}")

    # Load config for defaults
    user_config = load_config()
    try:
        resolved_provider = resolve_onnx_provider(
            user_config, provider_override=provider, use_gpu_override=use_gpu
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    model_source, model_variant = _resolve_model_source_and_variant(user_config)
    model_quality = cast(
        ModelQuality, user_config.get("model_quality", DEFAULT_MODEL_QUALITY)
    )
    resolved_defaults = resolve_conversion_defaults(
        user_config,
        {
            "voice": voice,
            "language": language,
            "speed": speed,
            "split_mode": split_mode,
            "use_gpu": use_gpu,
            "onnx_provider": resolved_provider,
            "lang": lang,
        },
    )

    # Parse mixed_language_allowed from comma-separated string
    parsed_mixed_language_allowed = None
    if mixed_language_allowed:
        parsed_mixed_language_allowed = [
            lang_item.strip() for lang_item in mixed_language_allowed.split(",")
        ]

    # Auto-detect if voice is a blend
    voice_value = resolved_defaults["voice"]
    parsed_voice, parsed_voice_blend = parse_voice_parameter(voice_value)

    # Build conversion options (use ConversionOptions defaults if not specified)
    options = ConversionOptions(
        voice=parsed_voice or "af_bella",
        voice_blend=parsed_voice_blend,
        language=resolved_defaults["language"],
        speed=resolved_defaults["speed"],
        random_seed=random_seed,
        output_format=output_format,
        use_gpu=resolved_defaults["use_gpu"],
        onnx_provider=resolved_provider,
        split_mode=resolved_defaults["split_mode"],
        lang=resolved_defaults["lang"],
        model_quality=model_quality,
        model_source=model_source,
        model_variant=model_variant,
        use_mixed_language=(
            use_mixed_language or user_config.get("use_mixed_language", False)
        ),
        mixed_language_primary=(
            mixed_language_primary or user_config.get("mixed_language_primary")
        ),
        mixed_language_allowed=(
            parsed_mixed_language_allowed or user_config.get("mixed_language_allowed")
        ),
        mixed_language_confidence=(
            mixed_language_confidence
            if mixed_language_confidence is not None
            else user_config.get("mixed_language_confidence", 0.7)
        ),
        phoneme_dictionary_path=(
            phoneme_dictionary_path or user_config.get("phoneme_dictionary_path")
        ),
        phoneme_dict_case_sensitive=(
            phoneme_dict_case_sensitive
            or user_config.get("phoneme_dict_case_sensitive", False)
        ),
        model_path=model_path,
        voices_path=voices_path,
    )

    # Always show settings
    if options.voice_blend:
        console.print(f"[dim]Voice Blend:[/dim] {options.voice_blend}")
    else:
        console.print(f"[dim]Voice:[/dim] {options.voice}")
    lang_desc = LANGUAGE_DESCRIPTIONS.get(options.language, "Unknown")
    console.print(f"[dim]Language:[/dim] {options.language} ({lang_desc})")
    if options.lang:
        console.print(f"[dim]Phonemization Lang:[/dim] {options.lang} (override)")
    console.print(f"[dim]Speed:[/dim] {options.speed}")
    console.print(f"[dim]Format:[/dim] {options.output_format}")
    console.print(f"[dim]Split mode:[/dim] {options.split_mode}")
    console.print(f"[dim]ONNX Provider:[/dim] {options.effective_onnx_provider()}")

    if verbose:
        text_preview = sample_text[:100]
        ellipsis = "..." if len(sample_text) > 100 else ""
        console.print(f"[dim]Text:[/dim] {text_preview}{ellipsis}")
        if save_output:
            console.print(f"[dim]Output:[/dim] {output}")

    try:
        with TTSConverter(options) as converter:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Generating audio...", total=None)
                result = converter.convert_text(sample_text, output)

        if result.success:
            # Handle playback if requested
            if play_audio:
                import sounddevice as sd
                import soundfile as sf

                audio_data, sample_rate = sf.read(str(output))
                console.print("[dim]Playing audio...[/dim]")
                sd.play(audio_data, sample_rate)
                sd.wait()
                console.print("[green]Playback complete.[/green]")

            # Report save location (if not temp file)
            if save_output:
                console.print(f"[green]Sample saved to:[/green] {output}")

            # Cleanup temp file if needed
            if temp_dir is not None:
                import shutil

                shutil.rmtree(temp_dir)
        else:
            console.print(f"[red]Error:[/red] {result.error_message}")
            raise SystemExit(1)

    except Exception as e:
        console.print(f"[red]Error generating sample:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        # Cleanup temp dir on error
        if temp_dir is not None:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
        raise SystemExit(1) from None


def _interactive_chapter_selection(chapters: list) -> list[int] | None:
    """Interactive chapter selection using Rich."""
    console.print("\n[bold]Available Chapters:[/bold]")

    table = Table(show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title")
    table.add_column("Chars", justify="right")

    for i, ch in enumerate(chapters, 1):
        table.add_row(str(i), ch.title[:50], f"{ch.char_count:,}")

    console.print(table)

    console.print("\n[dim]Enter chapter selection:[/dim]")
    console.print("[dim]  - 'all' for all chapters[/dim]")
    console.print("[dim]  - '1-5' for range[/dim]")
    console.print("[dim]  - '1,3,5' for specific chapters[/dim]")
    console.print("[dim]  - Press Enter for all chapters[/dim]")

    selection = console.input("\n[bold]Selection:[/bold] ").strip()

    if not selection:
        return None  # All chapters

    try:
        return parse_chapter_selection(selection, len(chapters))
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return []


def _show_conversion_summary(
    epub_file: Path,
    output: Path,
    output_format: str,
    voice: str,
    language: str,
    speed: float,
    onnx_provider: str,
    model_source: str,
    model_variant: str,
    model_quality: str | None,
    num_chapters: int,
    title: str,
    author: str,
    conversion_unit: str = "chapter",
    paragraphs_dir: Path | None = None,
    lang: str | None = None,
    use_spacy: bool | None = None,
    spacy_model: str | None = None,
    spacy_model_size: str | None = None,
    use_mixed_language: bool = False,
    mixed_language_primary: str | None = None,
    mixed_language_allowed: list[str] | None = None,
    mixed_language_confidence: float = 0.7,
    random_seed: int | None = None,
    detect_emphasis: bool = False,
    epub_content_mode: str = "markdown",
    ssmd_emphasis_mode: str = "plain",
    prosody_policy: ProsodyPolicy = _DEFAULT_PROSODY_POLICY,
    short_sentence: str = DEFAULT_SHORT_SENTENCE,
    short_sentence_note: str | None = None,
    short_sentence_hint: str | None = None,
) -> None:
    """Show conversion summary before starting."""
    console.print()

    table = Table(title="Conversion Summary", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Input", str(epub_file))
    table.add_row("Output", str(output))
    table.add_row("Format", output_format.upper())
    table.add_row("Chapters", str(num_chapters))
    table.add_row(
        "Conversion unit",
        "Paragraph WAV per paragraph" if conversion_unit == "paragraph" else "Chapter",
    )
    if paragraphs_dir is not None:
        table.add_row("Paragraph output", paragraphs_dir.name)
        table.add_row("Filename order", "Fixed-width global sequence")
    table.add_row("Voice", voice)
    table.add_row("Language", LANGUAGE_DESCRIPTIONS.get(language, language))
    table.add_row("Model Source", model_source)
    table.add_row("Model Variant", model_variant)
    table.add_row("Model Quality", str(model_quality))
    if lang:
        table.add_row("Phonemization Lang", f"{lang} (override)")
    if use_spacy is False:
        table.add_row("spaCy request", "Disabled")
    elif spacy_model:
        table.add_row("spaCy request", f"Exact {spacy_model}")
    elif spacy_model_size:
        table.add_row("spaCy request", f"Exact {spacy_model_size} tier")
    else:
        table.add_row("spaCy request", "Automatic, highest installed")
    if use_mixed_language:
        table.add_row("Mixed-Language", "Enabled")
        if mixed_language_primary:
            table.add_row("  Primary Lang", mixed_language_primary)
        if mixed_language_allowed:
            table.add_row("  Allowed Langs", ", ".join(mixed_language_allowed))
        table.add_row("  Confidence", f"{mixed_language_confidence:.2f}")
    table.add_row("Speed", f"{speed}x")
    is_markdown = epub_content_mode == "markdown"
    table.add_row(
        "EPUB Content Extraction",
        "Markdown" if is_markdown else "Plain (compatibility)",
    )
    table.add_row(
        "EPUB Headings/Scene Breaks",
        "Preserved" if is_markdown else "Legacy plain path",
    )
    table.add_row(
        "EPUB Emphasis Markup",
        "Preserved" if is_markdown and detect_emphasis else "Unwrapped",
    )
    table.add_row("EPUB CSS Emphasis", "Enabled" if is_markdown else "Not used")
    emphasis_labels = {
        "plain": "Plain (emphasis unchanged)",
        "approximate": "Approximate (gain-only)",
        "warn": "Plain + warnings",
        "error": "Reject emphasis",
    }
    table.add_row(
        "SSMD Emphasis",
        emphasis_labels.get(ssmd_emphasis_mode, ssmd_emphasis_mode),
    )
    method_labels = {
        "phase_vocoder": "Phase vocoder",
        "wsola": "WSOLA",
        "esola": "ESOLA",
        "td_psola": "TD-PSOLA",
        "psola": "PSOLA (AudioSig: td_psola)",
    }
    table.add_row(
        "SSMD Prosody Method",
        method_labels.get(prosody_policy.method, prosody_policy.method),
    )
    table.add_row(
        "Prosody Fallbacks",
        " -> ".join(
            method_labels.get(method, method)
            for method in prosody_policy.fallback_methods
        )
        or "None",
    )
    table.add_row(
        "Prosody Strict Mode", "Enabled" if prosody_policy.strict else "Disabled"
    )
    table.add_row("Prosody Clipping", "Enabled" if prosody_policy.clip else "Disabled")
    table.add_row("Prosody FFT Size", str(prosody_policy.n_fft))
    table.add_row(
        "Prosody Hop Length",
        "Automatic"
        if prosody_policy.hop_length is None
        else str(prosody_policy.hop_length),
    )
    table.add_row("Prosody Filter Width", str(prosody_policy.filter_width))
    table.add_row("Prosody Rolloff", str(prosody_policy.rolloff))
    table.add_row(
        "Boundary Blend",
        f"{prosody_policy.boundary_blend_ms} ms",
    )
    if random_seed is not None:
        table.add_row("Seed", str(random_seed))
    table.add_row("Short Sentence", short_sentence)
    if short_sentence_note:
        table.add_row("Short Sentence Note", short_sentence_note)
    table.add_row("ONNX Provider", onnx_provider)
    table.add_row("Title", title)
    table.add_row("Author", author)

    console.print(table)
    if short_sentence_hint:
        console.print(f"[yellow]Hint: {short_sentence_hint}[/yellow]")
    if ssmd_emphasis_mode == "approximate":
        console.print(
            "[dim]The current emphasis approximation changes gain only, so "
            "the selected prosody method is used only for "
            "SSMD rate or pitch annotations.[/dim]"
        )
    console.print()


def _format_short_sentence_summary(
    short_sentence: str | None,
    enable_short_sentence: bool | None,
    language_code: str | None,
) -> str:
    """Return the applied short-sentence config as a CLI-compatible value."""
    if enable_short_sentence is False:
        return "off"

    resolved = resolve_short_sentence_config(
        short_sentence, language_code=language_code
    )
    if resolved is None or not resolved.enabled or resolved.resolve_mode is False:
        return "off"

    mode = str(resolved.resolve_mode)
    mode_value = "randomized" if mode == "randomized-phrase" else mode
    parts: list[tuple[str, object]] = [
        ("mode", mode_value),
        ("threshold", resolved.min_phoneme_length),
    ]

    mode_config = resolved.resolve_modes.get(mode)
    selection = getattr(mode_config, "phrase_selection", None)
    if selection is not None:
        parts.append(("selection", selection))
        parts.append(("max-tries", resolved.phrase_fallback_tries))

    if mode == "wrap":
        parts.append(("pretext", resolved.phoneme_pretext))

    return ",".join(f"{key}={_short_sentence_cli_value(value)}" for key, value in parts)


def _short_sentence_cli_value(value: object) -> str:
    text = str(value)
    if "," not in text and '"' not in text:
        return text
    return '"' + text.replace('"', '""') + '"'


def _format_short_sentence_note(
    short_sentence: str | None,
    enable_short_sentence: bool | None,
    language_code: str | None,
) -> str | None:
    if enable_short_sentence is False:
        return None
    return short_sentence_fallback_note(
        short_sentence,
        language_code=language_code,
    )


def _format_short_sentence_hint(
    short_sentence: str | None,
    enable_short_sentence: bool | None,
    language_code: str | None,
) -> str | None:
    if enable_short_sentence is False:
        return None
    # phrase short-sentence handling currently only supports english.
    if language_code not in {"a", "b"}:
        return None
    resolved = resolve_short_sentence_config(
        short_sentence, language_code=language_code
    )
    if resolved is None or not resolved.enabled or resolved.resolve_mode is False:
        return None
    return (
        "If some words in shorter sentences sound slightly distorted, try "
        "increasing the short-sentence threshold or max-retries, though it might "
        "negatively impact the generation speed. "
        "--short-sentence 'threshold=40,max-tries=10'"
    )


def _validate_short_sentence_or_abort(
    short_sentence: str | None,
    enable_short_sentence: bool | None,
) -> None:
    if enable_short_sentence is False:
        return
    errors = validate_short_sentence_config(short_sentence)
    if errors:
        raise typer.BadParameter("Invalid short-sentence config: " + "; ".join(errors))


def read(  # noqa: C901
    ctx: typer.Context,
    input_file: Path | None,
    voice: str | None,
    language: str | None,
    speed: float | None,
    use_gpu: bool | None,
    provider: str | None,
    content_mode: str | None,
    chapters: str | None,
    pages: str | None,
    start_chapter: int | None,
    start_page: int | None,
    page_size: int | None,
    resume: bool,
    list_content: bool,
    split_mode: str | None,
    pause_clause: float | None,
    pause_sentence: float | None,
    pause_paragraph: float | None,
    pause_variance: float | None,
    random_seed: int | None,
    pause_mode: str | None,
    enable_short_sentence: bool | None,
    short_sentence: str | None,
) -> None:
    """Read an EPUB or text file aloud with streaming playback.

    Streams audio in real-time without creating output files.
    Supports chapter/page selection, position saving, and resume.

    \b
    Examples:
        ttsforge read book.epub
        ttsforge read book.epub --chapters "1-5"
        ttsforge read book.epub --mode pages --pages "1-50"
        ttsforge read book.epub --mode pages --start-page 10
        ttsforge read book.epub --start-chapter 3
        ttsforge read book.epub --resume
        ttsforge read book.epub --split sentence
        ttsforge read book.epub --list
        ttsforge read story.txt
        cat story.txt | ttsforge read -

    \b
    Controls:
        Ctrl+C - Stop reading (position is saved for resume)
    """
    import random
    import signal
    import sys
    import time

    from pykokoro import GenerationConfig, KokoroPipeline, PipelineConfig
    from pykokoro.onnx_backend import LANG_CODE_TO_ONNX, Kokoro
    from pykokoro.stages.audio_generation.onnx import OnnxAudioGenerationAdapter
    from pykokoro.stages.audio_postprocessing.onnx import OnnxAudioPostprocessingAdapter
    from pykokoro.stages.phoneme_processing.onnx import OnnxPhonemeProcessorAdapter

    from ..audio_player import (
        PlaybackPosition,
        clear_playback_position,
        load_playback_position,
        save_playback_position,
    )

    # Get model path from global context
    model_path = ctx.obj.get("model_path") if ctx.obj else None
    voices_path = ctx.obj.get("voices_path") if ctx.obj else None

    # Load config for defaults
    config = load_config()
    try:
        effective_read_prosody_policy = _resolve_prosody_policy(config)
    except (TypeError, ValueError) as exc:
        console.print(f"[red]Invalid prosody configuration:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    try:
        resolved_provider = resolve_onnx_provider(
            config, provider_override=provider, use_gpu_override=use_gpu
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    model_source, model_variant = _resolve_model_source_and_variant(config)
    model_quality = cast(
        ModelQuality, config.get("model_quality", DEFAULT_MODEL_QUALITY)
    )
    text_postprocess_options = resolve_text_postprocess_options(config)
    resolved_defaults = resolve_conversion_defaults(
        config,
        {
            "voice": voice,
            "language": language,
            "speed": speed,
            "split_mode": split_mode,
            "use_gpu": use_gpu,
            "onnx_provider": resolved_provider,
            "lang": None,
        },
    )
    effective_voice = resolved_defaults["voice"]
    effective_language = resolved_defaults["language"]
    effective_speed = resolved_defaults["speed"]
    effective_onnx_provider = resolved_provider
    # Content mode: chapters or pages
    effective_content_mode = content_mode or config.get(
        "default_content_mode", "chapters"
    )
    effective_page_size = page_size or config.get("default_page_size", 2000)
    # Use default_split_mode from config, map "auto" to "sentence" for streaming
    config_split_mode = resolved_defaults["split_mode"]
    # Map auto/clause/line to sentence for the read command
    if config_split_mode in ("auto", "clause", "line"):
        effective_split_mode = "sentence"
    else:
        effective_split_mode = config_split_mode
    # Pause settings
    effective_pause_clause = (
        pause_clause if pause_clause is not None else config.get("pause_clause", 0.3)
    )
    effective_pause_sentence = (
        pause_sentence
        if pause_sentence is not None
        else config.get("pause_sentence", 0.5)
    )
    effective_pause_paragraph = (
        pause_paragraph
        if pause_paragraph is not None
        else config.get("pause_paragraph", 0.9)
    )
    effective_pause_variance = (
        pause_variance
        if pause_variance is not None
        else config.get("pause_variance", 0.05)
    )
    effective_pause_mode = (
        pause_mode if pause_mode is not None else config.get("pause_mode", "auto")
    )
    effective_enable_short_sentence = (
        enable_short_sentence
        if enable_short_sentence is not None
        else config.get("enable_short_sentence", None)
    )
    effective_short_sentence_config = resolve_short_sentence_config(
        short_sentence if short_sentence is not None else config.get("short_sentence"),
        warn=lambda message: console.print(f"[yellow]Warning:[/yellow] {message}"),
    )

    # Get language code for TTS
    espeak_lang = LANG_CODE_TO_ONNX.get(effective_language, "en-us")

    # Validate conflicting options
    if effective_content_mode == "chapters" and (pages or start_page):
        console.print(
            "[yellow]Warning:[/yellow] --pages/--start-page ignored in chapters mode. "
            "Use --mode pages to read by pages."
        )
    if effective_content_mode == "pages" and (chapters or start_chapter):
        console.print(
            "[yellow]Warning:[/yellow] --chapters/--start-chapter ignored in "
            "pages mode. Use --mode chapters to read by chapters."
        )

    # Handle stdin input
    content_data: list[ContentItem]
    if input_file is None or str(input_file) == "-":
        if sys.stdin.isatty():
            console.print(
                "[red]Error:[/red] No input provided. Provide a file or pipe text."
            )
            console.print("[dim]Usage: ttsforge read book.epub[/dim]")
            console.print("[dim]       cat story.txt | ttsforge read -[/dim]")
            sys.exit(1)

        # Read from stdin
        text_content = postprocess_extracted_text(
            sys.stdin.read().strip(),
            text_postprocess_options,
        )
        if not text_content:
            console.print("[red]Error:[/red] No text received from stdin.")
            sys.exit(1)

        # Create a simple structure for stdin text
        content_data = [
            cast(ContentItem, {"title": "Text", "text": text_content, "index": 0})
        ]
        file_identifier = "stdin"
        content_label = "section"  # Generic label for stdin
    else:
        # Validate file exists; stdin skips Typer's exists=True path validation.
        if not input_file.exists():
            console.print(f"[red]Error:[/red] File not found: {input_file}")
            sys.exit(1)

        file_identifier = str(input_file.resolve())

        # Handle different file types using InputReader
        try:
            from ..input_reader import InputReader

            reader = InputReader(
                input_file,
                postprocess_options=text_postprocess_options,
            )
            metadata = reader.get_metadata()
        except Exception as e:
            console.print(f"[red]Error loading file:[/red] {e}")
            sys.exit(1)

        # Show book info
        title = metadata.title or input_file.stem
        author = metadata.authors[0] if metadata.authors else "Unknown"
        console.print(f"[bold]{title}[/bold] by {author}")

        # For EPUB files, check if we can use pages mode
        if input_file.suffix.lower() == ".epub":
            # Load content based on mode (chapters or pages)
            if effective_content_mode == "pages":
                try:
                    from epub2text import EPUBParser

                    parser = EPUBParser(str(input_file))
                    epub_pages = parser.get_pages(
                        synthetic_page_size=effective_page_size
                    )
                except Exception as e:
                    console.print(f"[red]Error loading pages:[/red] {e}")
                    sys.exit(1)

                if not epub_pages:
                    console.print("[red]Error:[/red] No pages found in EPUB file.")
                    sys.exit(1)

                # Check if using native or synthetic pages
                has_native = parser.has_page_list()
                page_type = "native" if has_native else "synthetic"
                console.print(f"[dim]{len(epub_pages)} pages ({page_type})[/dim]")

                # Convert to our format
                content_data = [
                    cast(
                        ContentItem,
                        {
                            "title": f"Page {p.page_number}",
                            "text": postprocess_extracted_text(
                                p.text,
                                text_postprocess_options,
                            ),
                            "index": i,
                            "page_number": p.page_number,
                        },
                    )
                    for i, p in enumerate(epub_pages)
                ]
                content_label = "page"
            else:
                # Default: chapters mode
                epub_chapters = reader.get_chapters()

                if not epub_chapters:
                    console.print("[red]Error:[/red] No chapters found in file.")
                    sys.exit(1)

                console.print(f"[dim]{len(epub_chapters)} chapters[/dim]")

                content_data = [
                    cast(
                        ContentItem,
                        {
                            "title": ch.title or f"Chapter {i + 1}",
                            "text": ch.text,
                            "index": i,
                        },
                    )
                    for i, ch in enumerate(epub_chapters)
                ]
                content_label = "chapter"

        elif input_file.suffix.lower() in (".txt", ".text", ".ssmd"):
            # Plain text file - use InputReader's chapters
            text_chapters = reader.get_chapters()

            if not text_chapters:
                console.print("[red]Error:[/red] No content found in file.")
                sys.exit(1)

            # If it's a single chapter, use it as-is
            # If multiple chapters detected, use them
            content_data = [
                cast(
                    ContentItem,
                    {
                        "title": ch.title or input_file.stem,
                        "text": ch.text,
                        "index": i,
                    },
                )
                for i, ch in enumerate(text_chapters)
            ]
            content_label = "chapter" if len(text_chapters) > 1 else "section"
        else:
            console.print(
                f"[red]Error:[/red] Unsupported file type: {input_file.suffix}"
            )
            console.print("[dim]Supported formats: .epub, .txt[/dim]")
            sys.exit(1)

    # List content and exit if requested
    if list_content:
        console.print()
        for item in content_data:
            idx = item["index"] + 1
            item_title = item["title"]
            text_preview = item["text"][:80].replace("\n", " ").strip()
            if len(item["text"]) > 80:
                text_preview += "..."
            console.print(f"[bold]{idx:3}.[/bold] {item_title}")
            console.print(f"     [dim]{text_preview}[/dim]")
        return

    # Content selection (chapters or pages)
    selected_indices: list[int] | None = None

    if effective_content_mode == "pages":
        # Page selection
        if pages:
            try:
                selected_indices = parse_chapter_selection(pages, len(content_data))
            except ValueError as exc:
                console.print(f"[yellow]{exc}[/yellow]")
                sys.exit(1)
        elif start_page:
            if start_page < 1 or start_page > len(content_data):
                console.print(
                    f"[red]Error:[/red] Invalid page number {start_page}. "
                    f"Valid range: 1-{len(content_data)}"
                )
                sys.exit(1)
            selected_indices = list(range(start_page - 1, len(content_data)))
    else:
        # Chapter selection
        if chapters:
            try:
                selected_indices = parse_chapter_selection(chapters, len(content_data))
            except ValueError as exc:
                console.print(f"[yellow]{exc}[/yellow]")
                sys.exit(1)
        elif start_chapter:
            if start_chapter < 1 or start_chapter > len(content_data):
                console.print(
                    f"[red]Error:[/red] Invalid chapter number {start_chapter}. "
                    f"Valid range: 1-{len(content_data)}"
                )
                sys.exit(1)
            selected_indices = list(range(start_chapter - 1, len(content_data)))

    # Handle resume
    start_segment_index = 0
    if resume:
        saved_position = load_playback_position()
        if saved_position and saved_position.file_path == file_identifier:
            # Resume from saved position
            resume_index = saved_position.chapter_index
            start_segment_index = saved_position.segment_index

            if selected_indices is None:
                selected_indices = list(range(resume_index, len(content_data)))
            else:
                # Filter to only include items from resume point
                selected_indices = [i for i in selected_indices if i >= resume_index]

            console.print(
                f"[yellow]Resuming from {content_label} {resume_index + 1}, "
                f"segment {start_segment_index + 1}[/yellow]"
            )
        else:
            console.print(
                "[dim]No saved position found for this file, "
                "starting from beginning.[/dim]"
            )

    # Final selection
    if selected_indices is None:
        selected_indices = list(range(len(content_data)))

    if not selected_indices:
        console.print(f"[yellow]No {content_label}s to read.[/yellow]")
        return

    console.print()
    lang_desc = LANGUAGE_DESCRIPTIONS.get(effective_language, effective_language)
    console.print(
        f"[dim]Voice: {effective_voice} | Language: {lang_desc} | "
        f"Speed: {effective_speed}x[/dim]"
    )
    console.print()

    # Initialize TTS pipeline
    console.print("[dim]Loading TTS model...[/dim]")
    kokoro = None
    pipeline = None
    try:
        kokoro = Kokoro(
            model_path=model_path,
            voices_path=voices_path,
            provider=effective_onnx_provider,
            use_gpu=False,
            short_sentence_config=effective_short_sentence_config,
            model_quality=model_quality,
            model_source=model_source,
            model_variant=model_variant,
        )
        generation = GenerationConfig(
            speed=effective_speed,
            lang=espeak_lang,
            pause_mode=cast(Literal["tts", "manual", "auto"], effective_pause_mode),
            enable_short_sentence=effective_enable_short_sentence,
            pause_clause=effective_pause_clause,
            pause_sentence=effective_pause_sentence,
            pause_paragraph=effective_pause_paragraph,
            pause_variance=effective_pause_variance,
            random_seed=random_seed,
        )
        pipeline_config = PipelineConfig(
            voice=effective_voice,
            generation=generation,
            model_quality=model_quality,
            model_source=model_source,
            model_variant=model_variant,
            model_path=model_path,
            voices_path=voices_path,
            short_sentence_config=effective_short_sentence_config,
            prosody=build_pykokoro_prosody_config(effective_read_prosody_policy),
            retain_segment_audio=False,
        )
        pipeline = KokoroPipeline(
            pipeline_config,
            phoneme_processing=OnnxPhonemeProcessorAdapter(kokoro),
            audio_generation=OnnxAudioGenerationAdapter(kokoro),
            audio_postprocessing=OnnxAudioPostprocessingAdapter(kokoro),
        )
    except Exception as e:
        try:
            if pipeline is not None:
                pipeline.close()
        finally:
            if kokoro is not None:
                kokoro.close()
        console.print(f"[red]Error initializing TTS:[/red] {e}")
        sys.exit(1)

    # Track current position for saving
    current_content_idx = selected_indices[0]
    current_segment_idx = 0
    stop_requested = False

    def signal_handler(signum: int, frame: FrameType | None) -> None:
        """Handle Ctrl+C gracefully."""
        nonlocal stop_requested
        console.print("\n[yellow]Stopping... (position saved)[/yellow]")
        stop_requested = True

    # Set up signal handler
    original_handler = signal.signal(signal.SIGINT, signal_handler)

    try:
        import concurrent.futures

        import sounddevice as sd

        # Create a thread pool for TTS generation (1 worker for lookahead)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def generate_audio(text_segment: str) -> tuple[np.ndarray, int]:
            """Generate audio for a text segment."""
            result = pipeline.run(text_segment)
            samples = result.audio
            sample_rate = result.sample_rate
            try:
                return samples, sample_rate
            finally:
                result.release_audio()

        # Collect all segments across content items with their metadata
        all_segments: list[
            tuple[int, int, str, str]
        ] = []  # (content_idx, seg_idx, text, display)

        for content_position, content_idx in enumerate(selected_indices):
            content_item = content_data[content_idx]
            text = content_item["text"].strip()
            if not text:
                continue

            segments = _split_text_into_segments(text, split_mode=effective_split_mode)

            # Skip segments if resuming mid-content
            seg_offset = 0
            if content_position == 0 and start_segment_index > 0:
                segments = segments[start_segment_index:]
                seg_offset = start_segment_index

            for seg_idx, segment in enumerate(segments):
                actual_seg_idx = seg_idx + seg_offset
                # Clean up text for display (normalize whitespace)
                display_text = " ".join(segment.split())
                all_segments.append(
                    (content_idx, actual_seg_idx, segment, display_text)
                )

        if not all_segments:
            console.print("[yellow]No text to read.[/yellow]")
            return

        # Pre-generate first segment
        current_future = executor.submit(generate_audio, all_segments[0][2])
        next_future = None

        last_content_idx = -1

        for i, (content_idx, seg_idx, _segment_text, display_text) in enumerate(
            all_segments
        ):
            if stop_requested:
                break

            current_content_idx = content_idx
            current_segment_idx = seg_idx

            # Detect content change for paragraph pause
            content_changed = content_idx != last_content_idx

            # Show header when content item changes
            if content_changed:
                content_item = content_data[content_idx]
                console.print()
                label = content_label.capitalize()
                console.print(
                    f"[bold cyan]{label} {content_idx + 1}:[/bold cyan] "
                    f"{content_item['title']}"
                )
                console.print("-" * 60)
                if last_content_idx == -1 and start_segment_index > 0:
                    console.print(
                        f"[dim](resuming from segment {start_segment_index + 1})[/dim]"
                    )
                last_content_idx = content_idx

            # Display current segment
            console.print(f"[dim]{display_text}[/dim]")

            # Start generating next segment while we wait for current
            if i + 1 < len(all_segments):
                next_future = executor.submit(generate_audio, all_segments[i + 1][2])

            # Wait for current audio to be ready
            try:
                audio, sample_rate = current_future.result(timeout=60)
            except Exception as e:
                console.print(f"[red]TTS error:[/red] {e}")
                # Move to next segment's future
                if next_future:
                    current_future = next_future
                    next_future = None
                continue

            # Play audio
            if not stop_requested:
                sd.play(audio, sample_rate)
                sd.wait()

                # Add pause after segment (if not the last segment)
                if i + 1 < len(all_segments) and not stop_requested:
                    next_content_idx = all_segments[i + 1][0]
                    if next_content_idx != content_idx:
                        # Paragraph pause (between content items)
                        pause = effective_pause_paragraph + random.uniform(
                            -effective_pause_variance, effective_pause_variance
                        )
                    else:
                        # Segment pause (within content item)
                        pause = effective_pause_sentence + random.uniform(
                            -effective_pause_variance, effective_pause_variance
                        )
                    time.sleep(max(0, pause))  # Ensure non-negative

            # Swap futures: next becomes current
            if next_future:
                current_future = next_future
                next_future = None

        executor.shutdown(wait=False)

        # Finished
        if not stop_requested:
            # Clear saved position on successful completion
            clear_playback_position()
            console.print("\n[green]Finished reading.[/green]")
        else:
            # Save position for resume
            position = PlaybackPosition(
                file_path=file_identifier,
                chapter_index=current_content_idx,
                segment_index=current_segment_idx,
            )
            save_playback_position(position)
            label = content_label.capitalize()
            console.print(
                f"[dim]Position saved: {label} {current_content_idx + 1}, "
                f"Segment {current_segment_idx + 1}[/dim]"
            )
            console.print("[dim]Use --resume to continue from this position.[/dim]")

    except Exception as e:
        console.print(f"[red]Error during playback:[/red] {e}")
        # Save position on error too
        position = PlaybackPosition(
            file_path=file_identifier,
            chapter_index=current_content_idx,
            segment_index=current_segment_idx,
        )
        save_playback_position(position)
        raise
    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)
        try:
            if pipeline is not None:
                pipeline.close()
        finally:
            if kokoro is not None:
                kokoro.close()


def _split_text_into_segments(
    text: str, split_mode: str = "paragraph", max_length: int = 500
) -> list[str]:
    """Split text into readable segments for streaming.

    Args:
        text: Text to split
        split_mode: "sentence" for individual sentences, "paragraph" for grouped
        max_length: Maximum segment length (used for paragraph mode)

    Returns:
        List of text segments
    """

    # First split on sentence-ending punctuation
    sentence_pattern = r"(?<=[.!?])\s+"
    sentences = re.split(sentence_pattern, text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if split_mode == "sentence":
        # Return individual sentences, but split very long ones
        result = []
        for sentence in sentences:
            if len(sentence) > max_length:
                # Split long sentences on clause boundaries
                clause_parts = re.split(r"(?<=[,;:])\s+", sentence)
                for part in clause_parts:
                    part = part.strip()
                    if part:
                        result.append(part)
            else:
                result.append(sentence)
        return result

    # Paragraph mode: group sentences up to max_length
    segments = []
    current_segment = ""

    for sentence in sentences:
        # If adding this sentence would exceed max_length
        if len(current_segment) + len(sentence) + 1 > max_length:
            if current_segment:
                segments.append(current_segment.strip())

            # If single sentence is too long, split it further
            if len(sentence) > max_length:
                # Split on clause boundaries
                clause_parts = re.split(r"(?<=[,;:])\s+", sentence)
                for part in clause_parts:
                    part = part.strip()
                    if len(part) > max_length:
                        # Last resort: split at word boundaries
                        words = part.split()
                        sub_segment = ""
                        for word in words:
                            if len(sub_segment) + len(word) + 1 > max_length:
                                if sub_segment:
                                    segments.append(sub_segment.strip())
                                sub_segment = word
                            else:
                                sub_segment = (
                                    f"{sub_segment} {word}" if sub_segment else word
                                )
                        if sub_segment:
                            current_segment = sub_segment
                    else:
                        segments.append(part)
                current_segment = ""
            else:
                current_segment = sentence
        else:
            current_segment = (
                f"{current_segment} {sentence}" if current_segment else sentence
            )

    if current_segment.strip():
        segments.append(current_segment.strip())

    return [s for s in segments if s.strip()]
