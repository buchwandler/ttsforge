import pytest

from ttsforge.chapter_selection import parse_chapter_selection, resolve_chapter_selection


def test_parse_all() -> None:
    assert parse_chapter_selection("all", 5) == [0, 1, 2, 3, 4]


def test_parse_ranges_and_commas() -> None:
    assert parse_chapter_selection("1-3,5", 6) == [0, 1, 2, 4]


def test_parse_open_ended_range() -> None:
    assert parse_chapter_selection("3-", 5) == [2, 3, 4]


def test_parse_invalid_range() -> None:
    with pytest.raises(ValueError):
        parse_chapter_selection("5-2", 6)


def test_resolve_chapter_selection_returns_none_when_unspecified() -> None:
    assert resolve_chapter_selection(None, None, 5) is None


def test_resolve_chapter_selection_skips_from_all_chapters() -> None:
    assert resolve_chapter_selection(None, "2,4", 5) == [0, 2, 4]


def test_resolve_chapter_selection_skips_from_included_range() -> None:
    assert resolve_chapter_selection("1-5", "3", 6) == [0, 1, 3, 4]


def test_resolve_chapter_selection_can_skip_all_selected_chapters() -> None:
    assert resolve_chapter_selection("1-3", "all", 5) == []
