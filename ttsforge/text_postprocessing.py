"""Postprocess extracted text before SSMD generation or playback."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


EPUB_CHAPTER_MARKER_PATTERN = re.compile(
    r"^\s*<<CHAPTER:[^>]*>>\s*\n*", re.MULTILINE
)
ELLIPSIS_PATTERN = re.compile(r"\.\.\.(?=\s|$)")


@dataclass(frozen=True)
class TextPostprocessOptions:
    """Controls for extracted-text postprocessing."""

    subchapter_markers: tuple[str, ...] = field(default_factory=tuple)


def normalize_marker_list(value: object) -> tuple[str, ...]:
    """Normalize configured or CLI marker values to a tuple of non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        marker = value.strip()
        return (marker,) if marker else ()
    if not isinstance(value, Iterable):
        return ()

    markers: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        marker = item.strip()
        if marker:
            markers.append(marker)
    return tuple(markers)


def resolve_text_postprocess_options(
    config: dict[str, Any],
    *,
    subchapter_markers: tuple[str, ...] | None = None,
) -> TextPostprocessOptions:
    """Resolve text postprocessing options with CLI > config > defaults."""
    markers = (
        normalize_marker_list(subchapter_markers)
        if subchapter_markers
        else normalize_marker_list(config.get("subchapter_markers"))
    )
    return TextPostprocessOptions(subchapter_markers=markers)


def postprocess_extracted_text(
    text: str,
    options: TextPostprocessOptions | None = None,
) -> str:
    """Apply safe postprocessing to extracted non-SSMD text."""
    opts = options or TextPostprocessOptions()
    result = EPUB_CHAPTER_MARKER_PATTERN.sub("", text, count=1)
    result = _apply_subchapter_markers(result, opts.subchapter_markers)
    result = ELLIPSIS_PATTERN.sub("\u2026", result)
    return result


def _apply_subchapter_markers(text: str, markers: tuple[str, ...]) -> str:
    if not markers:
        return text

    marker_set = set(markers)
    lines = text.splitlines(keepends=True)
    processed: list[str] = []
    for line in lines:
        line_body = line.rstrip("\r\n")
        line_ending = line[len(line_body) :]
        if line_body.strip() in marker_set:
            processed.append(f"...p{line_ending}")
        else:
            processed.append(line)
    return "".join(processed)
