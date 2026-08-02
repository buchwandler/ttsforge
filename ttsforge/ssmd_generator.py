"""SSMD (Speech Synthesis Markdown) generator for ttsforge.

This module converts chapter text to SSMD format with markup for:
- Emphasis (*text* for moderate, **text** for strong)
- Language switches ([text]{lang="lang_code"})
- Phoneme substitutions ([word]{ph="phoneme"})

Note: Structural breaks (paragraphs, sentences, clauses) are NOT automatically
added. The SSMD parser in pykokoro handles sentence detection automatically.
Users can manually add breaks in the SSMD file if desired:
- Paragraph breaks (...p)
- Sentence breaks (...s)
- Clause breaks (...c)
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from .epub_markdown import normalize_epub_markdown
from .ssmd_support import (
    SSMDPolicy,
    SSMDValidationError,
    format_issue,
    inspect_ssmd_document,
    validate_ssmd_document,
)


class SSMDGenerationError(Exception):
    """Exception raised when SSMD generation fails."""

    pass


def hash_ssmd_content(content: str) -> str:
    """Generate a hash of content for change detection.

    Args:
        content: Text content to hash

    Returns:
        12-character hex hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def _hash_content(content: str) -> str:
    """Compatibility alias for the canonical SSMD SHA-256 hash."""
    return hash_ssmd_content(content)


def _inject_phoneme_substitutions(
    text: str, phoneme_dict: dict[str, str], case_sensitive: bool = False
) -> str:
    """Inject canonical SSMD 0.8 ``[word]{ph="phoneme"}`` annotations.

    Args:
        text: Text to process
        phoneme_dict: Dictionary mapping words to IPA phonemes
        case_sensitive: Whether to match case-sensitively

    Returns:
        Text with phoneme substitutions injected
    """
    if not phoneme_dict:
        return text

    words = [word for word in phoneme_dict.keys() if word]
    if not words:
        return text

    words = sorted(words, key=len, reverse=True)
    alternation = "|".join(re.escape(word) for word in words)
    boundary_pattern = rf"(?<!\w)({alternation})(?!\w)"
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = re.compile(boundary_pattern, flags=flags)

    if case_sensitive:
        lookup = phoneme_dict
    else:
        lookup = {}
        for word, phoneme in phoneme_dict.items():
            key = word.lower()
            if key not in lookup:
                lookup[key] = phoneme

    def replace(match: re.Match[str]) -> str:
        matched_word = match.group(1)
        key = matched_word if case_sensitive else matched_word.lower()
        phoneme = lookup.get(key)
        if not phoneme:
            return matched_word
        clean_phoneme = phoneme.strip("/")
        return f"[{matched_word}]" + "{" + f'ph="{clean_phoneme}"' + "}"

    return _transform_visible_markdown(
        text,
        lambda segment: compiled.sub(replace, segment),
    )


def _transform_visible_markdown(text: str, transform: Any) -> str:
    """Transform visible text while protecting Markdown and SSMD syntax."""
    parts: list[str] = []
    visible: list[str] = []

    def flush_visible() -> None:
        if visible:
            parts.append(transform("".join(visible)))
            visible.clear()

    index = 0
    line_start = True
    while index < len(text):
        if line_start:
            heading = re.match(r"^#{1,6}\s+", text[index:])
            if heading:
                flush_visible()
                parts.append(heading.group(0))
                index += len(heading.group(0))
                line_start = False
                continue
            if text.startswith("...p", index):
                flush_visible()
                parts.append("...p")
                index += 4
                line_start = False
                continue

        if text[index] == "\\" and index + 1 < len(text):
            flush_visible()
            parts.append(text[index : index + 2])
            index += 2
            line_start = False
            continue
        if text.startswith("**", index):
            flush_visible()
            parts.append("**")
            index += 2
            line_start = False
            continue
        if text[index] == "*":
            flush_visible()
            parts.append("*")
            index += 1
            line_start = False
            continue
        if text[index] == "[":
            close = text.find("]", index + 1)
            if close >= 0 and close + 1 < len(text) and text[close + 1] == "{":
                end = text.find("}", close + 2)
                if end >= 0:
                    flush_visible()
                    parts.append(text[index : end + 1])
                    index = end + 1
                    line_start = False
                    continue

        char = text[index]
        visible.append(char)
        index += 1
        line_start = char == "\n"

    flush_visible()
    return "".join(parts)


