"""Interactive synthesis setup tables and prompts for ``convert``."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import replace
from typing import TypeVar

import typer
from readio.api import (
    G2P_FALLBACKS,
    LEXICON_DATA_POLICIES,
    SHORT_SENTENCE_POLICIES,
    SPACY_POLICIES,
    VOICE_LEVEL_MODES,
    DiscoveryOptions,
    EngineInfo,
    LexiconInfo,
    ModelInfo,
    ProjectRef,
    SynthesisResolution,
    VoiceInfo,
)
from rich.console import Console

from ..audiobook import AudiobookConverter
from ..options import AudiobookOptions
from ..readio_backend import synthesis_request
from ..synthesis_setup import (
    CatalogSelectionError,
    CliPins,
    SetupSources,
    apply_lexicon_selection,
    choose_catalog_item,
    invalidate_dependency_sources,
    reset_dependency_choices,
)
from .catalog import (
    engine_item,
    lexicon_item,
    model_item,
    render_catalog_list,
    voice_item,
)

T = TypeVar("T")
PAUSE_MODES = ("auto", "tts", "manual")
SYNTHESIS_UNITS = ("sentence", "paragraph")


def _choice(prompt: str, default: str, choices: Sequence[str], console: Console) -> str:
    while True:
        value = str(
            typer.prompt(f"{prompt} ({'/'.join(choices)})", default=default)
        ).strip()
        if value in choices:
            return value
        console.print(f"Choose one of: {', '.join(choices)}.", style="red")


def _free_text(prompt: str, default: str) -> str:
    return str(typer.prompt(prompt, default=default)).strip()


def _catalog_choice(
    prompt: str,
    rows: Sequence[T],
    *,
    default: str | None,
    keys: Callable[[T], Collection[str]],
    console: Console,
) -> T | str:
    while True:
        value = typer.prompt(
            prompt, default=default or "", show_default=default is not None
        )
        try:
            return choose_catalog_item(
                value=value, rows=rows, default=default, keys=keys
            )
        except CatalogSelectionError as exc:
            console.print(str(exc), style="red")


def _prompt_speed(default: float, console: Console) -> float:
    while True:
        value = typer.prompt("Speed", default=f"{default:g}").strip()
        try:
            speed = float(value)
        except ValueError:
            console.print("Enter a number between 0.5 and 2.0.", style="red")
            continue
        if 0.5 <= speed <= 2.0:
            return speed
        console.print("Speed must be between 0.5 and 2.0.", style="red")


def _show_engines(rows: Sequence[EngineInfo], console: Console) -> None:
    render_catalog_list(
        console,
        title="Runnable Readio engines",
        items=tuple(engine_item(engine) for engine in rows),
    )


def _show_models(
    rows: Sequence[ModelInfo], language: str, engine: str, console: Console
) -> None:
    render_catalog_list(
        console,
        title=f"Available models for {language} / {engine}",
        items=tuple(model_item(model, engine=engine) for model in rows),
    )


def _voice_keys(voice: VoiceInfo) -> tuple[str, ...]:
    return tuple(
        value for value in (voice.selector, voice.id, voice.qualified_id) if value
    )


def _show_voices(
    rows: Sequence[VoiceInfo],
    language: str,
    engine: str,
    model: str | None,
    console: Console,
) -> None:
    title = f"Available voices for {language} / {engine}"
    if model:
        title += f" / {model}"
    render_catalog_list(
        console,
        title=title,
        items=tuple(voice_item(voice, engine=engine, model=model) for voice in rows),
    )


def _show_lexicons(rows: Sequence[LexiconInfo], console: Console) -> None:
    render_catalog_list(
        console,
        title="Available lexicons",
        items=tuple(lexicon_item(lexicon) for lexicon in rows),
    )


def _default_lexicon_input(value: tuple[str, ...] | None) -> str:
    if value is None:
        return "auto"
    if not value:
        return "none"
    return ",".join(value)


def _discovery_options(options: AudiobookOptions) -> DiscoveryOptions:
    return DiscoveryOptions(
        offline=options.offline,
        refresh=options.refresh,
        preference=options.model_source or "auto",
    )


def _choose_engine(
    converter: AudiobookConverter,
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    console: Console,
    reconfigure: bool = False,
) -> tuple[AudiobookOptions, str, EngineInfo | None]:
    all_engines = converter.engines()
    runnable_engines = tuple(engine for engine in all_engines if engine.runnable)
    if sources.prompt_required("engine", reconfigure=reconfigure):
        if len(runnable_engines) > 1:
            _show_engines(runnable_engines, console)
            selected = _catalog_choice(
                "Engine",
                runnable_engines,
                default=baseline.engine,
                keys=lambda item: (item.id,),
                console=console,
            )
            engine = selected.id if isinstance(selected, EngineInfo) else selected
            options = replace(options, engine=engine)
        elif len(runnable_engines) == 1:
            options = replace(options, engine=runnable_engines[0].id)
            console.print(f"Using Readio engine {runnable_engines[0].id}.")
        else:
            options = replace(options, engine=baseline.engine)
    engine = options.engine or baseline.engine
    engine_info = next((item for item in all_engines if item.id == engine), None)
    return options, engine, engine_info


def _choose_model(
    converter: AudiobookConverter,
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    console: Console,
    reconfigure: bool = False,
) -> tuple[AudiobookOptions, ModelInfo | None]:
    models = converter.models(
        language=language, engine=engine, discovery=discovery
    ).items
    selected_model_info = next(
        (item for item in models if item.id == options.model), None
    )
    if not sources.prompt_required("model", reconfigure=reconfigure):
        if selected_model_info is not None and sources.prompt_required(
            "model_source", reconfigure=reconfigure
        ):
            options = replace(options, model_source=selected_model_info.source)
        return options, selected_model_info

    if models:
        _show_models(models, language, engine, console)
    else:
        console.print(f"No catalog models matched {language} / {engine}.")
    selected_model = _catalog_choice(
        "Model",
        models,
        default=baseline.model,
        keys=lambda item: (item.id,),
        console=console,
    )
    model = (
        selected_model.id if isinstance(selected_model, ModelInfo) else selected_model
    )
    selected_model_info = (
        selected_model if isinstance(selected_model, ModelInfo) else None
    )
    if selected_model_info is not None and sources.prompt_required(
        "model_source", reconfigure=reconfigure
    ):
        options = replace(options, model=model, model_source=selected_model_info.source)
    else:
        options = replace(options, model=model)
    return options, selected_model_info


def _choose_quality(
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    qualities = model_info.qualities if model_info is not None else ()
    if not sources.prompt_required("quality", reconfigure=reconfigure) or not qualities:
        return options
    if len(qualities) == 1:
        return replace(options, quality=qualities[0])
    default = baseline.quality if baseline.quality in qualities else qualities[0]
    return replace(options, quality=_choice("Quality", default, qualities, console))


def _choose_voice(
    converter: AudiobookConverter,
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    if not sources.prompt_required("voice", reconfigure=reconfigure):
        return options
    voices = converter.voices(
        language=language,
        engine=engine,
        model=options.model,
        discovery=discovery,
    ).items
    if voices:
        _show_voices(voices, language, engine, options.model, console)
    else:
        model = options.model or "default"
        console.print(f"No catalog voices matched {language} / {engine} / {model}.")
    if baseline.voice and any(baseline.voice in _voice_keys(voice) for voice in voices):
        default_voice = baseline.voice
    else:
        default_voice = (
            model_info.default_voice
            if model_info is not None and model_info.default_voice
            else baseline.voice
        )
    selected = _catalog_choice(
        "Voice",
        voices,
        default=default_voice,
        keys=_voice_keys,
        console=console,
    )
    voice = selected.id if isinstance(selected, VoiceInfo) else selected
    return replace(options, voice=voice)


def _prompt_text_policies(
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    if sources.prompt_required("speed", reconfigure=reconfigure):
        options = replace(options, speed=_prompt_speed(baseline.speed, console))
    if sources.prompt_required("spacy", reconfigure=reconfigure):
        default_spacy = baseline.spacy if baseline.spacy in SPACY_POLICIES else "auto"
        options = replace(
            options,
            spacy=_choice("spaCy", default_spacy, SPACY_POLICIES, console),
        )
    if sources.prompt_required("short_sentence", reconfigure=reconfigure):
        default_short = (
            baseline.short_sentence
            if baseline.short_sentence in SHORT_SENTENCE_POLICIES
            else "phrase"
        )
        options = replace(
            options,
            short_sentence=_choice(
                "Short sentences",
                default_short,
                SHORT_SENTENCE_POLICIES,
                console,
            ),
        )
    return options


def _prompt_lexicon_options(
    converter: AudiobookConverter,
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    engine_info: EngineInfo | None,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    capabilities = engine_info.capabilities if engine_info is not None else None
    supports_lexicons = bool(
        capabilities is not None and capabilities.supports_lexicons
    )
    g2p_relevant = bool(
        (model_info is not None and model_info.g2p_backend) or supports_lexicons
    )
    if supports_lexicons and sources.prompt_required(
        "lexicons", reconfigure=reconfigure
    ):
        lexicons = converter.lexicons(
            language=language,
            engine=engine,
            model=options.model,
            discovery=discovery,
        ).items
        if lexicons:
            _show_lexicons(lexicons, console)
        else:
            console.print("No catalog lexicons matched this synthesis setup.")
        if options.auto_lexicons:
            default = "auto"
        elif options.clear_lexicons:
            default = "none"
        elif options.lexicons is not None:
            default = ",".join(options.lexicons) if options.lexicons else "none"
        else:
            default = _default_lexicon_input(baseline.lexicons)
        while True:
            value = typer.prompt("Lexicons", default=default).strip()
            try:
                return_options = apply_lexicon_selection(options, value, lexicons)
                break
            except CatalogSelectionError as exc:
                console.print(str(exc), style="red")
        options = return_options

    if g2p_relevant and sources.prompt_required(
        "g2p_fallback", reconfigure=reconfigure
    ):
        default_g2p = (
            baseline.g2p_fallback
            if baseline.g2p_fallback in G2P_FALLBACKS
            else "espeak"
        )
        options = replace(
            options,
            g2p_fallback=_choice("G2P fallback", default_g2p, G2P_FALLBACKS, console),
        )
    if (supports_lexicons or g2p_relevant) and sources.prompt_required(
        "lexicon_data_policy", reconfigure=reconfigure
    ):
        default_policy = (
            baseline.lexicon_data_policy
            if baseline.lexicon_data_policy in LEXICON_DATA_POLICIES
            else "auto"
        )
        options = replace(
            options,
            lexicon_data_policy=_choice(
                "Lexicon data",
                default_policy,
                LEXICON_DATA_POLICIES,
                console,
            ),
        )
    return options


def _prompt_voice_level(
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    engine_info: EngineInfo | None,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    capabilities = engine_info.capabilities if engine_info is not None else None
    if (
        capabilities is None
        or not capabilities.supports_voice_level_calibration
        or not sources.prompt_required("voice_level", reconfigure=reconfigure)
    ):
        return options
    default = (
        baseline.voice_level if baseline.voice_level in VOICE_LEVEL_MODES else "off"
    )
    return replace(
        options,
        voice_level=_choice("Voice level", default, VOICE_LEVEL_MODES, console),
    )


def _prompt_pause_and_unit(
    options: AudiobookOptions,
    sources: SetupSources,
    baseline: SynthesisResolution,
    console: Console,
    reconfigure: bool = False,
) -> AudiobookOptions:
    if sources.prompt_required("pause_mode", reconfigure=reconfigure):
        default_pause = (
            baseline.pause_mode if baseline.pause_mode in PAUSE_MODES else "auto"
        )
        options = replace(
            options,
            pause_mode=_choice("Pause mode", default_pause, PAUSE_MODES, console),
        )
    if sources.prompt_required("unit", reconfigure=reconfigure):
        default_unit = baseline.unit if baseline.unit in SYNTHESIS_UNITS else "sentence"
        options = replace(
            options,
            unit=_choice("Synthesis unit", default_unit, SYNTHESIS_UNITS, console),
        )
    return options


def configure_synthesis_interactively(
    *,
    converter: AudiobookConverter,
    project: ProjectRef,
    options: AudiobookOptions,
    sources: SetupSources | None = None,
    reconfigure: bool = False,
    pins: CliPins | None = None,
    console: Console,
) -> AudiobookOptions:
    """Prompt for unresolved or explicitly reconfigured setup fields."""
    if sources is None:
        sources = SetupSources(cli=pins.fields if pins is not None else frozenset())
    prompt_fields = (
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
        "voice_level",
        "pause_mode",
        "unit",
    )
    if not any(
        sources.prompt_required(field, reconfigure=reconfigure)
        for field in prompt_fields
    ):
        return options

    baseline = converter.resolve_synthesis(project, synthesis_request(options))
    pins = CliPins(sources.cli)
    previous_language = options.language or baseline.language
    if sources.prompt_required("language", reconfigure=reconfigure):
        options = replace(options, language=_free_text("Language", baseline.language))
        if options.language != previous_language:
            options = reset_dependency_choices(options, "language", pins)
            sources = invalidate_dependency_sources(sources, "language")
            baseline = converter.resolve_synthesis(project, synthesis_request(options))
    language = options.language or baseline.language

    previous_engine = options.engine or baseline.engine
    options, engine, engine_info = _choose_engine(
        converter, options, sources, baseline, console, reconfigure=reconfigure
    )
    if engine != previous_engine:
        options = reset_dependency_choices(options, "engine", pins)
        sources = invalidate_dependency_sources(sources, "engine")
        baseline = converter.resolve_synthesis(project, synthesis_request(options))
        engine = options.engine or baseline.engine

    discovery = _discovery_options(options)
    previous_model = options.model or baseline.model
    options, model_info = _choose_model(
        converter,
        options,
        sources,
        baseline,
        language,
        engine,
        discovery,
        console,
        reconfigure=reconfigure,
    )
    selected_model = options.model or baseline.model
    if selected_model != previous_model:
        options = reset_dependency_choices(options, "model", pins)
        sources = invalidate_dependency_sources(sources, "model")
        baseline = converter.resolve_synthesis(project, synthesis_request(options))

    options = _choose_quality(
        options, sources, baseline, model_info, console, reconfigure=reconfigure
    )
    discovery = _discovery_options(options)
    options = _choose_voice(
        converter,
        options,
        sources,
        baseline,
        model_info,
        language,
        engine,
        discovery,
        console,
        reconfigure=reconfigure,
    )
    options = _prompt_text_policies(
        options, sources, baseline, console, reconfigure=reconfigure
    )
    options = _prompt_lexicon_options(
        converter,
        options,
        sources,
        baseline,
        model_info,
        language,
        engine,
        discovery,
        engine_info,
        console,
        reconfigure=reconfigure,
    )
    options = _prompt_voice_level(
        options,
        sources,
        baseline,
        engine_info,
        console,
        reconfigure=reconfigure,
    )
    return _prompt_pause_and_unit(
        options, sources, baseline, console, reconfigure=reconfigure
    )
