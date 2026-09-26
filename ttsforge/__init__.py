"""TTSForge: a user-friendly audiobook frontend to Readio."""

from __future__ import annotations

from .audiobook import AudiobookConverter, LegacyWorkspaceError, ProjectSetup
from .chapter_selection import parse_chapter_selection, resolve_chapter_selection
from .options import AudiobookOptions
from .progress import RichReadioProgress

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "AudiobookConverter",
    "AudiobookOptions",
    "LegacyWorkspaceError",
    "ProjectSetup",
    "RichReadioProgress",
    "__version__",
    "parse_chapter_selection",
    "resolve_chapter_selection",
]
