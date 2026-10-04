"""Backward-compatible imports for guided synthesis setup helpers."""

from __future__ import annotations

from .application.errors import CatalogSelectionError
from .application.models import AudiobookRequest, InputOverrides, SetupOrigins
from .application.setup import (
    apply_lexicon_selection,
    choose_catalog_item,
    invalidate_dependency_sources,
    merge_saved_setup,
    parse_catalog_multi_selection,
    reset_dependency_choices,
)


class CliPins(InputOverrides):
    """Compatibility name for frontend-neutral input overrides."""

    def pinned(self, field: str) -> bool:
        return self.includes(field)

    @classmethod
    def from_cli_values(cls, **values: object) -> CliPins:
        """Build legacy CLI provenance from raw Typer values."""
        return cls(
            frozenset(
                name
                for name, value in values.items()
                if value is not None and value is not False
            )
        )


class SetupSources(SetupOrigins):
    """Compatibility adapter for the former CLI/project provenance model."""

    def __init__(
        self,
        cli: frozenset[str] = frozenset(),
        project: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(explicit=cli, project=project)

    @property
    def cli(self) -> frozenset[str]:
        return self.explicit

    def prompt_required(self, field: str, *, reconfigure: bool = False) -> bool:
        return self.needs_input(field, reconfigure=reconfigure)


__all__ = [
    "AudiobookRequest",
    "CatalogSelectionError",
    "CliPins",
    "InputOverrides",
    "SetupOrigins",
    "SetupSources",
    "apply_lexicon_selection",
    "choose_catalog_item",
    "invalidate_dependency_sources",
    "merge_saved_setup",
    "parse_catalog_multi_selection",
    "reset_dependency_choices",
]