def _add_language_markers(text: str, mixed_language_config: dict | None = None) -> str:
    """Add language markers for mixed-language segments.

    Note: This is a placeholder for now. Full implementation would require
    language detection library (lingua-language-detector).

    Args:
        text: Text to process
        mixed_language_config: Configuration for mixed-language mode

    Returns:
        Text with language markers (currently returns text unchanged)
    """
    # TODO: Implement language detection and wrapping
    # For now, return text unchanged
    # Future: Use lingua-language-detector to identify foreign segments
    # and wrap them with ``[segment]{lang="lang_code"}``.
    return text


def _add_structural_breaks(text: str) -> str:
    """Preserve paragraph structure without adding automatic SSMD breaks.

    The SSMD parser in pykokoro will handle sentence detection automatically.
    This function only preserves existing paragraph breaks as double newlines.

    Args:
        text: Plain text to process

    Returns:
        Text with normalized paragraph spacing (no SSMD break markers)
    """
    # Split into paragraphs and normalize spacing
    paragraphs = re.split(r"\n\s*\n+", text)
    result_paragraphs = []

    for para in paragraphs:
        para = para.strip()
        if para:
            result_paragraphs.append(para)

    # Join paragraphs with double newlines (standard paragraph separation)
    # No SSMD markers - let pykokoro's parser handle sentence detection
    result = "\n\n".join(result_paragraphs)

    return result


def _strip_redundant_title(chapter_title: str, chapter_text: str) -> str:
    """Remove a duplicated chapter title from the start of the text."""
    title = chapter_title.strip()
    if not title:
        return chapter_text

    lines = chapter_text.splitlines()
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break

    if first_idx is None:
        return chapter_text

    first_line = lines[first_idx]
    title_pattern = re.compile(
        rf"^\s*{re.escape(title)}(?:\b|[\s:;\-\u2013\u2014])",
        re.IGNORECASE,
    )
    if not title_pattern.search(first_line):
        return chapter_text

    trimmed_line = title_pattern.sub("", first_line, count=1).lstrip(
        " \t:;-\u2013\u2014"
    )
    if trimmed_line:
        lines[first_idx] = trimmed_line
        return "\n".join(lines[first_idx:]).lstrip()

    remaining = lines[first_idx + 1 :]
    while remaining and not remaining[0].strip():
        remaining = remaining[1:]
    return "\n".join(remaining).lstrip()


