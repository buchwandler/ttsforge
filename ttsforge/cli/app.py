"""Application construction for the provider-independent TTSForge CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperCommand, TyperGroup

from ..constants import PROGRAM_NAME
from .helpers import get_version


def _sync_rich_terminal() -> None:
    """Apply terminal color environment variables at help-render time.

    Typer snapshots ``GITHUB_ACTIONS`` and related variables when
    ``typer.rich_utils`` is imported.  That makes a later ``NO_COLOR=1``
    change ineffective, which is especially visible in CliRunner-based tests
    and other embedded uses of the CLI.
    """
    from typer import rich_utils

    if os.getenv("NO_COLOR"):
        rich_utils.FORCE_TERMINAL = False
    elif any(
        os.getenv(name)
        for name in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS", "CLICOLOR_FORCE")
    ):
        rich_utils.FORCE_TERMINAL = True
    else:
        rich_utils.FORCE_TERMINAL = None


class _ColorAwareTyperCommand(TyperCommand):
    """Typer command that evaluates color policy for every help request."""

    def format_help(self, ctx, formatter):  # type: ignore[no-untyped-def]
        _sync_rich_terminal()
        return super().format_help(ctx, formatter)


class _ColorAwareTyperGroup(TyperGroup):
    """Typer group that evaluates color policy for every help request."""

    def format_help(self, ctx, formatter):  # type: ignore[no-untyped-def]
        _sync_rich_terminal()
        return super().format_help(ctx, formatter)


class _ColorAwareTyper(typer.Typer):
    """Typer application whose generated commands share the color policy."""

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("cls", _ColorAwareTyperGroup)
        super().__init__(*args, **kwargs)

    def command(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("cls", _ColorAwareTyperCommand)
        return super().command(*args, **kwargs)


def _version_callback(value: bool) -> None:
    if value:
        # Version output is a machine-readable boundary.  Do not send it
        # through Rich, which may add ANSI markup under FORCE_COLOR.
        typer.echo(f"{PROGRAM_NAME} version {get_version()}")
        raise typer.Exit()


app = _ColorAwareTyper(
    add_completion=True,
    invoke_without_command=True,
    no_args_is_help=False,
    help="ttsforge - Generate audiobooks from EPUB files with TTS.",
    rich_markup_mode="rich",
)
phonemes_app = _ColorAwareTyper(
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
