"""Tests for frontend synthesis setup provenance and selection behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import DiscoveryOptions, LexiconInfo

from ttsforge.audiobook import AudiobookConverter
from ttsforge.options import AudiobookOptions
from ttsforge.synthesis_setup import (
    CatalogSelectionError,
    CliPins,
    apply_lexicon_selection,
    choose_catalog_item,
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
