from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest

from ttsforge.epub_markdown import markdown_structure_counts
from ttsforge.input_reader import EpubReadOptions, InputReader
from ttsforge.ssmd_generator import chapter_to_ssmd


def _write_markdown_fixture(path: Path) -> None:
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">fixture-book</dc:identifier>
    <dc:title>Markdown Fixture</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml"
      media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="styles.css" media-type="text/css"/>
  </manifest>
  <spine><itemref idref="chapter"/></spine>
</package>"""
    nav = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <body><nav epub:type="toc"><ol>
    <li><a href="chapter.xhtml#one">ONE</a></li>
  </ol></nav></body>
</html>"""
    chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
    <head><link rel="stylesheet" type="text/css" href="styles.css"/></head>
  <body>
    <style>.italic { font-style: italic; }</style>
    <h1 id="one">ONE</h1>
    <h2>Four years ago</h2>
    <p>Above all, <em>semantic italic</em> remains.</p>
    <p><strong>Strong text</strong> remains.</p>
    <p><span class="italic">CSS italic</span> remains too.</p>
    <hr/>
    <p>After the break.</p>
  </body>
</html>"""
    css = ".italic { font-style: italic; }"

    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", nav)
        archive.writestr("OEBPS/chapter.xhtml", chapter)
        archive.writestr("OEBPS/styles.css", css)


@pytest.fixture()
def markdown_epub(tmp_path: Path) -> Path:
    path = tmp_path / "markdown-fixture.epub"
    _write_markdown_fixture(path)
    return path


def test_reader_consumes_chapter_document_markdown_and_metadata(
    markdown_epub: Path,
) -> None:
    chapters = InputReader(
        markdown_epub,
        epub_options=EpubReadOptions(),
    ).get_chapters()

    assert len(chapters) == 1
    chapter = chapters[0]
    assert chapter.title == "ONE"
    assert chapter.source_format == "markdown"
    assert chapter.source_id
    assert chapter.level == 1
    assert chapter.markdown_body is not None
    assert "## Four years ago" in chapter.markdown_body
    assert "*semantic italic*" in chapter.markdown_body
    assert "**Strong text**" in chapter.markdown_body
    assert "*CSS italic*" in chapter.markdown_body
    assert "---" in chapter.markdown_body
    assert chapter.char_count == len(chapter.text)
    assert "*" not in chapter.text


def test_generated_ssmd_preserves_headings_emphasis_and_pause(
    markdown_epub: Path,
) -> None:
    chapter = InputReader(markdown_epub).get_chapters()[0]
    ssmd = chapter_to_ssmd(
        chapter.title,
        chapter.text,
        chapter_markdown=chapter.markdown_body,
        source_format=chapter.source_format,
    )

    assert ssmd.count("# ONE") == 1
    assert "## Four years ago" in ssmd
    assert "*semantic italic*" in ssmd
    assert "**Strong text**" in ssmd
    assert "*CSS italic*" in ssmd
    assert "\n...p\n" in ssmd
    assert markdown_structure_counts(chapter.markdown_body or "")["scene_breaks"] == 0


def test_detect_emphasis_false_preserves_structure_but_unwraps_inline_markup(
    markdown_epub: Path,
) -> None:
    chapter = InputReader(
        markdown_epub,
        epub_options=EpubReadOptions(preserve_emphasis=False, preserve_strong=False),
    ).get_chapters()[0]

    assert "## Four years ago" in (chapter.markdown_body or "")
    assert "semantic italic" in (chapter.markdown_body or "")
    assert "**" not in (chapter.markdown_body or "")
    assert "*semantic italic*" not in (chapter.markdown_body or "")
    assert "---" in (chapter.markdown_body or "")


def test_plain_compatibility_mode_keeps_legacy_visible_text(
    markdown_epub: Path,
) -> None:
    chapter = InputReader(
        markdown_epub,
        epub_options=EpubReadOptions(content_mode="plain"),
    ).get_chapters()[0]

    assert chapter.source_format == "plain"
    assert chapter.markdown_body is None
    assert "semantic italic" in chapter.text
    assert "Four years ago" in chapter.text
