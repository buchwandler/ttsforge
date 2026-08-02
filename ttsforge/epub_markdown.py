"""Defensive normalization for the Markdown profile emitted by epub2text.

This is intentionally not a general Markdown parser.  epub2text owns EPUB,
XHTML, CSS, and inline extraction; TTSForge only needs to validate and carry
the small Markdown dialect used as the SSMD generation boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class EpubMarkdownError(ValueError):
    """Raised when a chapter body violates the controlled Markdown profile."""


@dataclass(frozen=True)
class EpubMarkdownResult:
    """Normalized chapter Markdown and non-fatal profile diagnostics."""

    body: str
    diagnostics: tuple[str, ...] = ()


_FRONT_MATTER_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")
_LINK = re.compile(r"(?<!\\)\[([^\]\n]+)\]\([^\)\n]+\)")
_INLINE_CODE = re.compile(r"(?<!\\)`([^`\n]+)`")
_RAW_HTML = re.compile(r"<\/?[A-Za-z][^>]*>")
_UNMATCHED_LINK = re.compile(r"(?<!\\)\[[^\]\n]*$")


def normalize_epub_markdown(
    markdown_body: str,
    *,
    preserve_emphasis: bool = True,
) -> EpubMarkdownResult:
    """Validate and normalize an epub2text chapter Markdown body.

    The function only handles constructs that epub2text is configured to emit
    at this boundary.  It preserves headings, blank-line paragraphs, Unicode,
    escapes, and emphasis delimiters.  Links and inline code are unwrapped as
    a defensive measure because the reader requests that policy from epub2text.
    """
    if not isinstance(markdown_body, str):
        raise EpubMarkdownError("Chapter Markdown body must be a string")

    normalized = markdown_body.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    _reject_front_matter(lines)

    diagnostics: list[str] = []
    output: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```") or line.strip().startswith("~~~"):
            in_fence = not in_fence
            diagnostics.append("code_fence_unexpected")

        stripped = line.strip()
        if stripped in {"---", "***", "___"}:
            output.append("...p")
            continue

        if line.startswith("#######"):
            diagnostics.append("heading_level_out_of_range")
        if _RAW_HTML.search(line):
            diagnostics.append("raw_html_unexpected")
        if _UNMATCHED_LINK.search(line):
            diagnostics.append("unmatched_link_syntax")

        line = _unwrap_links_and_code(line, diagnostics)
        if not preserve_emphasis:
            line = _unwrap_emphasis(line)
        output.append(line.rstrip())

    if in_fence:
        diagnostics.append("unclosed_code_fence")

    while output and not output[0].strip():
        output.pop(0)
    while output and not output[-1].strip():
        output.pop()

    body = "\n".join(output)
    if body:
        body += "\n"
    return EpubMarkdownResult(body=body, diagnostics=tuple(dict.fromkeys(diagnostics)))


def normalize_epub_markdown_for_ssmd(
    markdown_body: str,
    *,
    preserve_emphasis: bool = True,
) -> str:
    """Return normalized Markdown, raising on invalid chapter front matter."""
    return normalize_epub_markdown(
        markdown_body,
        preserve_emphasis=preserve_emphasis,
    ).body


def markdown_structure_counts(markdown_body: str) -> dict[str, int]:
    """Count the controlled structural features for verbose diagnostics."""
    lines = markdown_body.splitlines()
    return {
        "headings": sum(1 for line in lines if re.match(r"^#{1,6}\s+", line)),
        "subheadings": sum(1 for line in lines if re.match(r"^#{2,6}\s+", line)),
        "moderate_spans": len(
            re.findall(r"(?<!\\)(?<!\*)\*(?!\*)(?:[^*\n]|\\.)+\*(?!\*)", markdown_body)
        ),
        "strong_spans": len(
            re.findall(r"(?<!\\)\*\*(?:[^*\n]|\\.)+\*\*", markdown_body)
        ),
        "scene_breaks": sum(1 for line in lines if line.strip() == "...p"),
    }


def _reject_front_matter(lines: list[str]) -> None:
    """Reject YAML-like front matter so TTSForge remains its sole owner."""
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None or lines[first].strip() != "---":
        return

    for line in lines[first + 1 : first + 33]:
        if line.strip() == "---":
            raise EpubMarkdownError(
                "Unexpected YAML front matter in EPUB chapter Markdown; "
                "TTSForge owns generated SSMD front matter"
            )
        if line.strip() and not _FRONT_MATTER_KEY.match(line.strip()):
            return


def _unwrap_links_and_code(line: str, diagnostics: list[str]) -> str:
    def unwrap_link(match: re.Match[str]) -> str:
        diagnostics.append("link_unwrapped")
        return match.group(1)

    def unwrap_code(match: re.Match[str]) -> str:
        diagnostics.append("inline_code_unwrapped")
        return match.group(1)

    line = _LINK.sub(unwrap_link, line)
    return _INLINE_CODE.sub(unwrap_code, line)


def _unwrap_emphasis(line: str) -> str:
    """Remove balanced emphasis delimiters while preserving literal asterisks."""
    previous = None
    result = line
    while result != previous:
        previous = result
        result = re.sub(
            r"(?<!\\)\*\*([^*\n]+?)\*\*",
            lambda match: match.group(1),
            result,
        )
        result = re.sub(
            r"(?<!\\)(?<!\*)\*([^*\n]+?)\*(?!\*)",
            lambda match: match.group(1),
            result,
        )
    return result