def _strip_redundant_markdown_title(chapter_title: str, chapter_markdown: str) -> str:
    """Remove one exact leading Markdown heading duplicated by navigation."""
    title = re.sub(r"\\([\\`*{}\[\]<>|~_])", r"\1", chapter_title.strip())
    lines = chapter_markdown.splitlines()
    first = next((idx for idx, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return chapter_markdown
    match = re.match(r"^#{1,6}\s+(.+?)\s*$", lines[first])
    if not match or match.group(1).strip().casefold() != title.casefold():
        return chapter_markdown
    remaining = lines[first + 1 :]
    while remaining and not remaining[0].strip():
        remaining.pop(0)
    body = "\n".join(remaining).strip("\n")
    return f"{body}\n" if body else ""


def chapter_to_ssmd(
    chapter_title: str,
    chapter_text: str,
    phoneme_dict: dict[str, str] | None = None,
    phoneme_dict_case_sensitive: bool = False,
    mixed_language_config: dict | None = None,
    *,
    chapter_markdown: str | None = None,
    source_format: Literal["plain", "markdown"] = "plain",
    include_title: bool = True,
    document_header: Mapping[str, Any] | None = None,
) -> str:
    """Convert a chapter to SSMD format.

    Args:
        chapter_title: Title of the chapter
        chapter_text: Plain text content of the chapter
        phoneme_dict: Optional dictionary mapping words to IPA phonemes
        phoneme_dict_case_sensitive: Whether phoneme matching is case-sensitive
        mixed_language_config: Optional config for mixed-language mode
        chapter_markdown: epub2text-generated Markdown body without a title
        source_format: Source representation used for this chapter
        include_title: Whether to include chapter title in SSMD
        document_header: Optional explicit header values.  Missing generated
            fields are filled without replacing explicit document values.

    Returns:
        SSMD formatted text

    Raises:
        SSMDGenerationError: If generation fails
    """
    try:
        if source_format == "markdown":
            if chapter_markdown is None:
                raise SSMDGenerationError(
                    "Markdown source format requires chapter_markdown"
                )
            result = _strip_redundant_markdown_title(
                chapter_title,
                normalize_epub_markdown(chapter_markdown).body,
            )
        else:
            result = chapter_text
            if include_title and chapter_title:
                result = _strip_redundant_title(chapter_title, result)
            result = _add_structural_breaks(result)

        # Apply visible-text transformations without changing Markdown syntax.
        if phoneme_dict:
            result = _inject_phoneme_substitutions(
                result, phoneme_dict, phoneme_dict_case_sensitive
            )

        # Step 4: Add language markers (if mixed-language mode)
        if mixed_language_config and mixed_language_config.get("use_mixed_language"):
            result = _add_language_markers(result, mixed_language_config)

        # Add exactly one synthetic chapter title when requested.
        if include_title and chapter_title:
            # Clean title and add as heading with double newline separation
            clean_title = chapter_title.strip()
            result = f"# {clean_title}\n\n{result}"

        from ssmd import merge_generated_header, serialize_front_matter

        generated_header: dict[str, Any] = {}
        if chapter_title:
            generated_header["title"] = chapter_title.strip()
        header = merge_generated_header(dict(document_header or {}), generated_header)
        return serialize_front_matter(header, result)

    except Exception as e:
        raise SSMDGenerationError(
            f"Failed to generate SSMD for chapter '{chapter_title}': {str(e)}"
        ) from e


def save_ssmd_file(
    ssmd_content: str,
    output_path: Path,
    *,
    policy: SSMDPolicy | None = None,
) -> str:
    """Save SSMD content to a file and return its hash.

    Args:
        ssmd_content: SSMD formatted text
        output_path: Path to save the SSMD file

    Returns:
        Hash of the saved content

    Raises:
        SSMDGenerationError: If file save fails
    """
    try:
        validate_ssmd_document(ssmd_content, policy=policy or SSMDPolicy())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(ssmd_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, output_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return hash_ssmd_content(ssmd_content)
    except SSMDValidationError as e:
        raise SSMDGenerationError(str(e)) from e
    except Exception as e:
        raise SSMDGenerationError(
            f"Failed to save SSMD file to {output_path}: {str(e)}"
        ) from e


def load_ssmd_file(ssmd_path: Path) -> tuple[str, str]:
    """Load SSMD file and return content with hash.

    Args:
        ssmd_path: Path to the SSMD file

    Returns:
        Tuple of (content, hash)

    Raises:
        SSMDGenerationError: If file load fails or doesn't exist
    """
    try:
        if not ssmd_path.exists():
            raise SSMDGenerationError(f"SSMD file not found: {ssmd_path}")

        with open(ssmd_path, encoding="utf-8") as f:
            content = f.read()

        return content, _hash_content(content)
    except SSMDGenerationError:
        raise
    except Exception as e:
        raise SSMDGenerationError(
            f"Failed to load SSMD file from {ssmd_path}: {str(e)}"
        ) from e


def validate_ssmd(ssmd_content: str) -> list[str]:
    """Validate SSMD content through SSMD 0.8 and the Kokoro profile.

    Args:
        ssmd_content: SSMD formatted text

    Returns:
        List of warning strings. Empty list means no issues found.
    """
    info = inspect_ssmd_document(ssmd_content, policy=SSMDPolicy())
    return [
        format_issue(issue)
        for issue in info.issues
        if issue.severity in {"warn", "error"}
    ]


def merge_ssmd_document_header(
    existing_content: str,
    generated_header: Mapping[str, Any],
) -> str:
    """Merge generated fields without replacing explicit header values."""

    from ssmd import merge_generated_header, parse_front_matter, serialize_front_matter

    front_matter = parse_front_matter(existing_content)
    if not front_matter.present:
        return serialize_front_matter(dict(generated_header), existing_content)
    merged = merge_generated_header(front_matter.data, generated_header)
    return serialize_front_matter(merged, front_matter.body)
