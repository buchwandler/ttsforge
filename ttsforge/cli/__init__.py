"""Typer CLI for :mod:`ttsforge`.

The command declarations are provider-independent. Command implementation
modules are imported only after Typer has parsed and validated an invocation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from typer.main import get_command

from ..constants import PROGRAM_NAME
from ._registration import register_commands
from .helpers import console, get_version


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]{PROGRAM_NAME}[/bold] version {get_version()}")
        raise typer.Exit()


app = typer.Typer(
    add_completion=True,
    invoke_without_command=True,
    no_args_is_help=False,
    help="ttsforge - Generate audiobooks from EPUB files with TTS.",
    rich_markup_mode=None,
)
phonemes_app = typer.Typer(
    add_completion=False,
    help="Commands for working with phonemes and pre-tokenized content.",
    rich_markup_mode=None,
)
app.add_typer(phonemes_app, name="phonemes")
register_commands(app, phonemes_app)


@app.callback()
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
    model: Annotated[
        Path | None,
        typer.Option(
            "--model",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to custom kokoro.onnx model file.",
        ),
    ] = None,
    voices: Annotated[
        Path | None,
        typer.Option(
            "--voices",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to custom voices.bin file.",
        ),
    ] = None,
) -> None:
    """Generate audiobooks from EPUB files with TTS."""
    del version
    ctx.ensure_object(dict)
    ctx.obj["model_path"] = model
    ctx.obj["voices_path"] = voices
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


# Compatibility for integrations that pass the command to click.testing.CliRunner.
main = get_command(app)


def cli_main() -> None:
    """Run the Typer application as the installed console script."""
    app(prog_name=PROGRAM_NAME)


__all__ = ["app", "cli_main", "main", "phonemes_app"]


if __name__ == "__main__":
    cli_main()
