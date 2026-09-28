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
from rich.table import Table

from ..audiobook import AudiobookConverter
from ..options import AudiobookOptions
from ..readio_backend import synthesis_request
from ..synthesis_setup import (
    CatalogSelectionError,
    CliPins,
    apply_lexicon_selection,
    choose_catalog_item,
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


def _engine_features(engine: EngineInfo) -> str:
    capabilities = engine.capabilities
    if capabilities is None:
        return ""
    features = []
    if capabilities.supports_named_voices:
        features.append("voices")
    if capabilities.supports_lexicons:
        features.append("lexicons")
    if capabilities.supports_model_sources:
        features.append("model sources")
    if capabilities.supports_qualities:
        features.append("qualities")
    if capabilities.supports_voice_level_calibration:
        features.append("voice level")
    return ", ".join(features)


def _show_engines(rows: Sequence[EngineInfo], console: Console) -> None:
    table = Table(title="Runnable Readio engines")
    table.add_column("#", no_wrap=True)
    table.add_column("Engine")
    table.add_column("Version")
    table.add_column("Runnable")
    table.add_column("Features", overflow="fold")
    for index, engine in enumerate(rows, 1):
        table.add_row(
            str(index),
            engine.id,
            engine.version or "—",
            "yes" if engine.runnable else "no",
            _engine_features(engine),
        )
    console.print(table)


def _show_models(
    rows: Sequence[ModelInfo], language: str, engine: str, console: Console
) -> None:
    table = Table(title=f"Available models for {language} / {engine}")
    table.add_column("#", no_wrap=True)
    table.add_column("Model", overflow="fold")
    table.add_column("Engine")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Runtime")
    table.add_column("Qualities", overflow="fold")
    table.add_column("Default voice", overflow="fold")
    table.add_column("G2P / lexicons", overflow="fold")
    for index, model in enumerate(rows, 1):
        resources = [model.g2p_backend or "—"]
        if model.lexicons:
            resources.append(", ".join(model.lexicons))
        table.add_row(
            str(index),
            model.id,
            model.backend,
            model.source or "—",
            model.status,
            "yes" if model.runtime_available else "no",
            ", ".join(model.qualities) or "—",
            model.default_voice or "—",
            " / ".join(resources),
        )
    console.print(table)


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
    table = Table(title=title)
    table.add_column("#", no_wrap=True)
    table.add_column("Voice", overflow="fold")
    table.add_column("Locale")
    table.add_column("Gender")
    table.add_column("Model", overflow="fold")
    table.add_column("Engine")
    table.add_column("Status")
    table.add_column("Runtime")
    table.add_column("Default")
    for index, voice in enumerate(rows, 1):
        table.add_row(
            str(index),
            voice.selector or voice.qualified_id,
            voice.locale,
            voice.gender or "—",
            voice.model or "—",
            voice.engine,
            voice.status,
            "yes" if voice.runtime_available else "no",
            "yes" if voice.default else "no",
        )
    console.print(table)


def _show_lexicons(rows: Sequence[LexiconInfo], console: Console) -> None:
    table = Table(title="Available lexicons")
    table.add_column("#", no_wrap=True)
    table.add_column("Selector", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Backend", overflow="fold")
    table.add_column("Installed")
    table.add_column("Default")
    table.add_column("Model support", overflow="fold")
    table.add_column("Encoding", overflow="fold")
    table.add_column("Version", overflow="fold")
    for index, lexicon in enumerate(rows, 1):
        table.add_row(
            str(index),
            lexicon.selector,
            lexicon.display_name or lexicon.selector,
            lexicon.data_backend,
            "yes" if lexicon.installed else "no",
            "yes" if lexicon.default else "no",
            lexicon.model_support,
            lexicon.phoneme_encoding or "—",
            lexicon.data_version or "—",
        )
    console.print(table)


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
    pins: CliPins,
    baseline: SynthesisResolution,
    console: Console,
) -> tuple[AudiobookOptions, str, EngineInfo | None]:
    all_engines = converter.engines()
    runnable_engines = tuple(engine for engine in all_engines if engine.runnable)
    if not pins.pinned("engine"):
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
    pins: CliPins,
    baseline: SynthesisResolution,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    console: Console,
) -> tuple[AudiobookOptions, ModelInfo | None]:
    models = converter.models(
        language=language, engine=engine, discovery=discovery
    ).items
    selected_model_info = next(
        (item for item in models if item.id == options.model), None
    )
    if pins.pinned("model"):
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
    if selected_model_info is not None and not pins.pinned("model_source"):
        options = replace(options, model=model, model_source=selected_model_info.source)
    else:
        options = replace(options, model=model)
    return options, selected_model_info


def _choose_quality(
    options: AudiobookOptions,
    pins: CliPins,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    console: Console,
) -> AudiobookOptions:
    qualities = model_info.qualities if model_info is not None else ()
    if pins.pinned("quality") or not qualities:
        return options
    if len(qualities) == 1:
        return replace(options, quality=qualities[0])
    default = baseline.quality if baseline.quality in qualities else qualities[0]
    return replace(options, quality=_choice("Quality", default, qualities, console))


