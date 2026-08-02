import pytest

from ttsforge.epub_markdown import (
    EpubMarkdownError,
    markdown_structure_counts,
    normalize_epub_markdown,
)


def test_normalize_preserves_controlled_structure_and_converts_scene_break() -> None:
    result = normalize_epub_markdown(
        "## Four years ago\n\nAbove all, *italic* and **strong**.\n\n---\n\nAprès.\n"
    )

    assert result.body == (
        "## Four years ago\n\nAbove all, *italic* and **strong**.\n\n...p\n\nAprès.\n"
    )
    assert result.diagnostics == ()
    assert markdown_structure_counts(result.body) == {
        "headings": 1,
        "subheadings": 1,
        "moderate_spans": 1,
        "strong_spans": 1,
        "scene_breaks": 1,
    }


def test_normalize_unwraps_defensive_inline_constructs_and_emphasis() -> None:
    result = normalize_epub_markdown(
        r"A [linked word](https://example.test) and `literal` plus *soft* and **bold**."
        ,
        preserve_emphasis=False,
    )

    assert result.body == "A linked word and literal plus soft and bold.\n"
    assert "link_unwrapped" in result.diagnostics
    assert "inline_code_unwrapped" in result.diagnostics


def test_normalize_rejects_yaml_front_matter() -> None:
    with pytest.raises(EpubMarkdownError, match="front matter"):
        normalize_epub_markdown("---\ntitle: nested\n---\n\nBody")


def test_normalize_reports_unexpected_profile_constructs() -> None:
    result = normalize_epub_markdown("<span>raw</span>\n\n````\ncode\n")

    assert "raw_html_unexpected" in result.diagnostics
    assert "code_fence_unexpected" in result.diagnostics
    assert "unclosed_code_fence" in result.diagnostics
