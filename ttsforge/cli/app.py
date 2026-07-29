"""Application construction for the provider-independent TTSForge CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..constants import PROGRAM_NAME
from .helpers import get_version


def _version_callback(value: bool) -> None:
    if value:
        # Version output is a machine-readable boundary.  Do not send it
        # through Rich, which may add ANSI markup under FORCE_COLOR.
        typer.echo(f"{PROGRAM_NAME} version {get_version()}")
        raise typer.Exit()


app = typer.Typer(
    add_completion=True,
    invoke_without_command=True,
    no_args_is_help=False,
    help="ttsforge - Generate audiobooks from EPUB files with TTS.",
    rich_markup_mode="rich",
)
phonemes_app = typer.Typer(
    add_completion=False,
    help="Commands for working with phonemes and pre-tokenized content.",
    rich_markup_mode="rich",
)
app.add_typer(phonemes_app, name="phonemes")


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


def cli_main() -> None:
    """Run the Typer application as the installed console script."""
    app(prog_name=PROGRAM_NAME)


from . import typer_conversion, typer_phonemes, typer_ssmd, typer_utility  # noqa: E402

typer_conversion.register(app)
typer_ssmd.register(app)
typer_phonemes.register(phonemes_app)
typer_utility.register(app)