def _choose_voice(
    converter: AudiobookConverter,
    options: AudiobookOptions,
    pins: CliPins,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    console: Console,
) -> AudiobookOptions:
    voices = converter.voices(
        language=language,
        engine=engine,
        model=options.model,
        discovery=discovery,
    ).items
    if pins.pinned("voice"):
        return options
    if voices:
        _show_voices(voices, language, engine, options.model, console)
    else:
        model = options.model or "default"
        console.print(f"No catalog voices matched {language} / {engine} / {model}.")
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
    voice = (
        selected.selector or selected.qualified_id
        if isinstance(selected, VoiceInfo)
        else selected
    )
    return replace(options, voice=voice)


def _prompt_text_policies(
    options: AudiobookOptions,
    pins: CliPins,
    baseline: SynthesisResolution,
    console: Console,
) -> AudiobookOptions:
    if not pins.pinned("speed"):
        options = replace(options, speed=_prompt_speed(baseline.speed, console))
    if not pins.pinned("spacy"):
        default_spacy = baseline.spacy if baseline.spacy in SPACY_POLICIES else "auto"
        options = replace(
            options,
            spacy=_choice("spaCy", default_spacy, SPACY_POLICIES, console),
        )
    if not pins.pinned("short_sentence"):
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
    pins: CliPins,
    baseline: SynthesisResolution,
    model_info: ModelInfo | None,
    language: str,
    engine: str,
    discovery: DiscoveryOptions,
    engine_info: EngineInfo | None,
    console: Console,
) -> AudiobookOptions:
    capabilities = engine_info.capabilities if engine_info is not None else None
    supports_lexicons = bool(
        capabilities is not None and capabilities.supports_lexicons
    )
    g2p_relevant = bool(
        (model_info is not None and model_info.g2p_backend) or supports_lexicons
    )
    if supports_lexicons and not pins.pinned("lexicons"):
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
        default = _default_lexicon_input(baseline.lexicons)
        while True:
            value = typer.prompt("Lexicons", default=default).strip()
            try:
                return_options = apply_lexicon_selection(options, value, lexicons)
                break
            except CatalogSelectionError as exc:
                console.print(str(exc), style="red")
        options = return_options

    if g2p_relevant and not pins.pinned("g2p_fallback"):
        default_g2p = (
            baseline.g2p_fallback
            if baseline.g2p_fallback in G2P_FALLBACKS
            else "espeak"
        )
        options = replace(
            options,
            g2p_fallback=_choice("G2P fallback", default_g2p, G2P_FALLBACKS, console),
        )
    if (supports_lexicons or g2p_relevant) and not pins.pinned("lexicon_data_policy"):
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
    pins: CliPins,
    baseline: SynthesisResolution,
    engine_info: EngineInfo | None,
    console: Console,
) -> AudiobookOptions:
    capabilities = engine_info.capabilities if engine_info is not None else None
    if (
        capabilities is None
        or not capabilities.supports_voice_level_calibration
        or pins.pinned("voice_level")
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
    pins: CliPins,
    baseline: SynthesisResolution,
    console: Console,
) -> AudiobookOptions:
    if not pins.pinned("pause_mode"):
        default_pause = (
            baseline.pause_mode if baseline.pause_mode in PAUSE_MODES else "auto"
        )
        options = replace(
            options,
            pause_mode=_choice("Pause mode", default_pause, PAUSE_MODES, console),
        )
    if not pins.pinned("unit"):
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
    pins: CliPins,
    console: Console,
) -> AudiobookOptions:
    """Ask for unpinned synthesis values, using Readio defaults and catalogs."""
    baseline = converter.resolve_synthesis(project, synthesis_request(options))
    if not pins.pinned("language"):
        options = replace(options, language=_free_text("Language", baseline.language))
    language = options.language or baseline.language

    options, engine, engine_info = _choose_engine(
        converter, options, pins, baseline, console
    )
    discovery = _discovery_options(options)
    options, model_info = _choose_model(
        converter,
        options,
        pins,
        baseline,
        language,
        engine,
        discovery,
        console,
    )
    options = _choose_quality(options, pins, baseline, model_info, console)
    discovery = _discovery_options(options)
    options = _choose_voice(
        converter,
        options,
        pins,
        baseline,
        model_info,
        language,
        engine,
        discovery,
        console,
    )
    options = _prompt_text_policies(options, pins, baseline, console)
    options = _prompt_lexicon_options(
        converter,
        options,
        pins,
        baseline,
        model_info,
        language,
        engine,
        discovery,
        engine_info,
        console,
    )
    options = _prompt_voice_level(options, pins, baseline, engine_info, console)
    return _prompt_pause_and_unit(options, pins, baseline, console)
