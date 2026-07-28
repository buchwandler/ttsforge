"""Explicit, typed Typer wrappers for phoneme commands."""

# The explicit command signatures intentionally retain long help declarations.
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

LanguageCode = Literal["a", "b", "d", "e", "f", "h", "i", "j", "p", "z"]
AudioFormat = Literal["wav", "mp3", "flac", "opus", "m4b"]
ExportSplitMode = Literal["paragraph", "sentence", "clause"]
VoiceName = Literal[
    "af",
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
    "ef_dora",
    "em_alex",
    "em_santa",
    "ff_siwis",
    "hf_alpha",
    "hf_beta",
    "hm_omega",
    "hm_psi",
    "if_sara",
    "im_nicola",
    "jf_alpha",
    "jf_gongitsune",
    "jf_nezumi",
    "jf_tebukuro",
    "jm_kumo",
    "pf_dora",
    "pm_alex",
    "pm_santa",
    "zf_xiaobei",
    "zf_xiaoni",
    "zf_xiaoxiao",
    "zm_yunjian",
    "zm_yunxi",
    "zm_yunxia",
    "zm_yunyang",
]


def phonemes_export_command(
    epub_file: Annotated[
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
            help="Output file path. Defaults to input filename with .phonemes.json extension.",
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    readable: Annotated[
        bool,
        typer.Option(
            "--readable", help="Export as human-readable text format instead of JSON."
        ),
    ] = False,
    language: Annotated[
        LanguageCode,
        typer.Option("-l", "--language", help="Language code for phonemization."),
    ] = "a",
    chapters: Annotated[
        str | None,
        typer.Option(
            "--chapters", help="Chapters to export (e.g., '1-5', '1,3,5', 'all')."
        ),
    ] = None,
    vocab_version: Annotated[
        str,
        typer.Option(
            "--vocab-version", help="Vocabulary version to use for tokenization."
        ),
    ] = "v1.0",
    split_mode: Annotated[
        ExportSplitMode,
        typer.Option(
            "--split-mode",
            help="Split mode: paragraph (newlines), sentence (spaCy), clause (+ commas).",
        ),
    ] = "sentence",
    max_chars: Annotated[
        int,
        typer.Option(
            "--max-chars",
            help="Maximum characters per segment (for additional splitting of long segments).",
        ),
    ] = 300,
    subchapter_markers: Annotated[
        list[str] | None,
        typer.Option(
            "--subchapter-marker",
            help="Exact line marker to convert into a paragraph pause. Repeat for multiple markers.",
        ),
    ] = None,
) -> None:
    "Export an EPUB as pre-tokenized phoneme data.\n\nThis creates a JSON file containing the book's text converted to\nphonemes and tokens, which can be later converted to audio without\nre-running the phonemization step.\n\nSplit modes:\n- paragraph: Split only on double newlines (fewer, longer segments)\n- sentence: Split on sentence boundaries using spaCy (recommended)\n- clause: Split on sentences + commas (more, shorter segments)\n\nExamples:\n\n    ttsforge phonemes export book.epub\n\n    ttsforge phonemes export book.epub --readable -o book.readable.txt\n\n    ttsforge phonemes export book.epub --language b --chapters 1-5\n\n    ttsforge phonemes export book.epub --split-mode clause"
    from .commands_phonemes import phonemes_export

    phonemes_export(
        epub_file=epub_file,
        output=output,
        readable=readable,
        language=language,
        chapters=chapters,
        vocab_version=vocab_version,
        split_mode=split_mode,
        max_chars=max_chars,
        subchapter_markers=tuple(subchapter_markers or ()),
    )


def phonemes_convert_command(
    ctx: typer.Context,
    phoneme_file: Annotated[
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
            help="Output file path. Defaults to input filename with audio extension.",
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    output_format: Annotated[
        AudioFormat | None, typer.Option("-f", "--format", help="Output audio format.")
    ] = None,
    voice: Annotated[
        VoiceName | None, typer.Option("-v", "--voice", help="Voice to use for TTS.")
    ] = None,
    speed: Annotated[
        float, typer.Option("-s", "--speed", help="Speech speed.", min=0.5, max=2.0)
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
        typer.Option("--silence", help="Silence between chapters in seconds.", min=0.0),
    ] = 2.0,
    pause_clause: Annotated[
        float | None,
        typer.Option(
            "--pause-clause",
            help="Pause after clauses in seconds (default: 0.25).",
            min=0.0,
        ),
    ] = None,
    pause_sentence: Annotated[
        float | None,
        typer.Option(
            "--pause-sentence",
            help="Pause after sentences in seconds (default: 0.2).",
            min=0.0,
        ),
    ] = None,
    pause_paragraph: Annotated[
        float | None,
        typer.Option(
            "--pause-paragraph",
            help="Pause after paragraphs in seconds (default: 0.75).",
            min=0.0,
        ),
    ] = None,
    pause_variance: Annotated[
        float | None,
        typer.Option(
            "--pause-variance",
            help="Random variance added to pauses in seconds (default: 0.05).",
            min=0.0,
        ),
    ] = None,
    random_seed: Annotated[
        int | None,
        typer.Option(
            "--seed",
            help="Random seed for reproducible pause variance and randomized handling.",
        ),
    ] = None,
    pause_mode: Annotated[
        str | None,
        typer.Option("--pause-mode", help="auto, manual or tts (default: auto)."),
    ] = None,
    short_sentence: Annotated[
        str | None,
        typer.Option(
            "--short-sentence",
            help="Short-sentence handling config, e.g. 'mode=randomized,threshold=30,selection=auto,max-tries=5' or 'config=path/to/short_sentence.json'.",
        ),
    ] = None,
    announce_chapters: Annotated[
        bool | None,
        typer.Option(
            "--announce-chapters/--no-announce-chapters",
            help="Read chapter titles aloud before chapter content (default: enabled).",
        ),
    ] = None,
    chapter_pause: Annotated[
        float | None,
        typer.Option(
            "--chapter-pause",
            help="Pause duration after chapter title announcement in seconds (default: 2.0).",
            min=0.0,
        ),
    ] = None,
    chapters: Annotated[
        str | None,
        typer.Option(
            "--chapters",
            help="Select chapters to convert (1-based). E.g., '1-5', '3,5,7', or '1-3,7'.",
        ),
    ] = None,
    title: Annotated[
        str | None, typer.Option("--title", help="Audiobook title (for m4b metadata).")
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", help="Audiobook author (for m4b metadata)."),
    ] = None,
    cover: Annotated[
        Path | None,
        typer.Option(
            "--cover",
            help="Cover image path (for m4b format).",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    voice_blend: Annotated[
        str | None,
        typer.Option(
            "--voice-blend",
            help="Blend multiple voices. E.g., 'af_nicole:50,am_michael:50'.",
        ),
    ] = None,
    voice_database: Annotated[
        Path | None,
        typer.Option(
            "--voice-database",
            help="Path to custom voice database (SQLite).",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    streaming: Annotated[
        bool,
        typer.Option(
            "--streaming/--no-streaming",
            help="Use streaming mode (faster, no resume). Default: resumable.",
        ),
    ] = False,
    keep_chapters: Annotated[
        bool,
        typer.Option(
            "--keep-chapters", help="Keep intermediate chapter files after merging."
        ),
    ] = False,
    yes: Annotated[
        bool, typer.Option("-y", "--yes", help="Skip confirmation prompts.")
    ] = False,
) -> None:
    "Convert a pre-tokenized phoneme file to audio.\n\nPHONEME_FILE should be a JSON file created by 'ttsforge phonemes export'.\n\nBy default, conversion is resumable (chapter-at-a-time mode). If interrupted,\nre-running the same command will resume from the last completed chapter.\n\nUse --streaming for faster conversion without resume capability.\n\nExamples:\n\n    ttsforge phonemes convert book.phonemes.json\n\n    ttsforge phonemes convert book.phonemes.json -v am_adam -o book.m4b\n\n    ttsforge phonemes convert book.phonemes.json --chapters 1-5\n\n    ttsforge phonemes convert book.phonemes.json --streaming"
    from .commands_phonemes import phonemes_convert

    phonemes_convert(
        ctx=ctx,
        phoneme_file=phoneme_file,
        output=output,
        output_format=output_format,
        voice=voice,
        speed=speed,
        use_gpu=use_gpu,
        provider=provider,
        silence=silence,
        pause_clause=pause_clause,
        pause_sentence=pause_sentence,
        pause_paragraph=pause_paragraph,
        pause_variance=pause_variance,
        random_seed=random_seed,
        pause_mode=pause_mode,
        short_sentence=short_sentence,
        announce_chapters=announce_chapters,
        chapter_pause=chapter_pause,
        chapters=chapters,
        title=title,
        author=author,
        cover=cover,
        voice_blend=voice_blend,
        voice_database=voice_database,
        streaming=streaming,
        keep_chapters=keep_chapters,
        yes=yes,
    )


def phonemes_preview_command(
    text: Annotated[str, typer.Argument()],
    language: Annotated[
        str,
        typer.Option(
            "-l",
            "--language",
            help="Language code for phonemization (e.g., 'de', 'en-us', 'a' for auto).",
        ),
    ] = "a",
    tokens: Annotated[
        bool, typer.Option("--tokens", help="Show token IDs in addition to phonemes.")
    ] = False,
    vocab_version: Annotated[
        str, typer.Option("--vocab-version", help="Vocabulary version to use.")
    ] = "v1.0",
    play: Annotated[
        bool, typer.Option("-p", "--play", help="Play audio preview of the text.")
    ] = False,
    voice: Annotated[
        str,
        typer.Option(
            "-v",
            "--voice",
            help="Voice to use for audio preview, or voice blend (e.g., 'af_nicole:50,am_michael:50').",
        ),
    ] = "af_sky",
    phoneme_dict: Annotated[
        Path | None,
        typer.Option(
            "--phoneme-dict",
            help="Path to custom phoneme dictionary file.",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
) -> None:
    'Preview phonemes for given text.\n\nShows how text will be converted to phonemes and optionally tokens.\nUse --play to hear the audio output.\n\nExamples:\n\n    ttsforge phonemes preview "Hello world"\n\n    ttsforge phonemes preview "Hello world" --tokens\n\n    ttsforge phonemes preview "Hello world" --language de\n\n    ttsforge phonemes preview "König" --language de --play\n\n    ttsforge phonemes preview "Hermione" --play --phoneme-dict custom.json\n\n    ttsforge phonemes preview "Hello" --play --voice "af_nicole:50,am_michael:50"'
    from .commands_phonemes import phonemes_preview

    phonemes_preview(
        text=text,
        language=language,
        tokens=tokens,
        vocab_version=vocab_version,
        play=play,
        voice=voice,
        phoneme_dict=phoneme_dict,
    )


def phonemes_info_command(
    phoneme_file: Annotated[
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
    stats: Annotated[
        bool, typer.Option("--stats", help="Show detailed token statistics.")
    ] = False,
) -> None:
    "Show information about a phoneme file.\n\nPHONEME_FILE should be a JSON file created by 'ttsforge phonemes export'.\n\nUse --stats to show detailed token statistics (min, median, mean, max)."
    from .commands_phonemes import phonemes_info

    phonemes_info(phoneme_file=phoneme_file, stats=stats)


def register(app: typer.Typer) -> None:
    """Register phoneme commands without importing implementations."""
    app.command(name="export")(phonemes_export_command)
    app.command(name="convert")(phonemes_convert_command)
    app.command(name="preview")(phonemes_preview_command)
    app.command(name="info")(phonemes_info_command)
