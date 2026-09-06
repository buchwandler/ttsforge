from __future__ import annotations

from ttsforge.audio_player import PlaybackPosition


def test_legacy_read_cursor_is_explicitly_best_effort():
    cursor = PlaybackPosition.from_dict(
        {"file_path": "book.epub", "chapter_index": 2, "segment_index": 4}
    )
    assert cursor.schema_version == 1
    assert cursor.legacy_segment_cursor
    assert cursor.unit_index == 4
    assert "segment_index" in cursor.to_dict()


def test_prepared_unit_cursor_round_trips_with_source_and_mode():
    cursor = PlaybackPosition(
        file_path="book.epub",
        chapter_index=2,
        unit_index=4,
        content_mode="pages",
        generation_fingerprint="generation",
        source_sha256="source",
        timestamp=12.5,
    )
    restored = PlaybackPosition.from_dict(cursor.to_dict())
    assert restored == cursor
    assert restored.segment_index == restored.unit_index
    assert restored.to_dict()["unit"] == "prepared"
