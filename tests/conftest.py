"""Shared test-environment controls."""

import sys

import pytest
from rich.console import Console


@pytest.fixture(autouse=True)
def deterministic_rich_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Rich output stable across terminal width and color settings."""
    console = Console(
        width=240,
        color_system=None,
        force_terminal=False,
        highlight=False,
    )
    for module_name in (
        "ttsforge.cli",
        "ttsforge.cli.helpers",
        "ttsforge.cli.commands_conversion",
        "ttsforge.cli.commands_phonemes",
        "ttsforge.cli.commands_utility",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "console"):
            monkeypatch.setattr(module, "console", console)
