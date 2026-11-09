from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ttsforge.application.models import AudiobookRequest, InputOverrides, SetupOrigins
from ttsforge.application.setup import merge_saved_setup


def test_cli_values_override_project_and_derived_values() -> None:
    request = AudiobookRequest(
        source=Path("book.epub"),
        language="en-US",
        output=Path("default.m4b"),
        title="Source title",
    )
    saved = replace(
        request,
        language="de-DE",
        output=Path("saved.m4b"),
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        title="Saved title",
    )

    merged = merge_saved_setup(
        request,
        saved,
        InputOverrides(frozenset({"output"})),
    )

    assert merged.language == "de-DE"
    assert merged.output == Path("default.m4b")
    assert merged.engine == "engine-a"
    assert merged.voice == "voice-a"
    assert merged.title == "Saved title"


def test_changed_language_invalidates_saved_engine_dependent_choices() -> None:
    request = AudiobookRequest(source=Path("book.epub"), language="fr-FR")
    saved = replace(
        request,
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        engine_options={"quality": "high"},
        speed=1.2,
    )

    merged = merge_saved_setup(
        request,
        saved,
        InputOverrides(frozenset({"language"})),
    )

    assert merged.language == "fr-FR"
    assert merged.engine is None
    assert merged.target is None
    assert merged.voice is None
    assert merged.engine_options == {}
    assert merged.speed is None


def test_language_confirmation_respects_explicit_and_project_origins() -> None:
    origins = SetupOrigins(
        explicit=frozenset({"engine"}),
        project=frozenset({"voice"}),
        derived=frozenset({"language"}),
    )

    assert not origins.needs_input("language")
    assert origins.should_confirm_derived("language")
    assert not origins.should_confirm_derived("engine")
    assert not origins.should_confirm_derived("voice")


def test_explicit_dependent_choice_survives_invalidation() -> None:
    request = AudiobookRequest(
        source=Path("book.epub"),
        engine="engine-b",
        target="target-b",
    )
    saved = replace(
        request,
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        engine_options={"quality": "high"},
    )

    merged = merge_saved_setup(
        request,
        saved,
        InputOverrides(frozenset({"engine", "target"})),
    )

    assert merged.engine == "engine-b"
    assert merged.target == "target-b"
    assert merged.voice is None
    assert merged.engine_options == {}


def test_engine_options_override_saved_keys_without_dropping_other_options() -> None:
    request = AudiobookRequest(
        source=Path("book.epub"),
        engine="engine-a",
        target="target-a",
        engine_options={"device": "cuda"},
    )
    saved = replace(
        request,
        engine_options={"device": "cpu", "precision": "fp16"},
    )

    merged = merge_saved_setup(
        request,
        saved,
        InputOverrides(frozenset({"engine_options"})),
    )

    assert merged.engine_options == {"device": "cuda", "precision": "fp16"}
