import json
from pathlib import Path

from ttsforge.conversion import ChapterState, ConversionState


def test_conversion_state_roundtrip(tmp_path: Path) -> None:
    state = ConversionState(
        source_file="book.epub",
        source_hash="abc123",
        output_file="book.m4b",
        work_dir=str(tmp_path),
        voice="af_heart",
        language="a",
        speed=1.0,
        split_mode="auto",
        output_format="m4b",
        chapters=[
            ChapterState(
                index=0,
                title="Chapter 1",
                content_hash="hash",
                source_format="markdown",
                source_id="ch1",
                source_markup_hash="markup",
                extraction_schema="epub2text.chapter-document/0.2.8",
                completed=True,
                audio_file="chapter_001.wav",
                duration=1.2,
                char_count=100,
                ssmd_file="chapter_001.ssmd",
                ssmd_hash="ssmdhash",
            )
        ],
        started_at="2024-01-01 00:00:00",
    )
    state_file = tmp_path / "state.json"
    state.save(state_file)

    loaded = ConversionState.load(state_file)
    assert loaded is not None
    assert loaded.voice == "af_heart"
    assert loaded.chapters[0].audio_file == "chapter_001.wav"
    assert loaded.chapters[0].completed is True
    assert loaded.chapters[0].source_format == "markdown"
    assert loaded.chapters[0].source_markup_hash == "markup"

    assert not (tmp_path / "state.json.tmp").exists()


def test_conversion_state_backward_compat(tmp_path: Path) -> None:
    data = {
        "version": 1,
        "source_file": "book.epub",
        "source_hash": "hash",
        "output_file": "book.m4b",
        "work_dir": str(tmp_path),
        "voice": "af_heart",
        "language": "a",
        "speed": 1.0,
        "split_mode": "auto",
        "output_format": "m4b",
        "chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "content_hash": "hash",
                "completed": False,
                "audio_file": None,
                "duration": 0.0,
                "char_count": 10,
                "ssmd_file": None,
                "ssmd_hash": None,
            }
        ],
        "segment_pause_min": 0.1,
        "segment_pause_max": 0.3,
        "paragraph_pause_min": 0.5,
        "paragraph_pause_max": 1.0,
    }

    state_file = tmp_path / "legacy_state.json"
    state_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = ConversionState.load(state_file)
    assert loaded is not None
    assert loaded.pause_sentence == 0.2
    assert loaded.pause_paragraph == 0.75
    assert loaded.pause_clause == 0.3
    assert loaded.pause_variance >= 0.01


def test_conversion_state_preserves_tri_state_spacy_values(tmp_path: Path) -> None:
    for value in (None, True, False):
        state_file = tmp_path / f"state-{value}.json"
        state_file.write_text(json.dumps({"version": 5, "use_spacy": value}), encoding="utf-8")
        loaded = ConversionState.load(state_file)
        assert loaded is not None
        assert loaded.use_spacy is value


def test_conversion_state_missing_spacy_value_defaults_to_auto(tmp_path: Path) -> None:
    state_file = tmp_path / "legacy-without-policy.json"
    state_file.write_text(json.dumps({"version": 5}), encoding="utf-8")
    loaded = ConversionState.load(state_file)
    assert loaded is not None
    assert loaded.use_spacy is None
