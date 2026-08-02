from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ttsforge.input_reader import Chapter, EpubReadOptions, InputReader


def test_chapter_visible_count_and_default_epub_options() -> None:
    chapter = Chapter(
        title="ONE",
        text="Visible text",
        markdown_body="## Sub\n\nVisible text\n",
        source_format="markdown",
    )

    assert EpubReadOptions() == EpubReadOptions(
        content_mode="markdown",
        preserve_emphasis=True,
        preserve_strong=True,
        preserve_scene_breaks=True,
    )
    assert chapter.char_count == len(chapter.text)


def test_markdown_mode_reports_missing_public_api(tmp_path: Path) -> None:
    epub = tmp_path / "missing-api.epub"
    epub.write_bytes(b"placeholder")
    parser = SimpleNamespace()

    with patch("epub2text.EPUBParser", return_value=parser):
        with pytest.raises(ImportError, match="get_chapter_documents"):
            InputReader(epub).get_chapters()
