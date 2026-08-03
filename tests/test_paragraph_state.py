"""Schema-5 and legacy state behavior."""

import json
from pathlib import Path

from ttsforge.conversion import ChapterState, ConversionState
from ttsforge.render_units import RenderUnitState


def _unit() -> RenderUnitState:
    return RenderUnitState(
        sequence_index=0,
        unit_index=0,
        chapter_position=0,
        source_chapter_index=2,
        paragraph_index=0,
        kind="title",
        content_hash="content",
        render_fingerprint="render",
        char_count=5,
        completed=True,
        audio_file="00000001__c000003__p000000__title__TITLE.wav",
        duration=1.0,
        content_duration=1.0,
    )


def test_schema5_state_round_trip_and_legacy_chapter_load(tmp_path: Path):
    path = tmp_path / "state.json"
    state = ConversionState(
        version=5,
        conversion_unit="paragraph",
        paragraphs_dir=str(tmp_path / "Book_paragraphs"),
        source_selection=[2],
        chapters=[ChapterState(index=2, title="Title", content_hash="hash", units=[_unit()])],
    )
    state.save(path)
    loaded = ConversionState.load(path)
    assert loaded is not None
    assert loaded.conversion_unit == "paragraph"
    assert loaded.chapters[0].units[0].completed
    assert loaded.get_completed_unit_count() == 1

    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["version"] = 4
    legacy.pop("conversion_unit")
    legacy["chapters"][0].pop("units")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    legacy_state = ConversionState.load(path)
    assert legacy_state is not None
    assert legacy_state.conversion_unit == "chapter"
    assert legacy_state.chapters[0].units == []

