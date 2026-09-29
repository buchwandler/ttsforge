"""Frontend policy and selection helpers for guided synthesis setup."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from typing import Any, TypeVar

from readio.api import LexiconInfo

from .options import AudiobookOptions

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CliPins:
    """Fields whose values were explicitly supplied to the CLI."""

    fields: frozenset[str]

    def pinned(self, field: str) -> bool:
        """Return whether the CLI explicitly supplied ``field``."""
        return field in self.fields

    @classmethod
    def from_cli_values(cls, **values: object) -> CliPins:
        """Build provenance from raw Typer values before option normalization."""
        return cls(
            frozenset(
                name
                for name, value in values.items()
                if value is not None and value is not False
            )
        )


@dataclass(frozen=True, slots=True)
class SetupSources:
    """Field provenance used to decide whether guided setup must ask a question."""

    cli: frozenset[str] = frozenset()
    project: frozenset[str] = frozenset()

    def prompt_required(self, field: str, *, reconfigure: bool = False) -> bool:
        if field in self.cli:
            return False
        return not (field in self.project and not reconfigure)


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
    "lexicons": None,
    "clear_lexicons": False,
    "auto_lexicons": False,
    "g2p_fallback": None,
    "lexicon_data_policy": None,
}


def invalidate_dependency_sources(
    sources: SetupSources, changed_field: str
) -> SetupSources:
    """Treat saved dependent fields as unresolved after a selector changes."""
    invalidated = frozenset(_DEPENDENT_FIELDS.get(changed_field, ()))
    return replace(sources, project=sources.project - invalidated)


def reset_dependency_choices(
    options: AudiobookOptions, changed_field: str, pins: CliPins
) -> AudiobookOptions:
    """Clear choices invalidated by a selector change, except explicit CLI pins."""
    updates: dict[str, Any] = {
        field: value
        for field, value in _RESET_VALUES.items()
        if field in _DEPENDENT_FIELDS.get(changed_field, ()) and not pins.pinned(field)
    }
    return replace(options, **updates)


def _has_saved_value(options: AudiobookOptions, field: str) -> bool:
    value = getattr(options, field)
    if field in {"clear_lexicons", "auto_lexicons", "allow_experimental", "offline"}:
        return bool(value)
    if field == "lexicons":
        return value is not None or options.clear_lexicons or options.auto_lexicons
    return value is not None


def merge_saved_setup(
    cli_options: AudiobookOptions,
    saved_options: AudiobookOptions,
    pins: CliPins,
    *,
    interactive: bool = True,
) -> AudiobookOptions:
    """Merge saved project values with CLI pins and invalidate stale dependents."""
    updates = {
        field: getattr(saved_options, field)
        for field in _SETUP_FIELDS
        if not pins.pinned(field)
    }
    merged = replace(cli_options, **updates)
    for changed_field in ("language", "engine", "model"):
        if not pins.pinned(changed_field) or getattr(
            cli_options, changed_field
        ) == getattr(saved_options, changed_field):
            continue
        dependent = tuple(
            field
            for field in _DEPENDENT_FIELDS[changed_field]
            if not pins.pinned(field) and _has_saved_value(saved_options, field)
        )
        if dependent and not interactive:
            conflicts = ", ".join(f"--{field.replace('_', '-')}" for field in dependent)
            raise ValueError(
                f"Changing --{changed_field.replace('_', '-')} conflicts with saved "
                f"project settings {conflicts}. Use --reconfigure or pass compatible "
                "values explicitly."
            )
        merged = reset_dependency_choices(merged, changed_field, pins)
    return merged


class CatalogSelectionError(ValueError):
    """A deterministic row or public-identifier selection was invalid."""


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
    options: AudiobookOptions, value: str, rows: Sequence[LexiconInfo]
) -> AudiobookOptions:
    """Apply Readio's auto, disabled, or explicit-selector lexicon request mode."""
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
