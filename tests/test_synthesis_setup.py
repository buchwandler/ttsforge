from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ttsforge.application.models import AudiobookRequest, InputOverrides
from ttsforge.application.setup import merge_saved_setup


def test_cli_saved_and_source_defaults_follow_explicit_precedence() -> None:
    source = Path("book.epub")
    derived = AudiobookRequest(
        source=source,
        chapters="1-2",
        output=Path("book.m4b"),
        language="en-US",
        title="Source title",
        author="Source author",
        cover=Path("source-cover.jpg"),
        bitrate="96k",
    )
    saved = replace(
        derived,
        chapters="2-4",
        output=Path("saved.m4b"),
        language="de-DE",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        bitrate="128k",
        title="Saved title",
        author="Saved author",
        cover=Path("saved-cover.jpg"),
    )
    cli = replace(
        derived,
        chapters="3",
        bitrate="192k",
        title="CLI title",
        author="CLI author",
        cover=Path("cli-cover.jpg"),
    )
    overrides = InputOverrides(
        frozenset({"chapters", "bitrate", "title", "author", "cover"})
    )

    merged = merge_saved_setup(cli, saved, overrides)

    assert merged.chapters == "3"
    assert merged.output == Path("saved.m4b")
    assert merged.language == "de-DE"
    assert merged.engine == "engine-a"
    assert merged.target == "target-a"
    assert merged.voice == "voice-a"
    assert merged.bitrate == "192k"
    assert merged.title == "CLI title"
    assert merged.author == "CLI author"
    assert merged.cover == Path("cli-cover.jpg")


def test_saved_target_and_voice_are_invalidated_when_target_changes() -> None:
    request = AudiobookRequest(
        source=Path("book.epub"),
        engine="engine-a",
        target="target-b",
    )
    saved = replace(
        request,
        target="target-a",
        voice="voice-a",
        engine_options={"quality": "high"},
        speed=1.2,
    )

    merged = merge_saved_setup(
        request,
        saved,
        InputOverrides(frozenset({"target"})),
    )

    assert merged.target == "target-b"
    assert merged.voice is None
    assert merged.engine_options == {}
    assert merged.speed is None
