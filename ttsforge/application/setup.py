"""Frontend-neutral setup merge and catalog-selection policy."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import replace
from typing import Any, Protocol, TypeVar

from .errors import CatalogSelectionError, SetupConflictError
from .models import AudiobookRequest, InputOverrides, SetupOrigins

T = TypeVar("T")


class LexiconChoice(Protocol):
    selector: str
    display_name: str | None


_SETUP_FIELDS = (
    "language",
    "engine",
    "model",
    "model_source",
    "quality",
    "voice",
    "speed",
    "spacy",
    "short_sentence",
    "lexicons",
    "clear_lexicons",
    "auto_lexicons",
    "g2p_fallback",
    "lexicon_data_policy",
    "allow_experimental",
    "voice_level",
    "pause_mode",
    "unit",
    "offline",
    "target_lufs",
    "format",
    "output",
    "bitrate",
    "title",
    "author",
    "cover",
)

_DEPENDENT_FIELDS = {
    "language": (
        "engine",
        "model",
        "model_source",
        "quality",
        "voice",
        "lexicons",
        "clear_lexicons",
        "auto_lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
    ),
    "engine": (
        "model",
        "model_source",
        "quality",
        "voice",
        "speed",
        "lexicons",
        "clear_lexicons",
        "auto_lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
    ),
    "model": (
        "quality",
        "voice",
        "lexicons",
        "clear_lexicons",
        "auto_lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
    ),
}

_RESET_VALUES: dict[str, object] = {
    "engine": None,
    "model": None,
    "model_source": None,
    "quality": None,
    "voice": None,
    "speed": None,
    "lexicons": None,
    "clear_lexicons": False,
    "auto_lexicons": False,
    "g2p_fallback": None,
    "lexicon_data_policy": None,
}


def invalidate_dependency_sources(
    sources: SetupOrigins, changed_field: str
) -> SetupOrigins:
    """Treat saved dependent fields as unresolved after a selector changes."""
    invalidated = frozenset(_DEPENDENT_FIELDS.get(changed_field, ()))
    return SetupOrigins(
        explicit=sources.explicit, project=sources.project - invalidated
    )


def reset_dependency_choices(
    options: AudiobookRequest, changed_field: str, pins: InputOverrides
) -> AudiobookRequest:
    """Clear choices invalidated by a selector change, except explicit CLI pins."""
    updates: dict[str, Any] = {
        field: value
        for field, value in _RESET_VALUES.items()
        if field in _DEPENDENT_FIELDS.get(changed_field, ())
        and not pins.includes(field)
    }
    return replace(options, **updates)


def _has_saved_value(options: AudiobookRequest, field: str) -> bool:
    value = getattr(options, field)
    if field in {"clear_lexicons", "auto_lexicons", "allow_experimental", "offline"}:
        return bool(value)
    if field == "lexicons":
        return value is not None or options.clear_lexicons or options.auto_lexicons
    return value is not None


def merge_saved_setup(
    cli_options: AudiobookRequest,
    saved_options: AudiobookRequest,
    pins: InputOverrides,
    *,
    interactive: bool = True,
) -> AudiobookRequest:
    """Merge saved project values with CLI pins and invalidate stale dependents."""
    updates = {
        field: getattr(saved_options, field)
        for field in _SETUP_FIELDS
        if not pins.includes(field)
    }
    merged = replace(cli_options, **updates)
    for changed_field in ("language", "engine", "model"):
        if not pins.includes(changed_field) or getattr(
            cli_options, changed_field
        ) == getattr(saved_options, changed_field):
            continue
        dependent = tuple(
            field
            for field in _DEPENDENT_FIELDS[changed_field]
            if not pins.includes(field) and _has_saved_value(saved_options, field)
        )
        if dependent and not interactive:
            conflicts = ", ".join(f"--{field.replace('_', '-')}" for field in dependent)
            raise SetupConflictError(
                f"Changing --{changed_field.replace('_', '-')} conflicts with saved "
                f"project settings {conflicts}. Use --reconfigure or pass compatible "
                "values explicitly."
            )
        merged = reset_dependency_choices(merged, changed_field, pins)
    return merged


def choose_catalog_item(
    *,
    value: str,
    rows: Sequence[T],
    default: str | None,
    keys: Callable[[T], Collection[str]],
) -> T | str:
    """Resolve row numbers and exact identifiers; return raw text for empty catalogs."""
    selection = value.strip()
    if not selection:
        if default is None:
            raise CatalogSelectionError("A selection is required.")
        matches = [row for row in rows if default in keys(row)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CatalogSelectionError(f"Default {default!r} is ambiguous.")
        return default

    if not rows:
        return selection

    if selection.isdecimal():
        row_number = int(selection)
        if 1 <= row_number <= len(rows):
            return rows[row_number - 1]
        raise CatalogSelectionError(f"Selection must be between 1 and {len(rows)}.")

    matches = [row for row in rows if selection in keys(row)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise CatalogSelectionError(
            f"Selection {selection!r} is ambiguous; enter a row number "
            "or exact identifier."
        )
    raise CatalogSelectionError(
        f"Unknown selection {selection!r}. Enter a row number or exact identifier."
    )


def parse_catalog_multi_selection(
    value: str,
    rows: Sequence[T],
    *,
    keys: Callable[[T], Collection[str]],
    selector: Callable[[T], str],
) -> tuple[str, ...]:
    """Parse comma-separated row numbers or exact identifiers, preserving order."""
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part for part in parts):
        raise CatalogSelectionError("Enter one or more comma-separated selections.")
    selected: list[str] = []
    for part in parts:
        item = choose_catalog_item(value=part, rows=rows, default=None, keys=keys)
        chosen = selector(item) if not isinstance(item, str) else item
        if chosen not in selected:
            selected.append(chosen)
    return tuple(selected)


def apply_lexicon_selection(
    options: AudiobookRequest, value: str, rows: Sequence[LexiconChoice]
) -> AudiobookRequest:
    """Apply automatic, disabled, or explicit-selector lexicon choices."""
    normalized = value.strip().casefold()
    if normalized == "auto":
        return replace(options, lexicons=None, clear_lexicons=False, auto_lexicons=True)
    if normalized == "none":
        return replace(options, lexicons=None, clear_lexicons=True, auto_lexicons=False)
    selectors = parse_catalog_multi_selection(
        value,
        rows,
        keys=lambda row: (row.selector, row.display_name or ""),
        selector=lambda row: row.selector,
    )
    return replace(
        options,
        lexicons=selectors,
        clear_lexicons=False,
        auto_lexicons=False,
    )
