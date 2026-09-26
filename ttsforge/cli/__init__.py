"""Typer command line interface for TTSForge."""

from __future__ import annotations

from typer.main import get_command

from .app import app, cli_main

# Compatibility for integrations that use click.testing.CliRunner.
main = get_command(app)

__all__ = ["app", "cli_main", "main"]

if __name__ == "__main__":
    cli_main()
