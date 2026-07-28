"""Explicit, typed Typer wrappers for utility commands."""

# The explicit command signatures intentionally retain long help declarations.
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, cast

import typer
from typer.core import TyperCommand, TyperGroup


class RepeatedPairGroup(TyperGroup):
    """Make the compatibility ``--set KEY VALUE`` option repeatable."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for parameter in self.params:
            if parameter.name == "set_option":
                parameter.multiple = True
                parameter.default = ()


class ShortSentenceConfigCommand(TyperCommand):
    """Append the lightweight advanced-config path to command help."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        super().format_help(ctx, formatter)
        from ..paths import get_advanced_short_sentence_config_path

        formatter.write_paragraph()
        formatter.write(
            "Advanced short-sentence config path: "
            f"{get_advanced_short_sentence_config_path()}\n"
        )


def _action_callback(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in {"show", "init", "reset"}:
        raise typer.BadParameter("must be one of: show, init, reset")
    return normalized


LanguageCode = Literal["a", "b", "d", "e", "f", "h", "i", "j", "p", "z"]
ModelQuality = Literal[
    "fp32", "fp16", "q8", "q8f16", "q4", "q4f16", "uint8", "uint8f16"
]
SortMode = Literal["name", "count", "alpha"]


def voices_command(
    language: Annotated[
        LanguageCode | None,
        typer.Option(
            "-l",
            "--language",
            help="Filter voices by language (default: all languages).",
        ),
    ] = None,
) -> None:
    "List available TTS voices."
    from .utility_light import voices

    voices(language=language)


def demo_command(
    ctx: typer.Context,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output file path (default: ./voices_demo.wav).",
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    language: Annotated[
        LanguageCode | None,
        typer.Option(
            "-l",
            "--language",
            help="Filter voices by language (default: all languages).",
        ),
    ] = None,
    voices_filter: Annotated[
        str | None,
        typer.Option(
            "-v",
            "--voice",
            help="Specific voices to include (comma-separated, e.g., 'af_heart,am_adam').",
        ),
    ] = None,
    speed: Annotated[
        float, typer.Option("-s", "--speed", help="Speech speed (default: 1.0).")
    ] = 1.0,
    use_gpu: Annotated[
        bool | None,
        typer.Option(
            "--gpu/--no-gpu",
            help="Compatibility shortcut: --gpu maps to provider=auto and --no-gpu maps to provider=cpu.",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            help="ONNX Runtime execution provider or alias (auto, cpu, nnapi, xnnpack, or a full *ExecutionProvider name).",
        ),
    ] = None,
    silence: Annotated[
        float,
        typer.Option(
            "--silence", help="Silence between voice samples in seconds (default: 0.5)."
        ),
    ] = 0.5,
    text: Annotated[
        str | None,
        typer.Option(
            "--text",
            help="Custom text to use (use {voice} placeholder for voice name).",
        ),
    ] = None,
    separate: Annotated[
        bool,
        typer.Option(
            "--separate",
            help="Save each voice as a separate file instead of concatenating.",
        ),
    ] = False,
    blend: Annotated[
        str | None,
        typer.Option(
            "--blend", help="Voice blend to demo (e.g., 'af_nicole:50,am_michael:50')."
        ),
    ] = None,
    blend_presets: Annotated[
        bool,
        typer.Option(
            "--blend-presets", help="Demo a curated set of voice blend combinations."
        ),
    ] = False,
    play_audio: Annotated[
        bool,
        typer.Option(
            "-p",
            "--play",
            help="Play audio directly (also saves to file if -o specified).",
        ),
    ] = False,
) -> None:
    'Generate a demo audio file with all available voices.\n\nCreates a single audio file with samples from each voice, or separate files\nfor each voice with --separate. Great for previewing and comparing voices.\n\nSupports voice blending with --blend or --blend-presets options.\n\nExamples:\n\n    ttsforge demo\n\n    ttsforge demo -l a  # Only American English voices\n\n    ttsforge demo -v af_heart,am_adam  # Specific voices\n\n    ttsforge demo --separate -o ./voices/  # Separate files in directory\n\n    ttsforge demo --text "Custom message from {voice}!"\n\n    ttsforge demo --blend "af_nicole:50,am_michael:50"  # Custom voice blend\n\n    ttsforge demo --blend-presets  # Demo all preset voice blends\n\n    ttsforge demo --play  # Play directly without saving\n\n    ttsforge demo -v af_heart --play  # Play a single voice demo'
    from .commands_utility import demo

    demo(
        ctx=ctx,
        output=output,
        language=language,
        voices_filter=voices_filter,
        speed=speed,
        use_gpu=use_gpu,
        provider=provider,
        silence=silence,
        text=text,
        separate=separate,
        blend=blend,
        blend_presets=blend_presets,
        play_audio=play_audio,
    )


def download_command(
    ctx: typer.Context,
    force: Annotated[
        bool, typer.Option("--force", help="Force re-download even if files exist.")
    ] = False,
    quality: Annotated[
        ModelQuality | None,
        typer.Option(
            "--quality",
            "-q",
            help="Model quality/quantization level. Default: from config or fp32.",
        ),
    ] = None,
) -> None:
    "Download ONNX model and voice files required for TTS.\n\nDownloads from Hugging Face (onnx-community/Kokoro-82M-v1.0-ONNX).\n\nQuality options:\n  fp32     - Full precision (326 MB) - Best quality, default\n  fp16     - Half precision (163 MB) - Good quality, smaller\n  q8       - 8-bit quantized (92 MB) - Good quality, compact\n  q8f16    - 8-bit with fp16 (86 MB) - Smallest file\n  q4       - 4-bit quantized (305 MB)\n  q4f16    - 4-bit with fp16 (155 MB)\n  uint8    - Unsigned 8-bit (177 MB)\n  uint8f16 - Unsigned 8-bit with fp16 (114 MB)"
    from .commands_utility import download

    download(ctx=ctx, force=force, quality=quality)


def config_command(
    ctx: typer.Context,
    show: Annotated[
        bool, typer.Option("--show", help="Show current configuration.")
    ] = False,
    reset: Annotated[
        bool, typer.Option("--reset", help="Reset configuration to defaults.")
    ] = False,
    set_option: Annotated[
        tuple[str, str] | None,
        typer.Option("--set", help="Set a configuration option.", metavar="KEY VALUE"),
    ] = None,
) -> None:
    "Manage ttsforge configuration.\n\nConfiguration is stored in ~/.config/ttsforge/config.json"
    has_legacy_action = show or reset or bool(set_option)

    if ctx.invoked_subcommand is not None:
        if has_legacy_action:
            typer.echo(
                "Error: config options cannot be combined with a config subcommand",
                err=True,
            )
            raise typer.Exit(code=2)
        return

    from .utility_light import config

    config(
        show=show,
        reset=reset,
        set_option=cast(tuple[tuple[str, str], ...], set_option or ()),
    )


def short_sentence_config_command(
    ctx: typer.Context,
    action: Annotated[
        str | None,
        typer.Argument(metavar="ACTION", callback=_action_callback),
    ] = None,
) -> None:
    "Create, link, or show the advanced short-sentence JSON configuration.\n\nACTION is 'init', 'show', or 'reset'. Called without ACTION, this help is\nshown."
    from .utility_light import short_sentence_advanced_config

    short_sentence_advanced_config(ctx=ctx, action=action)


def legacy_short_sentence_advanced_config_command(
    ctx: typer.Context,
    action: Annotated[
        str | None,
        typer.Argument(metavar="ACTION", callback=_action_callback),
    ] = None,
) -> None:
    """Compatibility alias for ``config short-sentence``."""
    typer.echo(
        "Deprecated: use 'ttsforge config short-sentence ACTION'.",
        err=True,
    )
    short_sentence_config_command(ctx=ctx, action=action)


def extract_names_command(
    input_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output JSON file path (default: INPUT_FILE_custom_phonemes.json).",
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    min_count: Annotated[
        int,
        typer.Option(
            "--min-count",
            help="Minimum occurrences for a name to be included (default: 3).",
        ),
    ] = 3,
    max_names: Annotated[
        int,
        typer.Option(
            "--max-names", help="Maximum number of names to extract (default: 500)."
        ),
    ] = 500,
    language: Annotated[
        LanguageCode,
        typer.Option(
            "-l", "--language", help="Language for phoneme generation (default: a)."
        ),
    ] = "a",
    include_all: Annotated[
        bool,
        typer.Option(
            "--include-all",
            help="Include all detected proper nouns (ignore min-count).",
        ),
    ] = False,
    preview: Annotated[
        bool,
        typer.Option(
            "--preview", help="Preview extracted names without saving to file."
        ),
    ] = False,
    chunk_size: Annotated[
        int,
        typer.Option(
            "--chunk-size",
            help="Characters per chunk for processing (default: 100000).",
        ),
    ] = 100000,
    chapters: Annotated[
        str | None,
        typer.Option(
            "--chapters",
            help="Specific chapters to process (e.g., '1,3,5-10' or 'all'). Default: all.",
        ),
    ] = None,
) -> None:
    "Extract proper names from a book and generate phoneme dictionary.\n\nScans INPUT_FILE (EPUB or TXT) for proper names and creates a JSON phoneme\ndictionary with auto-generated pronunciation suggestions. You can then review\nand edit the suggestions before using them for TTS conversion.\n\nExamples:\n\n    \n    # Extract names and save to default file\n    ttsforge extract-names mybook.epub\n\n    \n    # Preview names without saving\n    ttsforge extract-names mybook.epub --preview\n\n    \n    # Extract frequent names only (10+ occurrences)\n    ttsforge extract-names mybook.epub --min-count 10 -o names.json\n\n    \n    # Extract from specific chapters\n    ttsforge extract-names mybook.epub --chapters 1,3,5-10\n\n    \n    # Extract from chapter range\n    ttsforge extract-names mybook.epub --start 5 --end 15\n\n    \n    # Then use the dictionary for conversion\n    ttsforge convert mybook.epub --phoneme-dict custom_phonemes.json"
    from .commands_utility import extract_names

    extract_names(
        input_file=input_file,
        output=output,
        min_count=min_count,
        max_names=max_names,
        language=language,
        include_all=include_all,
        preview=preview,
        chunk_size=chunk_size,
        chapters=chapters,
    )


def list_names_command(
    phoneme_dict: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ],
    sort_by: Annotated[
        SortMode,
        typer.Option(
            "--sort-by",
            help="Sort by: name (same as alpha), count (occurrences), alpha (alphabetical).",
        ),
    ] = "count",
    play: Annotated[
        bool,
        typer.Option(
            "--play", help="Play audio preview for each name (interactive mode)."
        ),
    ] = False,
    voice: Annotated[
        str,
        typer.Option(
            "-v", "--voice", help="Voice to use for audio preview (default: af_sky)."
        ),
    ] = "af_sky",
    language: Annotated[
        str,
        typer.Option(
            "-l",
            "--language",
            help="Language code for audio preview (e.g., 'de', 'en-us', 'a' for auto, default: a).",
        ),
    ] = "a",
) -> None:
    "List all names in a phoneme dictionary for review.\n\nDisplays the contents of a phoneme dictionary in a readable table format,\nmaking it easy to review and identify names that need phoneme corrections.\n\nUse --play to interactively listen to each name pronunciation.\n\nExamples:\n\n    \n    # List names sorted by frequency\n    ttsforge list-names custom_phonemes.json\n\n    \n    # List names alphabetically\n    ttsforge list-names custom_phonemes.json --sort-by alpha\n\n    \n    # Interactive audio preview\n    ttsforge list-names custom_phonemes.json --play\n\n    \n    # Audio preview with different voice and language\n    ttsforge list-names custom_phonemes.json --play --voice af_bella --language de"
    from .commands_utility import list_names

    list_names(
        phoneme_dict=phoneme_dict,
        sort_by=sort_by,
        play=play,
        voice=voice,
        language=language,
    )


def register(app: typer.Typer) -> None:
    """Register utility commands without importing implementations."""
    app.command(name="voices")(voices_command)
    app.command(name="demo")(demo_command)
    app.command(name="download")(download_command)
    config_app = typer.Typer(
        cls=RepeatedPairGroup,
        add_completion=False,
        invoke_without_command=True,
        no_args_is_help=False,
        help="Manage ttsforge configuration.",
        rich_markup_mode="rich",
    )
    config_app.callback()(config_command)
    config_app.command(
        name="short-sentence",
        cls=ShortSentenceConfigCommand,
    )(short_sentence_config_command)
    app.add_typer(config_app, name="config")

    app.command(
        name="short-sentence-advanced-config",
        cls=ShortSentenceConfigCommand,
        hidden=True,
    )(legacy_short_sentence_advanced_config_command)
    app.command(name="extract-names")(extract_names_command)
    app.command(name="list-names")(list_names_command)
