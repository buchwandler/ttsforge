"""Resolve terminal interaction behavior once for a CLI invocation."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InteractionMode:
    interactive: bool
    json: bool
    live_progress: bool
    confirm: bool


def resolve_interaction_mode(
    *,
    json_mode: bool,
    assume_yes: bool,
    force_non_interactive: bool,
) -> InteractionMode:
    terminal = sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()
    interactive = terminal and not json_mode and not force_non_interactive
    return InteractionMode(
        interactive=interactive,
        json=json_mode,
        live_progress=interactive,
        confirm=interactive and not assume_yes,
    )
