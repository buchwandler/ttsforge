"""Unified input file reader for EPUB, TXT, and SSMD files.

This module provides a common interface for reading different input formats,
extracting metadata, chapters, and content for TTS conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .ssmd_support import SSMDValidationError, inspect_ssmd_document
from .text_postprocessing import (
    TextPostprocessOptions,
    postprocess_extracted_text,
)
from .utils import detect_encoding


@dataclass
class Metadata:
    """Book metadata."""

    title: str | None = None
    authors: list[str] = field(default_factory=list)
    language: str | None = None
    publisher: str | None = None
    publication_year: int | None = None


@dataclass
class Chapter:
    """Represents a chapter with title and content."""

    title: str
    text: str
    index: int = 0
    is_ssmd: bool = False
    markdown_body: str | None = None
    source_format: Literal["plain", "markdown", "ssmd"] = "plain"
    source_id: str | None = None
    parent_id: str | None = None
    level: int = 1
    extraction_schema: str | None = None
    extraction_diagnostics: tuple[str, ...] = ()

    @property
    def char_count(self) -> int:
        """Return the character count of the chapter."""
        return len(self.text)

    @property
    def content(self) -> str:
        """Alias for text to maintain compatibility with conversion.Chapter."""
        return self.text


@dataclass(frozen=True)
class EpubReadOptions:
    """Controls the public epub2text chapter extraction policy."""

    content_mode: Literal["markdown", "plain"] = "markdown"
    preserve_emphasis: bool = True
    preserve_strong: bool = True
    preserve_scene_breaks: bool = True


class InputReader:
    """Unified reader for EPUB, TXT (Gutenberg), and SSMD files."""

    def __init__(
        self,
        file_path: Path | str,
        postprocess_options: TextPostprocessOptions | None = None,
        epub_options: EpubReadOptions | None = None,
    ):
        """Initialize the reader with a file path.

        Args:
            file_path: Path to the input file (EPUB, TXT, or SSMD)
        """
        self.file_path = Path(file_path)
        self.postprocess_options = postprocess_options or TextPostprocessOptions()
        self.epub_options = epub_options or EpubReadOptions()
        self._metadata: Metadata | None = None
        self._chapters: list[Chapter] | None = None

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # Determine file type
        self.file_type = self._detect_file_type()

    def _detect_file_type(self) -> str:
        """Detect the file type based on extension.

        Returns:
            File type: 'epub', 'txt', or 'ssmd'
        """
        suffix = self.file_path.suffix.lower()
        if suffix == ".epub":
            return "epub"
        elif suffix == ".ssmd":
            return "ssmd"
        elif suffix in [".txt", ".text"]:
            return "txt"
        elif suffix == ".pdf":
            raise ValueError(
                "PDF input is not supported yet. Convert the PDF to EPUB or TXT "
                "and try again."
            )
        else:
            raise ValueError(
                f"Unsupported file type: {suffix}. Supported types: .epub, .txt, .ssmd"
            )

    def get_metadata(self) -> Metadata:
        """Extract metadata from the file.

        Returns:
            Metadata object with title, author, language, etc.
        """
        if self._metadata is not None:
            return self._metadata

        if self.file_type == "epub":
            self._metadata = self._get_epub_metadata()
        elif self.file_type == "txt":
            self._metadata = self._get_gutenberg_metadata()
        elif self.file_type == "ssmd":
            self._metadata = self._get_ssmd_metadata()
        elif self.file_type == "pdf":
            raise ValueError("PDF input is not supported yet.")

        if self._metadata is None:
            raise ValueError("Metadata could not be loaded")
        return self._metadata

    def get_chapters(self) -> list[Chapter]:
        """Extract chapters from the file.

        Returns:
            List of Chapter objects
        """
        if self._chapters is not None:
            return self._chapters

        if self.file_type == "epub":
            self._chapters = self._get_epub_chapters()
        elif self.file_type == "txt":
            self._chapters = self._get_gutenberg_chapters()
        elif self.file_type == "ssmd":
            self._chapters = self._get_ssmd_chapters()
        elif self.file_type == "pdf":
            raise ValueError("PDF input is not supported yet.")

        if self._chapters is None:
            raise ValueError("Chapters could not be loaded")
        return self._chapters

    # EPUB methods
    def _get_epub_metadata(self) -> Metadata:
        """Extract metadata from EPUB file."""
        try:
            from epub2text import EPUBParser
        except ImportError as e:
            raise ImportError(
                "epub2text is required for EPUB support. "
                "Install with: pip install epub2text"
            ) from e

        parser = EPUBParser(str(self.file_path))
        epub_metadata = parser.get_metadata()

        raw_year: object = epub_metadata.publication_year
        publication_year: int | None = None
        if isinstance(raw_year, int):
            publication_year = raw_year
        elif isinstance(raw_year, str):
            try:
                publication_year = int(raw_year)
            except ValueError:
                publication_year = None

        return Metadata(
            title=epub_metadata.title,
            authors=list(epub_metadata.authors) if epub_metadata.authors else [],
            language=epub_metadata.language,
            publisher=epub_metadata.publisher,
            publication_year=publication_year,
        )

    def _get_epub_chapters(self) -> list[Chapter]:
        """Extract chapters from EPUB file."""
        try:
            from epub2text import EPUBParser
        except ImportError as e:
            raise ImportError(
                "epub2text is required for EPUB support. "
                "Install with: pip install epub2text"
            ) from e

        parser = EPUBParser(str(self.file_path))
        options = self.epub_options

        if options.content_mode == "markdown":
            try:
                from epub2text import ChapterMarkdownOptions
            except ImportError as e:
                raise ImportError(
                    "epub2text>=0.2.8 is required for EPUB Markdown mode; "
                    "install or upgrade epub2text"
                ) from e
            try:
                documents = parser.get_chapter_documents(
                    options=ChapterMarkdownOptions(
                        include_title=False,
                        minimum_body_heading_level=2,
                        preserve_emphasis=options.preserve_emphasis,
                        preserve_strong=options.preserve_strong,
                        link_mode="unwrap",
                        code_mode="unwrap",
                        resolve_css_emphasis=True,
                        preserve_scene_breaks=options.preserve_scene_breaks,
                    )
                )
            except AttributeError as e:
                raise ImportError(
                    "Installed epub2text does not provide the required "
                    "get_chapter_documents() API for Markdown mode; "
                    "install epub2text>=0.2.8"
                ) from e

            return [
                Chapter(
                    title=doc.title,
                    text=postprocess_extracted_text(
                        doc.text,
                        self.postprocess_options,
                    ),
                    markdown_body=doc.markdown_body,
                    source_format="markdown",
                    source_id=doc.id,
                    parent_id=doc.parent_id,
                    level=doc.level,
                    extraction_schema=_epub_extraction_schema("chapter-document"),
                    extraction_diagnostics=tuple(
                        _format_extraction_diagnostic(diagnostic)
                        for diagnostic in doc.diagnostics
                    ),
                    index=i,
                )
                for i, doc in enumerate(documents)
            ]

        epub_chapters = parser.get_chapters()
        return [
            Chapter(
                title=ch.title,
                text=postprocess_extracted_text(
                    ch.text,
                    self.postprocess_options,
                ),
                source_format="plain",
                source_id=ch.id,
                parent_id=ch.parent_id,
                level=ch.level,
                extraction_schema=_epub_extraction_schema("chapter"),
                index=i,
            )
            for i, ch in enumerate(epub_chapters)
        ]

    # Gutenberg TXT methods
    def _get_gutenberg_metadata(self) -> Metadata:
        """Extract metadata from Project Gutenberg TXT file.

        Parses the header of a Gutenberg text file to extract metadata.
        """
        encoding = detect_encoding(self.file_path)
        with open(self.file_path, encoding=encoding, errors="replace") as f:
            # Read first 1000 lines for metadata (Gutenberg header is typically short)
            header_lines = []
            for i, line in enumerate(f):
                if i >= 1000:
                    break
                header_lines.append(line)
                # Stop at start of content
                if "*** START OF" in line.upper():
                    break

        header_text = "".join(header_lines)

        # Extract metadata using regex
        title = None
        authors = []
        language = None

        # Title pattern: "Title: <title>"
        title_match = re.search(
            r"^Title:\s*(.+)$", header_text, re.MULTILINE | re.IGNORECASE
        )
        if title_match:
            title = title_match.group(1).strip()

        # Author pattern: "Author: <author>"
        author_match = re.search(
            r"^Author:\s*(.+)$", header_text, re.MULTILINE | re.IGNORECASE
        )
        if author_match:
            authors = [author_match.group(1).strip()]

        # Language pattern: "Language: <language>"
        lang_match = re.search(
            r"^Language:\s*(.+)$", header_text, re.MULTILINE | re.IGNORECASE
        )
        if lang_match:
            language = lang_match.group(1).strip()

        return Metadata(title=title, authors=authors, language=language)

    def _get_gutenberg_chapters(self) -> list[Chapter]:
        """Extract chapters from Project Gutenberg TXT file.

        Splits the text into chapters based on common patterns like:
        - "CHAPTER I", "CHAPTER 1", "Chapter One"
        - "ONE", "TWO", etc. (capitalized chapter titles)
        - "PART I", etc.
        """
        encoding = detect_encoding(self.file_path)
        with open(self.file_path, encoding=encoding, errors="replace") as f:
            full_text = f.read()

        # Find the start and end markers
        start_match = re.search(
            r"\*\*\* START OF (?:THE|THIS) (?:PROJECT )?GUTENBERG (?:EBOOK|E-BOOK)",
            full_text,
            re.IGNORECASE,
        )
        end_match = re.search(
            r"\*\*\* END OF (?:THE|THIS) (?:PROJECT )?GUTENBERG (?:EBOOK|E-BOOK)",
            full_text,
            re.IGNORECASE,
        )

        # Extract content between markers
        if start_match:
            start_pos = start_match.end()
        else:
            start_pos = 0

        if end_match:
            end_pos = end_match.start()
        else:
            end_pos = len(full_text)

        content = full_text[start_pos:end_pos].strip()

        # Try to split by chapters
        # Pattern 1: "CHAPTER X" or "Chapter X" at start of line
        chapter_pattern = re.compile(
            r"^(?:CHAPTER|Chapter|PART|Part)\s+(?:[IVXLCDM]+|\d+|[A-Z][A-Z\s-]+)$",
            re.MULTILINE,
        )

        # Find all chapter markers
        chapter_matches = list(chapter_pattern.finditer(content))

        if len(chapter_matches) > 1:
            # We found chapters, split by them
            chapters = []
            for i, match in enumerate(chapter_matches):
                title = match.group(0).strip()
                start = match.end()
                end = (
                    chapter_matches[i + 1].start()
                    if i + 1 < len(chapter_matches)
                    else len(content)
                )
                text = content[start:end].strip()

                if text:  # Only add non-empty chapters
                    chapters.append(
                        Chapter(
                            title=title,
                            text=postprocess_extracted_text(
                                text,
                                self.postprocess_options,
                            ),
                            index=i,
                        )
                    )

            return chapters
        else:
            # No clear chapter structure, check for numbered sections
            # Pattern 2: Single words in all caps on own line
            # (like "ONE", "TWO", etc.)
            section_pattern = re.compile(r"^([A-Z][A-Z\s-]{2,})$", re.MULTILINE)
            section_matches = list(section_pattern.finditer(content))

            # Filter to likely chapter titles (not too long, appear multiple times)
            if len(section_matches) >= 3:
                chapters = []
                for i, match in enumerate(section_matches):
                    title = match.group(0).strip()
                    start = match.end()
                    end = (
                        section_matches[i + 1].start()
                        if i + 1 < len(section_matches)
                        else len(content)
                    )
                    text = content[start:end].strip()

                    if text and len(text) > 100:  # Only add substantial sections
                        chapters.append(
                            Chapter(
                                title=title,
                                text=postprocess_extracted_text(
                                    text,
                                    self.postprocess_options,
                                ),
                                index=i,
                            )
                        )

                if chapters:
                    return chapters

            # No chapter structure found, return entire content as one chapter
            metadata = self.get_metadata()
            title = metadata.title or self.file_path.stem
            return [
                Chapter(
                    title=title,
                    text=postprocess_extracted_text(
                        content,
                        self.postprocess_options,
                    ),
                    index=0,
                )
            ]

    def _get_ssmd_metadata(self) -> Metadata:
        """Extract metadata from an SSMD file."""
        content = self._read_ssmd_source()
        info = inspect_ssmd_document(content)
        if info.errors:
            raise SSMDValidationError(info.errors, self.file_path)
        return Metadata(
            title=info.title or self.file_path.stem, authors=[], language=None
        )

    def _get_ssmd_chapters(self) -> list[Chapter]:
        """Read an SSMD file as a single chapter."""
        content = self._read_ssmd_source()
        info = inspect_ssmd_document(content)
        if info.errors:
            raise SSMDValidationError(info.errors, self.file_path)
        return [
            Chapter(
                title=info.title or self.file_path.stem,
                text=content,
                index=0,
                is_ssmd=True,
            )
        ]

    def _read_ssmd_source(self) -> str:
        """Read an SSMD document without applying plain-text transforms."""
        encoding = detect_encoding(self.file_path)
        with open(self.file_path, encoding=encoding, errors="replace") as f:
            return f.read()

    # PDF methods (placeholder for future implementation)
    def _get_pdf_metadata(self) -> Metadata:
        """Extract metadata from PDF file.

        TODO: Implement PDF metadata extraction.
        """
        raise NotImplementedError("PDF support is not yet implemented")

    def _get_pdf_chapters(self) -> list[Chapter]:
        """Extract chapters from PDF file.

        TODO: Implement PDF chapter extraction.
        """
        raise NotImplementedError("PDF support is not yet implemented")


def _format_extraction_diagnostic(diagnostic: Any) -> str:
    """Render the public epub2text Diagnostic contract."""
    return f"{diagnostic.severity}: {diagnostic.code}: {diagnostic.message}"


def _epub_extraction_schema(kind: str) -> str:
    """Return a stable source schema/version identity for resume state."""
    try:
        import epub2text

        version = str(epub2text.__version__)
    except (ImportError, AttributeError):
        version = "unknown"
    return f"epub2text.{kind}/{version}"
