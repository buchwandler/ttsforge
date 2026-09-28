"""Frontend policy and selection helpers for guided synthesis setup."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar

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
