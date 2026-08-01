"""Explicit, typed Typer wrappers for conversion commands."""

# The explicit command signatures intentionally retain long help and Literal
# declarations so the complete public contract stays visible in one module.
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

LanguageCode = Literal["a", "b", "d", "e", "f", "h", "i", "j", "p", "z"]
AudioFormat = Literal["wav", "mp3", "flac", "opus", "m4b"]
ConversionSplitMode = Literal["auto", "line", "paragraph", "sentence", "clause"]
ReadSplitMode = Literal["sentence", "paragraph"]


def convert_command(
    ctx: typer.Context,
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
            help="Output file path. Defaults to input filename with new extension.",
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
        Literal[
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
        | None,
        typer.Option("-v", "--voice", help="Voice to use for TTS."),
    ] = None,
    language: Annotated[
        LanguageCode | None,
        typer.Option(
            "-l",
            "--language",
            help="Language code (a=American English, b=British English, etc.).",
        ),
    ] = None,
    lang: Annotated[
        str | None,
        typer.Option(
            "--lang",
            help="Override language for phonemization (e.g., 'de', 'fr', 'en-us'). By default, language is determined from the voice.",
        ),
    ] = None,
    speed: Annotated[
        float | None,
        typer.Option(
            "-s", "--speed", help="Speech speed (0.5 to 2.0).", min=0.5, max=2.0
        ),
    ] = None,
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
    chapters: Annotated[
        str | None,
        typer.Option(
            "--chapters", help="Chapters to convert (e.g., '1-5', '1,3,5', 'all')."
        ),
    ] = None,
    skip_chapters: Annotated[
        str | None,
        typer.Option(
            "--skip-chapters", help="Chapters to skip (e.g., '5', '2,4,6', '10-12')."
        ),
    ] = None,
    silence: Annotated[
        float | None,
        typer.Option(
            "--silence", help="Silence duration between chapters in seconds.", min=0.0
        ),
    ] = None,
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
        typer.Option(
            "--pause-mode",
            help="Pause mode: 'tts', 'manual', or 'auto' (default: auto).",
        ),
    ] = None,
    disable_short_sentence: Annotated[
        bool,
        typer.Option(
            "--disable-short-sentence",
            help="Disable special handling for short sentences.",
        ),
    ] = False,
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
    title: Annotated[
        str | None, typer.Option("--title", help="Title metadata for the audiobook.")
    ] = None,
    author: Annotated[
        str | None, typer.Option("--author", help="Author metadata for the audiobook.")
    ] = None,
    cover: Annotated[
        Path | None,
        typer.Option(
            "--cover",
            help="Cover image for m4b format.",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    yes: Annotated[
        bool, typer.Option("-y", "--yes", help="Skip confirmation prompts.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show detailed output.")
    ] = False,
    split_mode: Annotated[
        ConversionSplitMode | None,
        typer.Option(
            "--split-mode",
            help="Text splitting mode: auto, line, paragraph, sentence, clause.",
        ),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume/--no-resume",
            help="Enable/disable resume capability (default: enabled).",
        ),
    ] = True,
    generate_ssmd_only: Annotated[
        bool,
        typer.Option(
            "--generate-ssmd",
            help="Generate only SSMD files without creating audio (for manual editing).",
        ),
    ] = False,
    detect_emphasis: Annotated[
        bool | None,
        typer.Option(
            "--detect-emphasis/--no-detect-emphasis",
            help="Detect EPUB italic/bold markup; omitted uses persistent configuration.",
        ),
    ] = None,
    prosody_method: Annotated[
        Literal[
            "phase_vocoder",
            "wsola",
            "esola",
            "td_psola",
            "psola",
        ]
        | None,
        typer.Option(
            "--prosody-method",
            help=(
                "Override the configured SSMD prosody algorithm. "
                "'psola' is an alias for AudioSig 'td_psola'."
            ),
        ),
    ] = None,
    prosody_strict: Annotated[
        bool | None,
        typer.Option(
            "--prosody-strict/--no-prosody-strict",
            help="Override whether SSMD prosody processing rejects fallback.",
        ),
    ] = None,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Discard any previous progress and start conversion from scratch.",
        ),
    ] = False,
    keep_chapter_files: Annotated[
        bool,
        typer.Option(
            "--keep-chapters",
            help="Keep individual chapter audio files after conversion.",
        ),
    ] = False,
    voice_blend: Annotated[
        str | None,
        typer.Option(
            "--voice-blend",
            help="Blend multiple voices (e.g., 'af_nicole:50,am_michael:50').",
        ),
    ] = None,
    voice_database: Annotated[
        Path | None,
        typer.Option(
            "--voice-db",
            help="Path to custom voice database (SQLite).",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    use_mixed_language: Annotated[
        bool | None,
        typer.Option(
            "--use-mixed-language/--no-use-mixed-language",
            help="Enable mixed-language support (auto-detect multiple languages in text).",
        ),
    ] = None,
    mixed_language_primary: Annotated[
        str | None,
        typer.Option(
            "--mixed-language-primary",
            help="Primary language for mixed-language mode (e.g., 'de', 'en-us').",
        ),
    ] = None,
    mixed_language_allowed: Annotated[
        str | None,
        typer.Option(
            "--mixed-language-allowed",
            help="Comma-separated list of allowed languages (e.g., 'de,en-us').",
        ),
    ] = None,
    mixed_language_confidence: Annotated[
        float | None,
        typer.Option(
            "--mixed-language-confidence",
            help="Detection confidence threshold for mixed-language mode (0.0-1.0, default: 0.7).",
            min=0.0,
            max=1.0,
        ),
    ] = None,
    phoneme_dictionary_path: Annotated[
        str | None,
        typer.Option(
            "--phoneme-dict",
            help="Path to custom phoneme dictionary JSON file for pronunciation overrides.",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    phoneme_dict_case_sensitive: Annotated[
        bool | None,
        typer.Option(
            "--phoneme-dict-case-sensitive/--no-phoneme-dict-case-sensitive",
            help="Make phoneme dictionary matching case-sensitive (default: case-insensitive).",
        ),
    ] = None,
    subchapter_markers: Annotated[
        list[str] | None,
        typer.Option(
            "--subchapter-marker",
            help="Exact line marker to convert into a paragraph pause. Repeat for multiple markers.",
        ),
    ] = None,
    ssmd_header: Annotated[
        bool | None,
        typer.Option(
            "--ssmd-header/--no-ssmd-header",
            help="Parse an exact leading --- block as SSMD front matter (default: enabled).",
        ),
    ] = None,
    ssmd_unknown_header: Annotated[
        Literal["warn", "error", "ignore"] | None,
        typer.Option(
            "--ssmd-unknown-header", help="Policy for unknown SSMD header keys."
        ),
    ] = None,
    ssmd_missing_voice: Annotated[
        Literal["error", "use-default"] | None,
        typer.Option(
            "--ssmd-missing-voice", help="Policy for unresolved logical voices."
        ),
    ] = None,
    ssmd_emphasis: Annotated[
        Literal["plain", "approximate", "warn", "error"] | None,
        typer.Option(
            "--ssmd-emphasis",
            help="SSMD emphasis policy (default: configured value, normally plain).",
        ),
    ] = None,
    enable_ssmd_emphasis: Annotated[
        bool,
        typer.Option(
            "--enable-ssmd-emphasis",
            help=(
                "Opt in to approximate SSMD emphasis with segment-level "
                "volume/rate changes. Use --detect-emphasis for EPUB HTML."
            ),
        ),
    ] = False,
    ssmd_profile_validation: Annotated[
        bool | None,
        typer.Option(
            "--ssmd-profile-validation/--no-ssmd-profile-validation",
            help="Validate Kokoro SSMD profile support.",
        ),
    ] = None,
    ssmd_fail_on_warning: Annotated[
        bool | None,
        typer.Option(
            "--ssmd-fail-on-warning/--no-ssmd-fail-on-warning",
            help="Promote SSMD warnings to errors.",
        ),
    ] = None,
    ssmd_voice: Annotated[
        list[str] | None,
        typer.Option(
            "--ssmd-voice",
            help="Bind a logical SSMD role: ROLE=KOKORO_VOICE. Repeatable.",
        ),
    ] = None,
    ssmd_pause_defaults: Annotated[
        bool | None,
        typer.Option(
            "--ssmd-pause-defaults/--no-ssmd-pause-defaults",
            help="Explicitly enable or disable SSMD pause defaults.",
        ),
    ] = None,
    pause_voice_change: Annotated[
        float | None,
        typer.Option(
            "--pause-voice-change",
            help="Explicit pause after logical voice changes, in seconds.",
            min=0.0,
        ),
    ] = None,
    ssmd_audio_root: Annotated[
        Path | None,
        typer.Option(
            "--ssmd-audio-root", help="Allowed root for local SSMD audio sources."
        ),
    ] = None,
    ssmd_remote_audio: Annotated[
        bool | None,
        typer.Option(
            "--ssmd-remote-audio/--no-ssmd-remote-audio",
            help="Allow bounded HTTPS SSMD audio sources.",
        ),
    ] = None,
    ssmd_audio_max_bytes: Annotated[
        int | None,
        typer.Option(
            "--ssmd-audio-max-bytes", help="Maximum SSMD audio source bytes.", min=1
        ),
    ] = None,
    ssmd_audio_max_duration: Annotated[
        float | None,
        typer.Option(
            "--ssmd-audio-max-duration",
            help="Maximum SSMD audio source duration in seconds.",
            min=0.0,
        ),
    ] = None,
    embed_ssmd_voice_bindings: Annotated[
        bool | None,
        typer.Option(
            "--embed-ssmd-voice-bindings/--no-embed-ssmd-voice-bindings",
            help="Embed explicit SSMD voice bindings in generated headers.",
        ),
    ] = None,
    embed_ssmd_pause_defaults: Annotated[
        bool | None,
        typer.Option(
            "--embed-ssmd-pause-defaults/--no-embed-ssmd-pause-defaults",
            help="Embed explicit SSMD pause defaults in generated headers.",
        ),
    ] = None,
) -> None:
    "Convert an EPUB file to an audiobook.\n\nEPUB_FILE is the path to the EPUB file to convert."
    from .commands_conversion import convert

    disable_short_sentence_value = False if disable_short_sentence else None
    convert(
        ctx=ctx,
        epub_file=epub_file,
        output=output,
        output_format=output_format,
        voice=voice,
        language=language,
        lang=lang,
        speed=speed,
        use_gpu=use_gpu,
        provider=provider,
        chapters=chapters,
        skip_chapters=skip_chapters,
        silence=silence,
        pause_clause=pause_clause,
        pause_sentence=pause_sentence,
        pause_paragraph=pause_paragraph,
        pause_variance=pause_variance,
        random_seed=random_seed,
        pause_mode=pause_mode,
        enable_short_sentence=disable_short_sentence_value,
        short_sentence=short_sentence,
        announce_chapters=announce_chapters,
        chapter_pause=chapter_pause,
        title=title,
        author=author,
        cover=cover,
        yes=yes,
        verbose=verbose,
        split_mode=split_mode,
        resume=resume,
        generate_ssmd_only=generate_ssmd_only,
        detect_emphasis=detect_emphasis,
        prosody_method=prosody_method,
        prosody_strict=prosody_strict,
        fresh=fresh,
        keep_chapter_files=keep_chapter_files,
        voice_blend=voice_blend,
        voice_database=voice_database,
        use_mixed_language=use_mixed_language,
        mixed_language_primary=mixed_language_primary,
        mixed_language_allowed=mixed_language_allowed,
        mixed_language_confidence=mixed_language_confidence,
        phoneme_dictionary_path=phoneme_dictionary_path,
        phoneme_dict_case_sensitive=phoneme_dict_case_sensitive,
        subchapter_markers=tuple(subchapter_markers or ()),
        ssmd_header=ssmd_header,
        ssmd_unknown_header=ssmd_unknown_header,
        ssmd_missing_voice=ssmd_missing_voice,
        ssmd_emphasis=ssmd_emphasis,
        enable_ssmd_emphasis=enable_ssmd_emphasis,
        ssmd_profile_validation=ssmd_profile_validation,
        ssmd_fail_on_warning=ssmd_fail_on_warning,
        ssmd_voice=ssmd_voice or [],
        ssmd_pause_defaults=ssmd_pause_defaults,
        pause_voice_change=pause_voice_change,
        ssmd_audio_root=ssmd_audio_root,
        ssmd_remote_audio=ssmd_remote_audio,
        ssmd_audio_max_bytes=ssmd_audio_max_bytes,
        ssmd_audio_max_duration=ssmd_audio_max_duration,
        embed_ssmd_voice_bindings=embed_ssmd_voice_bindings,
        embed_ssmd_pause_defaults=embed_ssmd_pause_defaults,
    )


def list_chapters_command(
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
) -> None:
    "List chapters in a file.\n\nEPUB_FILE is the path to the file (EPUB, TXT, or SSMD)."
    from .commands_conversion import list_chapters

    list_chapters(epub_file=epub_file)


def info_command(
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
) -> None:
    "Show metadata and information about a file.\n\nEPUB_FILE is the path to the file (EPUB, TXT, or SSMD)."
    from .commands_conversion import info

    info(epub_file=epub_file)


def sample_command(
    ctx: typer.Context,
    text: Annotated[str | None, typer.Argument()] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output file path (default: ./sample.wav).",
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    output_format: Annotated[
        AudioFormat, typer.Option("-f", "--format", help="Output audio format.")
    ] = "wav",
    voice: Annotated[
        str | None,
        typer.Option(
            "-v",
            "--voice",
            help="TTS voice to use or voice blend (e.g., 'af_sky' or 'af_nicole:50,am_michael:50').",
        ),
    ] = None,
    language: Annotated[
        LanguageCode | None, typer.Option("-l", "--language", help="Language for TTS.")
    ] = None,
    lang: Annotated[
        str | None,
        typer.Option(
            "--lang",
            help="Override language for phonemization (e.g., 'de', 'fr', 'en-us').",
        ),
    ] = None,
    speed: Annotated[
        float | None,
        typer.Option(
            "-s", "--speed", help="Speech speed (default: 1.0).", min=0.5, max=2.0
        ),
    ] = None,
    random_seed: Annotated[
        int | None,
        typer.Option(
            "--seed",
            help="Random seed for reproducible pause variance and randomized handling.",
        ),
    ] = None,
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
    split_mode: Annotated[
        ConversionSplitMode | None,
        typer.Option("--split-mode", help="Text splitting mode for processing."),
    ] = None,
    play_audio: Annotated[
        bool,
        typer.Option(
            "-p",
            "--play",
            help="Play audio directly (also saves to file if -o specified).",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show detailed output.")
    ] = False,
    use_mixed_language: Annotated[
        bool,
        typer.Option(
            "--use-mixed-language",
            help="Enable mixed-language support (auto-detect multiple languages in text).",
        ),
    ] = False,
    mixed_language_primary: Annotated[
        str | None,
        typer.Option(
            "--mixed-language-primary",
            help="Primary language for mixed-language mode (e.g., 'de', 'en-us').",
        ),
    ] = None,
    mixed_language_allowed: Annotated[
        str | None,
        typer.Option(
            "--mixed-language-allowed",
            help="Comma-separated list of allowed languages (e.g., 'de,en-us').",
        ),
    ] = None,
    mixed_language_confidence: Annotated[
        float | None,
        typer.Option(
            "--mixed-language-confidence",
            help="Detection confidence threshold for mixed-language mode (0.0-1.0, default: 0.7).",
            min=0.0,
            max=1.0,
        ),
    ] = None,
    phoneme_dictionary_path: Annotated[
        str | None,
        typer.Option(
            "--phoneme-dict",
            help="Path to custom phoneme dictionary JSON file for pronunciation overrides.",
            exists=True,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    phoneme_dict_case_sensitive: Annotated[
        bool,
        typer.Option(
            "--phoneme-dict-case-sensitive",
            help="Make phoneme dictionary matching case-sensitive (default: case-insensitive).",
        ),
    ] = False,
) -> None:
    'Generate a sample audio file to test TTS settings.\n\nIf no TEXT is provided, uses a default sample text.\n\nExamples:\n\n    ttsforge sample\n\n    ttsforge sample "Hello, this is a test."\n\n    ttsforge sample --voice am_adam --speed 1.2 -o test.wav\n\n    ttsforge sample --play  # Play directly without saving\n\n    ttsforge sample --play -o test.wav  # Play and save to file'
    from .commands_conversion import sample

    sample(
        ctx=ctx,
        text=text,
        output=output,
        output_format=output_format,
        voice=voice,
        language=language,
        lang=lang,
        speed=speed,
        random_seed=random_seed,
        use_gpu=use_gpu,
        provider=provider,
        split_mode=split_mode,
        play_audio=play_audio,
        verbose=verbose,
        use_mixed_language=use_mixed_language,
        mixed_language_primary=mixed_language_primary,
        mixed_language_allowed=mixed_language_allowed,
        mixed_language_confidence=mixed_language_confidence,
        phoneme_dictionary_path=phoneme_dictionary_path,
        phoneme_dict_case_sensitive=phoneme_dict_case_sensitive,
    )


def read_command(
    ctx: typer.Context,
    input_file: Annotated[
        Path | None,
        typer.Argument(
            exists=False,
            file_okay=True,
            dir_okay=True,
            readable=True,
            writable=False,
            resolve_path=False,
        ),
    ] = None,
    voice: Annotated[
        Literal[
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
        | None,
        typer.Option("-v", "--voice", help="TTS voice to use."),
    ] = None,
    language: Annotated[
        LanguageCode | None, typer.Option("-l", "--language", help="Language for TTS.")
    ] = None,
    speed: Annotated[
        float | None, typer.Option("-s", "--speed", help="Speech speed (default: 1.0).")
    ] = None,
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
    content_mode: Annotated[
        Literal["chapters", "pages"] | None,
        typer.Option(
            "--mode", help="Split content by chapters or pages (default: chapters)."
        ),
    ] = None,
    chapters: Annotated[
        str | None,
        typer.Option(
            "-c",
            "--chapters",
            help="Chapter selection (e.g., '1-5', '1,3,5', '3-'). Use with --mode chapters.",
        ),
    ] = None,
    pages: Annotated[
        str | None,
        typer.Option(
            "-p",
            "--pages",
            help="Page selection (e.g., '1-50', '10,20,30'). Use with --mode pages.",
        ),
    ] = None,
    start_chapter: Annotated[
        int | None,
        typer.Option(
            "--start-chapter", help="Start from specific chapter number (1-indexed)."
        ),
    ] = None,
    start_page: Annotated[
        int | None,
        typer.Option(
            "--start-page", help="Start from specific page number (1-indexed)."
        ),
    ] = None,
    page_size: Annotated[
        int | None,
        typer.Option(
            "--page-size",
            help="Synthetic page size in characters (default: 2000). Only for --mode pages.",
            min=1,
        ),
    ] = None,
    resume: Annotated[
        bool, typer.Option("--resume", help="Resume from last saved position.")
    ] = False,
    list_content: Annotated[
        bool,
        typer.Option("--list", help="List chapters/pages and exit without reading."),
    ] = False,
    split_mode: Annotated[
        ReadSplitMode | None,
        typer.Option(
            "--split",
            help="Text splitting mode: sentence (shorter) or paragraph (grouped).",
        ),
    ] = None,
    pause_clause: Annotated[
        float | None,
        typer.Option("--pause-clause", help="Pause after clauses in seconds.", min=0.0),
    ] = None,
    pause_sentence: Annotated[
        float | None,
        typer.Option(
            "--pause-sentence", help="Pause after sentences in seconds.", min=0.0
        ),
    ] = None,
    pause_paragraph: Annotated[
        float | None,
        typer.Option(
            "--pause-paragraph", help="Pause after paragraphs in seconds.", min=0.0
        ),
    ] = None,
    pause_variance: Annotated[
        float | None,
        typer.Option(
            "--pause-variance",
            help="Random variance added to pauses in seconds.",
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
        typer.Option("--pause-mode", help="Trim leading/trailing silence from audio."),
    ] = None,
    disable_short_sentence: Annotated[
        bool,
        typer.Option(
            "--disable-short-sentence",
            help="Disable special handling for short sentences.",
        ),
    ] = False,
    short_sentence: Annotated[
        str | None,
        typer.Option(
            "--short-sentence",
            help="Short-sentence handling config, e.g. 'mode=randomized,threshold=30,selection=auto,max-tries=5' or 'config=path/to/short_sentence.json'.",
        ),
    ] = None,
) -> None:
    'Read an EPUB or text file aloud with streaming playback.\n\nStreams audio in real-time without creating output files.\nSupports chapter/page selection, position saving, and resume.\n\n\nExamples:\n    ttsforge read book.epub\n    ttsforge read book.epub --chapters "1-5"\n    ttsforge read book.epub --mode pages --pages "1-50"\n    ttsforge read book.epub --mode pages --start-page 10\n    ttsforge read book.epub --start-chapter 3\n    ttsforge read book.epub --resume\n    ttsforge read book.epub --split sentence\n    ttsforge read book.epub --list\n    ttsforge read story.txt\n    cat story.txt | ttsforge read -\n\n\nControls:\n    Ctrl+C - Stop reading (position is saved for resume)'
    from .commands_conversion import read

    disable_short_sentence_value = False if disable_short_sentence else None
    read(
        ctx=ctx,
        input_file=input_file,
        voice=voice,
        language=language,
        speed=speed,
        use_gpu=use_gpu,
        provider=provider,
        content_mode=content_mode,
        chapters=chapters,
        pages=pages,
        start_chapter=start_chapter,
        start_page=start_page,
        page_size=page_size,
        resume=resume,
        list_content=list_content,
        split_mode=split_mode,
        pause_clause=pause_clause,
        pause_sentence=pause_sentence,
        pause_paragraph=pause_paragraph,
        pause_variance=pause_variance,
        random_seed=random_seed,
        pause_mode=pause_mode,
        enable_short_sentence=disable_short_sentence_value,
        short_sentence=short_sentence,
    )


def register(app: typer.Typer) -> None:
    """Register conversion commands without importing implementations."""
    app.command(name="convert")(convert_command)
    app.command(name="list")(list_chapters_command)
    app.command(name="info")(info_command)
    app.command(name="sample")(sample_command)
    app.command(name="read")(read_command)
