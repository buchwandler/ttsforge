"""Small user-facing options for audiobook conversion.

Synthesis semantics are translated to public Readio request types at the
integration boundary instead of being duplicated as TTSForge backend config.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudiobookOptions:
    """User-facing choices for one EPUB-to-audiobook operation."""

    source: Path
    project: Path | None = None
    chapters: str = "all"
    output: Path | None = None
    format: str = "m4b"
    language: str | None = None
    voice: str | None = None
    engine: str | None = None
    speed: float | None = None
    bitrate: str | None = None
    target_lufs: float | None = None
    offline: bool = False
    refresh: bool = False
    force: bool = False
    fresh: bool = False
    title: str | None = None
    author: str | None = None
    cover: Path | None = None
