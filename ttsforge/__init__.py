"""TTSForge: a user-friendly audiobook frontend to Readio."""

from __future__ import annotations

from importlib import import_module

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"

_EXPORTS = {
    "AudiobookApplicationService": (
        ".application.service",
        "AudiobookApplicationService",
    ),
    "AudiobookOptions": (".application.models", "AudiobookOptions"),
    "AudiobookRequest": (".application.models", "AudiobookRequest"),
    "LegacyWorkspaceError": (".application.errors", "LegacyWorkspaceError"),
    "ProjectPaths": (".application.models", "ProjectPaths"),
    "RichReadioProgress": (".progress", "RichReadioProgress"),
    "parse_chapter_selection": (".chapter_selection", "parse_chapter_selection"),
    "resolve_chapter_selection": (".chapter_selection", "resolve_chapter_selection"),
}

__all__ = [
    "AudiobookApplicationService",
    "AudiobookOptions",
    "AudiobookRequest",
    "LegacyWorkspaceError",
    "ProjectPaths",
    "RichReadioProgress",
    "__version__",
    "parse_chapter_selection",
    "resolve_chapter_selection",
]


def __getattr__(name: str) -> object:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
