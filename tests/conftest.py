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
        "ttsforge.cli.utility_light",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "console"):
            monkeypatch.setattr(module, "console", console)


@pytest.fixture
def runner(monkeypatch):
    """Create a CLI runner with deterministic terminal settings."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    monkeypatch.delenv("CLICOLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")
    from typer.testing import CliRunner

    return CliRunner()
