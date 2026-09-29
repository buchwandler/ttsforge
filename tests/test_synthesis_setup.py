"""Tests for frontend synthesis setup provenance and selection behavior."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import (
    DiscoveryOptions,
    LexiconInfo,
    ProjectRef,
    SynthesisResolution,
)
from rich.console import Console

import ttsforge.ui.synthesis as synthesis_ui
from ttsforge.audiobook import AudiobookConverter
from ttsforge.options import AudiobookOptions
from ttsforge.synthesis_setup import (
    CatalogSelectionError,
    CliPins,
    SetupSources,
    apply_lexicon_selection,
    choose_catalog_item,
    merge_saved_setup,
    reset_dependency_choices,
)


def test_cli_pins_track_supplied_values_without_inference_from_false_defaults() -> None:
    pins = CliPins.from_cli_values(
        language="en-us",
        speed=1.0,
        lexicons=True,
        allow_experimental=False,
        pause_mode=None,
    )

    assert pins.pinned("language")
    assert pins.pinned("speed")
    assert pins.pinned("lexicons")
    assert not pins.pinned("allow_experimental")
    assert not pins.pinned("pause_mode")


@dataclass(frozen=True)
class _Choice:
    identifier: str
    selector: str


def _choices() -> tuple[_Choice, ...]:
    return (_Choice("model-a", "alpha"), _Choice("model-b", "beta"))


def _keys(item: _Choice) -> tuple[str, str]:
    return item.identifier, item.selector


def test_catalog_selection_accepts_rows_exact_ids_and_default() -> None:
    rows = _choices()
    assert (
        choose_catalog_item(value="2", rows=rows, default=None, keys=_keys) == rows[1]
    )
    assert (
        choose_catalog_item(value="model-a", rows=rows, default=None, keys=_keys)
        == rows[0]
    )
    assert (
        choose_catalog_item(value="", rows=rows, default="beta", keys=_keys) == rows[1]
    )


def test_catalog_selection_reports_invalid_and_ambiguous_input() -> None:
    rows = (_Choice("model-a", "shared"), _Choice("model-b", "shared"))
    with pytest.raises(CatalogSelectionError, match="between 1 and 2"):
        choose_catalog_item(value="3", rows=rows, default=None, keys=_keys)
    with pytest.raises(CatalogSelectionError, match="Unknown selection"):
        choose_catalog_item(value="model", rows=rows, default=None, keys=_keys)
    with pytest.raises(CatalogSelectionError, match="ambiguous"):
        choose_catalog_item(value="shared", rows=rows, default=None, keys=_keys)


def _lexicon(selector: str) -> LexiconInfo:
    return LexiconInfo(
        selector=selector,
        engine="pykokoro",
        language="en",
        locale="en-us",
        asset_id=selector,
        data_backend="kokorog2p",
        default=False,
        installed=True,
        models=("v1.0",),
        model_support="supported",
        display_name=selector.title(),
        phoneme_encoding="ipa",
        data_version="1",
    )


def _options() -> AudiobookOptions:
    return AudiobookOptions(source=Path("book.epub"))


def test_lexicon_selection_maps_modes_and_deduplicates_in_input_order() -> None:
    rows = (_lexicon("crane"), _lexicon("custom"))
    automatic = apply_lexicon_selection(_options(), "auto", rows)
    disabled = apply_lexicon_selection(_options(), "none", rows)
    selected = apply_lexicon_selection(_options(), "2,crane,1,crane", rows)

    assert automatic.lexicons is None
    assert automatic.auto_lexicons is True
    assert automatic.clear_lexicons is False
    assert disabled.lexicons is None
    assert disabled.auto_lexicons is False
    assert disabled.clear_lexicons is True
    assert selected.lexicons == ("custom", "crane")
    assert selected.auto_lexicons is False
    assert selected.clear_lexicons is False


def test_empty_lexicon_catalog_allows_raw_selector_and_invalid_rows_fail() -> None:
    raw = apply_lexicon_selection(_options(), "custom-resource", ())
    assert raw.lexicons == ("custom-resource",)
    with pytest.raises(CatalogSelectionError, match="between 1 and 1"):
        apply_lexicon_selection(_options(), "2", (_lexicon("crane"),))


def test_converter_catalog_delegates_use_the_same_readio_services() -> None:
    calls: list[tuple[str, object, object]] = []
    listing = SimpleNamespace(items=())
    engines = (object(),)

    def record(name: str):
        def call(query=None, *, discovery=None):
            calls.append((name, query, discovery))
            return listing

        return call

    catalog = SimpleNamespace(
        engines=lambda: engines,
        models_listing=record("models"),
        voices_listing=record("voices"),
        lexicons_listing=record("lexicons"),
    )
    resolution = object()

    def resolve(project, request):
        calls.append(("resolve", project, request))
        return resolution

    app = SimpleNamespace(
        catalog=catalog, projects=SimpleNamespace(resolve_synthesis=resolve)
    )
    converter = AudiobookConverter(app=app)  # type: ignore[arg-type]
    discovery = DiscoveryOptions(offline=True, refresh=True, preference="github")
    project = Path("book.readio")
    request = object()

    assert converter.engines() is engines
    assert (
        converter.models(language="en-us", engine="pykokoro", discovery=discovery)
        is listing
    )
    assert (
        converter.voices(
            language="en-us", engine="pykokoro", model="v1.0", discovery=discovery
        )
        is listing
    )
    assert (
        converter.lexicons(
            language="en-us", engine="pykokoro", model="v1.0", discovery=discovery
        )
        is listing
    )
    assert converter.resolve_synthesis(project, request) is resolution
    assert [name for name, _, _ in calls] == ["models", "voices", "lexicons", "resolve"]
    assert calls[0][1].language == "en-us"
    assert calls[0][1].engine == "pykokoro"
    assert calls[1][1].model == "v1.0"
    assert calls[2][1].model == "v1.0"
    assert all(call[2] is discovery for call in calls[:3])


def _saved_options() -> AudiobookOptions:
    return replace(
        _options(),
        language="en-us",
        engine="pykokoro",
        model="v1.0",
        model_source="github",
        quality="fp32",
        voice="af_sarah",
        speed=1.0,
        lexicons=("crane",),
        g2p_fallback="espeak",
        lexicon_data_policy="auto",
        spacy="auto",
        short_sentence="phrase",
        target_lufs=-18.0,
        bitrate="128k",
        title="Saved title",
    )


def test_setup_sources_distinguish_cli_project_and_unresolved_fields() -> None:
    sources = SetupSources(
        cli=frozenset({"voice"}),
        project=frozenset({"engine", "model"}),
    )

    assert not sources.prompt_required("voice")
    assert not sources.prompt_required("engine")
    assert sources.prompt_required("engine", reconfigure=True)
    assert sources.prompt_required("quality")


def test_merge_saved_setup_uses_project_values_except_cli_pins() -> None:
    cli_options = replace(_options(), voice="af_bella", refresh=True, force=True)
    merged = merge_saved_setup(
        cli_options,
        _saved_options(),
        CliPins(frozenset({"voice"})),
    )

    assert merged.language == "en-us"
    assert merged.engine == "pykokoro"
    assert merged.model == "v1.0"
    assert merged.voice == "af_bella"
    assert merged.target_lufs == -18.0
    assert merged.title == "Saved title"
    assert merged.refresh is True
    assert merged.force is True


def test_engine_change_resets_unpinned_dependent_saved_values() -> None:
    cli_options = replace(_options(), engine="piper", voice="af_bella")
    merged = merge_saved_setup(
        cli_options,
        _saved_options(),
        CliPins(frozenset({"engine", "voice"})),
    )

    assert merged.engine == "piper"
    assert merged.model is None
    assert merged.model_source is None
    assert merged.quality is None
    assert merged.voice == "af_bella"
    assert merged.lexicons is None
    assert merged.g2p_fallback is None
    assert merged.lexicon_data_policy is None


def test_language_change_resets_engine_and_model_but_keeps_cli_pins() -> None:
    cli_options = replace(
        _options(), language="fr-fr", engine="piper", model="voice-v2"
    )
    pins = CliPins(frozenset({"language", "engine", "model"}))
    merged = merge_saved_setup(cli_options, _saved_options(), pins)

    assert merged.language == "fr-fr"
    assert merged.engine == "piper"
    assert merged.model == "voice-v2"
    assert merged.quality is None
    assert merged.voice is None


def test_non_interactive_invalid_saved_dependency_is_actionable() -> None:
    cli_options = replace(_options(), engine="piper")
    with pytest.raises(ValueError, match=r"--engine.*--model.*--quality.*--voice"):
        merge_saved_setup(
            cli_options,
            _saved_options(),
            CliPins(frozenset({"engine"})),
            interactive=False,
        )


def test_dependency_reset_preserves_explicit_dependent_cli_pins() -> None:
    pins = CliPins(frozenset({"model", "voice"}))
    reset = reset_dependency_choices(_saved_options(), "engine", pins)

    assert reset.model == "v1.0"
    assert reset.voice == "af_sarah"
    assert reset.quality is None
    assert reset.lexicons is None


def _baseline() -> SynthesisResolution:
    return SynthesisResolution(
        engine="pykokoro",
        language="en-us",
        voice="af_sarah",
        model="v1.0",
        model_source="github",
        quality="q8",
        speed=1.0,
        unit="sentence",
        pause_mode="auto",
        voice_level="off",
    )


def test_ui_skips_a_complete_saved_setup_without_catalogs_or_prompts() -> None:
    fields = frozenset(
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
            "voice_level",
            "pause_mode",
            "unit",
        }
    )
    options = _options()

    result = synthesis_ui.configure_synthesis_interactively(
        converter=object(),
        project=ProjectRef(Path("book.readio"), "id", "book", "audiobook", "epub"),
        options=options,
        sources=SetupSources(project=fields),
        console=Console(),
    )

    assert result is options


def test_ui_suppresses_saved_quality_normally_and_uses_it_as_reconfigure_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _options()
    sources = SetupSources(project=frozenset({"quality"}))
    observed: list[tuple[str, str, tuple[str, ...]]] = []

    def choose(prompt, default, choices, console):  # type: ignore[no-untyped-def]
        observed.append((prompt, default, tuple(choices)))
        return default

    monkeypatch.setattr(synthesis_ui, "_choice", choose)
    model_info = SimpleNamespace(qualities=("fp32", "q8"))

    unchanged = synthesis_ui._choose_quality(
        options, sources, _baseline(), model_info, Console()
    )
    assert unchanged is options
    assert observed == []

    configured = synthesis_ui._choose_quality(
        options, sources, _baseline(), model_info, Console(), reconfigure=True
    )
    assert configured.quality == "q8"
    assert observed == [("Quality", "q8", ("fp32", "q8"))]


def test_ui_prompts_only_missing_fields_from_project_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _options()
    observed: list[str] = []

    def choose(prompt, default, choices, console):  # type: ignore[no-untyped-def]
        observed.append(prompt)
        return default

    monkeypatch.setattr(synthesis_ui, "_choice", choose)
    model_info = SimpleNamespace(qualities=("fp32", "q8"))
    result = synthesis_ui._choose_quality(
        options,
        SetupSources(project=frozenset({"voice"})),
        _baseline(),
        model_info,
        Console(),
    )

    assert result.quality == "q8"
    assert observed == ["Quality"]
