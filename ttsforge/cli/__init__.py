"""CLI interface for ttsforge - convert EPUB to audiobooks.

This module serves as the main entry point for the ttsforge CLI, organizing
commands into logical groups:

- Conversion commands: convert, read, sample, list, info
- Phoneme commands: phonemes export/convert/preview/info
- Utility commands: voices, demo, download, config, extract-names, list-names
"""

import importlib
from pathlib import Path
from typing import Optional, cast

import click

from ..constants import PROGRAM_NAME
from .helpers import console, get_version

# Import all command modules

_COMMANDS = {
    "convert": ("ttsforge.cli.commands_conversion", "convert"),
    "list": ("ttsforge.cli.commands_conversion", "list_chapters"),
    "info": ("ttsforge.cli.commands_conversion", "info"),
    "sample": ("ttsforge.cli.commands_conversion", "sample"),
    "read": ("ttsforge.cli.commands_conversion", "read"),
    "voices": ("ttsforge.cli.commands_utility", "voices"),
    "demo": ("ttsforge.cli.commands_utility", "demo"),
    "download": ("ttsforge.cli.commands_utility", "download"),
    "config": ("ttsforge.cli.commands_utility", "config"),
    "short-sentence-advanced-config": (
        "ttsforge.cli.commands_utility",
        "short_sentence_advanced_config",
    ),
    "phonemes": ("ttsforge.cli.commands_phonemes", "phonemes"),
    "extract-names": ("ttsforge.cli.commands_utility", "extract_names"),
    "list-names": ("ttsforge.cli.commands_utility", "list_names"),
}

_COMMAND_HELP = {
    "config": "Manage ttsforge configuration.",
    "convert": "Convert an EPUB file to an audiobook.",
    "demo": "Generate a demo audio file with all voices.",
    "download": "Download ONNX model and voice files.",
    "extract-names": "Extract proper names from a book and dictionary.",
    "info": "Show metadata and information about an input file.",
    "list": "List chapters in a file.",
    "list-names": "List all names in a phoneme dictionary.",
    "phonemes": "Commands for working with phonemes and pre-tokenized content.",
    "read": "Read an EPUB or text file aloud with streaming playback.",
    "sample": "Generate a sample audio file to test TTS settings.",
    "short-sentence-advanced-config": "Create, link, or show advanced configuration.",
    "voices": "List available TTS voices.",
}


class LazyCommandGroup(click.Group):
    """Click group that imports command implementations only when needed."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        command_index = next(
            (index for index, arg in enumerate(args) if not arg.startswith("-")),
            None,
        )
        root_help = not args or (
            "--help" in args
            and (command_index is None or args.index("--help") < command_index)
        )
        ctx.meta["lightweight_help"] = root_help
        return super().parse_args(ctx, args)

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_COMMANDS)

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        target = _COMMANDS.get(name)
        if target is None:
            return None
        if ctx.meta.get("lightweight_help"):
            return click.Command(name, help=_COMMAND_HELP.get(name, ""))
        module_name, attr_name = target
        return cast(
            click.Command, getattr(importlib.import_module(module_name), attr_name)
        )


@click.group(cls=LazyCommandGroup, invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version and exit.")
@click.option(
    "--model",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to custom kokoro.onnx model file.",
)
@click.option(
    "--voices",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to custom voices.bin file.",
)
@click.pass_context
def main(
    ctx: click.Context, version: bool, model: Path | None, voices: Path | None
) -> None:
    """ttsforge - Generate audiobooks from EPUB files with TTS."""
    ctx.ensure_object(dict)
    ctx.obj["model_path"] = model
    ctx.obj["voices_path"] = voices
    if version:
        console.print(f"[bold]{PROGRAM_NAME}[/bold] version {get_version()}")
        return
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Export main for backward compatibility
__all__ = ["main"]


if __name__ == "__main__":
    main()
