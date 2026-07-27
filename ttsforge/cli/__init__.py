"""Typer CLI for :mod:`ttsforge`.

The command declarations are provider-independent. Command implementation
modules are imported only after Typer has parsed and validated an invocation.
"""

from __future__ import annotations

from typer.main import get_command

from .app import app, cli_main, phonemes_app


# Compatibility for integrations that pass the command to click.testing.CliRunner.
main = get_command(app)


__all__ = ["app", "cli_main", "main", "phonemes_app"]


if __name__ == "__main__":
    cli_main()
