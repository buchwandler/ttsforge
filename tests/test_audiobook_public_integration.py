"""Black-box EPUB inspection/project tests against Readio's public API."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from readio.api import Readio

from ttsforge.audiobook import AudiobookConverter
from ttsforge.options import AudiobookOptions


def _write_epub(path: Path) -> None:
    chapters = (
        ("chapter-1.xhtml", "Chapter One", "First chapter text."),
        ("chapter-2.xhtml", "Chapter Two", "Second chapter text."),
    )
    manifest = "\n".join(
        f'<item id="chapter-{index}" href="{href}" '
        'media-type="application/xhtml+xml" />'
        for index, (href, _, _) in enumerate(chapters, start=1)
    )
    spine = "\n".join(
        f'<itemref idref="chapter-{index}" />' for index in range(1, len(chapters) + 1)
    )
    nav_items = "\n".join(
        f'<li><a href="{href}">{title}</a></li>' for href, title, _ in chapters
    )
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">readio-test-book</dc:identifier>
    <dc:title>Readio Sample</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
          properties="nav" />
    {manifest}
  </manifest>
  <spine>{spine}</spine>
</package>
"""
    nav = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <body><nav epub:type="toc"><ol>{nav_items}</ol></nav></body>
</html>
"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
      media-type="application/oebps-package+xml" /></rootfiles>
</container>
"""

    with ZipFile(path, "w") as archive:
        mimetype = ZipInfo("mimetype")
        mimetype.compress_type = ZIP_STORED
        archive.writestr(mimetype, "application/epub+zip")
        archive.writestr("META-INF/container.xml", container, ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", opf, ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, ZIP_DEFLATED)
        for href, title, text in chapters:
            chapter = (
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                f"<h1>{title}</h1><p>{text}</p></body></html>"
            )
            archive.writestr(f"OEBPS/{href}", chapter, ZIP_DEFLATED)


def test_public_inspection_and_project_creation_persist_chapter_scope(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.epub"
    _write_epub(source)
    converter = AudiobookConverter(Readio())

    inspection = converter.inspect(source)
    setup = converter.create_or_open_project(
        AudiobookOptions(source=source, chapters="2")
    )
    reopened = converter.create_or_open_project(
        AudiobookOptions(source=source, chapters="1")
    )

    assert inspection.metadata["title"] == "Readio Sample"
    assert [chapter.title for chapter in inspection.chapters] == [
        "Chapter One",
        "Chapter Two",
    ]
    assert setup.project.root == tmp_path / "sample.ssmdbook"
    assert setup.created is True
    assert setup.selected_chapters == (2,)
    assert reopened.project == setup.project
    assert reopened.created is False
    assert reopened.selected_chapters == (2,)
