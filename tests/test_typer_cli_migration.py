"""Contract tests for the Typer CLI migration boundary."""

from __future__ import annotations

import subprocess
import sys

import typer
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

from ttsforge.cli import app, main


def test_public_app_is_typer() -> None:
    assert isinstance(app, typer.Typer)


def test_typer_runner_preserves_root_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "convert" in result.output
    assert "phonemes" in result.output


def test_legacy_click_command_alias_remains_invokable() -> None:
    result = ClickCliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "ttsforge version" in result.output
    assert callable(main)


def test_python_module_entrypoint_matches_console_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ttsforge", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ttsforge version" in result.stdout
