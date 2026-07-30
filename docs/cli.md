# CLI Reference

Complete command-line interface reference for ttsforge.

The command tree is declared with explicit typed Typer wrappers. CLI startup,
help, and version output remain independent of the ONNX provider. The legacy
`--set KEY VALUE` configuration grammar accepts repeated pairs, including
values that begin with `-`.


## Global Options

```bash
ttsforge --version    # Show version and exit
ttsforge --help       # Show help message
```


## convert

Convert an EPUB file to an audiobook.

```bash
ttsforge convert EPUB_FILE [OPTIONS]
```

### Arguments

`EPUB_FILE`
: Path to the EPUB file to convert (required).

### Options

`-o, --output PATH`
: Output file path. Defaults to input filename with new extension in the same directory.

`-f, --format FORMAT`
: Output audio format. Choices: `wav`, `mp3`, `flac`, `opus`, `m4b`.
  Default: `m4b`.

`-v, --voice VOICE`
: Voice to use for TTS. Can be a single voice name or a voice blend.

  - Single voice: `af_heart`, `am_adam`, etc.
  - Voice blend: `af_nicole:50,am_michael:50` (auto-detects blend format)

  See {doc}`voices` for available voices.
  Default: `af_heart`.

`-l, --language LANG`
: Language code for TTS. Choices: `a` (American English), `b` (British English),
  `e` (Spanish), `f` (French), `h` (Hindi), `i` (Italian), `j` (Japanese),
  `p` (Brazilian Portuguese), `z` (Mandarin Chinese).
  Default: auto-detected from EPUB metadata.

`--lang LANG`
: Override language for phonemization (e.g., `de`, `fr`, `en-us`).
  By default, language is determined from the voice.

`-s, --speed FLOAT`
: Speech speed multiplier (0.5 to 2.0). Default: `1.0`.

`--gpu / --no-gpu`
: Compatibility shortcut: `--gpu` maps to provider `auto` and `--no-gpu`
  maps to provider `cpu`.

`--provider PROVIDER`
: ONNX Runtime execution provider or alias (`auto`, `cpu`, `nnapi`,
  `xnnpack`, or a full `*ExecutionProvider` name). Available on
  `convert`, `sample`, `read`, `demo`, and `phonemes convert`.

`--chapters SELECTION`
: Chapters to convert. Examples: `1-5`, `1,3,5`, `1-3,5,7-10`, `all`.
  Default: all chapters (interactive selection if not specified).

`--silence FLOAT`
: Silence duration between chapters in seconds. Default: `2.0`.

`--pause-clause FLOAT`
: Pause after clauses in seconds. Default: `0.5`.

`--pause-sentence FLOAT`
: Pause after sentences in seconds. Default: `0.7`.

`--pause-paragraph FLOAT`
: Pause after paragraphs in seconds. Default: `0.9`.

`--pause-variance FLOAT`
: Random variance added to pauses in seconds. Default: `0.05`.

`--pause-mode MODE`
: Pause mode: `tts`, `manual`, or `auto`. Default: `auto`.

`--disable-short-sentence`
: Disable special handling for short sentences.

`--short-sentence TEXT`
: Short-sentence handling config. Example:
  `mode=randomized,threshold=30,selection=auto,max-tries=3`.
  Can also reference a JSON config with `config=path/to/short_sentence.json`. See `ttsforge config short-sentence init`.

`--announce-chapters / --no-announce-chapters`
: Read chapter titles aloud before chapter content. Default: enabled.

`--chapter-pause FLOAT`
: Pause after chapter title announcement in seconds. Default: `2.0`.

`--title TEXT`
: Title metadata for the audiobook. Defaults to EPUB title.

`--author TEXT`
: Author metadata for the audiobook. Defaults to EPUB author.

`--cover PATH`
: Cover image for M4B format.

### SSMD 0.8 options

`--ssmd-header / --no-ssmd-header`
: Parse or preserve an exact leading front-matter block.

`--ssmd-unknown-header POLICY`
: `warn`, `error`, or `ignore` unknown header keys.

`--ssmd-missing-voice POLICY`
: `error` or `use-default` for unresolved logical roles.

`--ssmd-emphasis MODE`
: `plain`, `approximate`, `warn`, or `error`. The default is the
  persisted `ssmd_emphasis_mode` value, normally `plain`. Plain speaks
  emphasis unchanged; approximate applies segment-level volume/rate changes.

`--enable-ssmd-emphasis`
: Convenience opt-in equivalent to `--ssmd-emphasis approximate`. It applies
  segment-level volume/rate changes to existing SSMD emphasis. Use
  `--detect-emphasis` separately when EPUB italic/bold styling should first
  be extracted into SSMD annotations. This flag cannot be combined with
  `--ssmd-emphasis`.

`--ssmd-voice ROLE=VOICE`
: Repeatable explicit Kokoro binding override.

`--ssmd-pause-defaults / --no-ssmd-pause-defaults` and `--pause-voice-change FLOAT`
: Explicit pause-default enablement and voice-change timing. Explicit pause
  values override document defaults; persistent config values do not.

`--ssmd-audio-root PATH`, `--ssmd-remote-audio`, `--ssmd-audio-max-bytes INTEGER`, `--ssmd-audio-max-duration FLOAT`
: Secure bounded audio source policy. Remote sources require explicit opt-in.

### SSMD inspection

These commands do not initialize ONNX:

```bash
ttsforge ssmd validate FILE
ttsforge ssmd validate FILE --strict
ttsforge ssmd inspect FILE --json
```

`-y, --yes`
: Skip confirmation prompts.

`--verbose`
: Show detailed output during conversion.

`--split-mode MODE`
: Text splitting mode. Choices: `auto`, `line`, `paragraph`, `sentence`, `clause`.
  Default: `auto`.

`--resume / --no-resume`
: Enable or disable resume capability. Default: enabled.

`--fresh`
: Discard any previous progress and start conversion from scratch.

`--generate-ssmd`
: Generate only SSMD files without creating audio (for manual editing).

`--detect-emphasis / --no-detect-emphasis`
: Detect emphasis (italic/bold) from EPUB HTML. Default: disabled.

`--keep-chapters`
: Keep individual chapter audio files after conversion.

`--voice-blend SPEC`
: Blend multiple voices (traditional method). Format: `voice1:weight1,voice2:weight2`.
  Example: `af_nicole:50,am_michael:50`.

  **Note:** You can also specify blends directly in the `--voice` parameter,
  which will auto-detect the blend format. Both methods work identically.

`--voice-db PATH`
: Path to custom voice database (SQLite).

`--phoneme-dict PATH`
: Path to custom phoneme dictionary JSON file for pronunciation overrides.

`--phoneme-dict-case-sensitive`
: Make phoneme dictionary matching case-sensitive (default: case-insensitive).

`--use-mixed-language`
: Enable mixed-language support (auto-detect multiple languages in text).

`--mixed-language-primary LANG`
: Primary language for mixed-language mode (e.g., `de`, `en-us`).
  This language is used as the fallback when detection is uncertain.

`--mixed-language-allowed LANGS`
: Comma-separated list of allowed languages for detection (e.g., `de,en-us`).
  Required when `--use-mixed-language` is enabled.

`--mixed-language-confidence FLOAT`
: Detection confidence threshold for mixed-language mode (0.0-1.0).
  Default: `0.7`. Higher values require more confidence for language switches.

### Examples

```bash
# Basic conversion
ttsforge convert book.epub

# Convert with specific voice and speed
ttsforge convert book.epub -v am_adam -s 1.1

# Convert chapters 1-5 to MP3
ttsforge convert book.epub --chapters 1-5 -f mp3

# Full options
ttsforge convert book.epub \
    --voice af_sarah \
    --speed 1.1 \
    --format m4b \
    --title "My Audiobook" \
    --author "Author Name" \
    --cover cover.jpg \
    --output ./audiobooks/mybook.m4b \
    --yes

# Resume interrupted conversion
ttsforge convert book.epub

# Start fresh (discard progress)
ttsforge convert book.epub --fresh

# Mixed-language conversion (German with English terms)
ttsforge convert book.epub \
    --use-mixed-language \
    --mixed-language-primary de \
    --mixed-language-allowed de,en-us
```


## list

List chapters in an EPUB file.

```bash
ttsforge list EPUB_FILE
```

### Arguments

`EPUB_FILE`
: Path to the EPUB file (required).

### Example

```bash
ttsforge list book.epub
```

Output shows chapter numbers, titles, and character counts.


## info

Show metadata and information about an EPUB file.

```bash
ttsforge info EPUB_FILE
```

### Arguments

`EPUB_FILE`
: Path to the EPUB file (required).

### Example

```bash
ttsforge info book.epub
```

Shows title, author, language, publisher, year, chapter count, and file size.


## sample

Generate a sample audio file to test TTS settings.

```bash
ttsforge sample [TEXT] [OPTIONS]
```

### Arguments

`TEXT`
: Text to convert. If not provided, uses default sample text.

### Options

`-o, --output PATH`
: Output file path. Default: `./sample.wav`.

`-f, --format FORMAT`
: Output audio format. Default: `wav`.

`-v, --voice VOICE`
: TTS voice to use. Can be a single voice or voice blend.

  - Single voice: `af_heart`
  - Voice blend: `af_nicole:50,am_michael:50` (auto-detects blend format)

`-l, --language LANG`
: Language for TTS.

`--lang LANG`
: Override language for phonemization (e.g., `de`, `fr`, `en-us`).

`-s, --speed FLOAT`
: Speech speed. Default: `1.0`.

`--gpu / --no-gpu`
: Compatibility shortcut mapping to `auto` or `cpu`.

`--provider PROVIDER`
: ONNX Runtime execution provider or alias.

`--split-mode MODE`
: Text splitting mode.

`--verbose`
: Show detailed output.

`-p, --play`
: Play audio directly (also saves to file if `-o` specified).

  **Note:** Playback requires the optional `ttsforge[audio]` extra.

`--use-mixed-language`
: Enable mixed-language support (auto-detect multiple languages in text).

`--mixed-language-primary LANG`
: Primary language for mixed-language mode (e.g., `de`, `en-us`).

`--mixed-language-allowed LANGS`
: Comma-separated list of allowed languages (e.g., `de,en-us`).

`--mixed-language-confidence FLOAT`
: Detection confidence threshold (0.0-1.0). Default: `0.7`.

`--phoneme-dict PATH`
: Path to custom phoneme dictionary JSON file for pronunciation overrides.

`--phoneme-dict-case-sensitive`
: Make phoneme dictionary matching case-sensitive (default: case-insensitive).

### Examples

```bash
# Default sample
ttsforge sample

# Custom text
ttsforge sample "Hello, this is a test."

# With voice and output options
ttsforge sample "Testing voice" --voice am_adam -o test.wav

# Mixed-language sample
ttsforge sample \
   "Das ist ein Test. This is a test." \
   --use-mixed-language \
   --mixed-language-primary de \
   --mixed-language-allowed de,en-us
```


## read

Stream playback from an EPUB or text file (no output files).

```bash
ttsforge read [INPUT_FILE] [OPTIONS]
```

### Arguments

`INPUT_FILE`
: Path to EPUB/TXT file, or `-` to read from stdin. If omitted, reads stdin.

### Options

`-v, --voice VOICE`
: TTS voice to use.

`-l, --language LANG`
: Language for TTS.

`-s, --speed FLOAT`
: Speech speed. Default: `1.0`.

`--gpu / --no-gpu`
: Compatibility shortcut mapping to `auto` or `cpu`.

`--provider PROVIDER`
: ONNX Runtime execution provider or alias.

`--mode MODE`
: Content mode: `chapters` or `pages`.

`-c, --chapters SELECTION`
: Chapter selection for `chapters` mode.

`-p, --pages SELECTION`
: Page selection for `pages` mode.

`--start-chapter INT`
: Start from specific chapter number (1-indexed).

`--start-page INT`
: Start from specific page number (1-indexed).

`--page-size INT`
: Synthetic page size in characters (default: 2000).

`--resume`
: Resume from last saved position.

`--list`
: List chapters/pages and exit without reading.

`--split MODE`
: Text splitting mode: `sentence` or `paragraph`.

`--pause-clause FLOAT`
: Pause after clauses in seconds.

`--pause-sentence FLOAT`
: Pause after sentences in seconds.

`--pause-paragraph FLOAT`
: Pause after paragraphs in seconds.

`--pause-variance FLOAT`
: Random variance added to pauses in seconds.

`--pause-mode MODE`
: Pause mode: `tts`, `manual`, or `auto`.

`--disable-short-sentence`
: Disable special handling for short sentences.

`--short-sentence TEXT`
: Short-sentence handling config. Example:
  `mode=randomized,threshold=30,selection=auto,max-tries=3`.
  Can also reference a JSON config with `config=path/to/short_sentence.json`. See `ttsforge config short-sentence init`.

**Note:** Playback requires the optional `ttsforge[audio]` extra.

### Examples

```bash
# Read an EPUB aloud
ttsforge read book.epub

# Read pages 1-10
ttsforge read book.epub --mode pages --pages 1-10

# Resume from last position
ttsforge read book.epub --resume
```


## voices

List available TTS voices.

```bash
ttsforge voices [OPTIONS]
```

### Options

`-l, --language LANG`
: Filter voices by language code.

### Examples

```bash
# List all voices
ttsforge voices

# List American English voices
ttsforge voices -l a

# List British English voices
ttsforge voices -l b
```


## demo

Generate a demo audio file with voice samples.

```bash
ttsforge demo [OPTIONS]
```

### Options

`-o, --output PATH`
: Output file path. Default: `./voices_demo.wav` (or directory with `--separate`).

`-l, --language LANG`
: Filter voices by language.

`-v, --voice VOICES`
: Specific voices to include (comma-separated).
  Example: `af_heart,am_adam`.

`-s, --speed FLOAT`
: Speech speed. Default: `1.0`.

`--gpu / --no-gpu`
: Enable or disable GPU acceleration.

`--silence FLOAT`
: Silence between voice samples in seconds. Default: `0.5`.

`--text TEXT`
: Custom text to use. Use `{voice}` placeholder for voice name.

`--separate`
: Save each voice as a separate file instead of concatenating.

`--blend SPEC`
: Voice blend to demo (e.g., `af_nicole:50,am_michael:50`).

`--blend-presets`
: Demo a curated set of voice blend combinations.

`-p, --play`
: Play audio directly instead of only saving files.

  **Note:** Playback requires the optional `ttsforge[audio]` extra.

### Examples

```bash
# Demo all voices
ttsforge demo

# Demo American English voices only
ttsforge demo -l a

# Demo specific voices
ttsforge demo -v af_heart,am_adam,bf_emma

# Save separate files
ttsforge demo --separate -o ./voice_samples/

# Custom demo text
ttsforge demo --text "Hi, I'm {voice}. Nice to meet you!"
```


## download

Download ONNX model files required for TTS.

```bash
ttsforge download [OPTIONS]
```

### Options

`--force`
: Force re-download even if files exist.

### Examples

```bash
# Download models
ttsforge download

# Force re-download
ttsforge download --force
```


## config

Manage ttsforge configuration.

```bash
ttsforge config [OPTIONS]
```

Configuration is stored in `~/.config/ttsforge/config.json`.

### Options

`--show`
: Show current configuration.

`--reset`
: Reset configuration to defaults.

`--set KEY VALUE`
: Set a configuration option. Can be used multiple times.

### Examples

```bash
# Show configuration
ttsforge config --show

# Set default voice
ttsforge config --set default_voice am_adam

# Set multiple options
ttsforge config --set default_voice af_sarah --set default_speed 1.1

# Select the default ONNX provider
ttsforge config --set onnx_provider nnapi

# Legacy compatibility shortcut
ttsforge config --set use_gpu true

# Reset to defaults
ttsforge config --reset
```

See {doc}`configuration` for all available options.


## config short-sentence

Create, link, or inspect the advanced short-sentence JSON configuration.

```bash
ttsforge config short-sentence [show|init|reset]
```

Called without an action, this command prints its help.

### Arguments

`show`
: Show the advanced JSON config.

`init`
: Write the advanced JSON config and update the ttsforge config to use it.

`reset`
: Recreate the advanced JSON config from defaults and update the ttsforge config
  to use it.

### Examples

```bash
# Create and link the advanced short-sentence config
ttsforge config short-sentence init

# Show the advanced short-sentence config
ttsforge config short-sentence show

# Reset the advanced short-sentence config to defaults
ttsforge config short-sentence reset
```

The former `short-sentence-advanced-config` root command remains available
as a deprecated compatibility alias.


## phonemes

Commands for working with phonemes and pre-tokenized content.

### phonemes export

Export an EPUB as pre-tokenized phoneme data.

```bash
ttsforge phonemes export EPUB_FILE [OPTIONS]
```

#### Arguments

`EPUB_FILE`
: Path to the EPUB file (required).

#### Options

`-o, --output PATH`
: Output file path. Default: input filename with `.phonemes.json`.

`--readable`
: Export as human-readable text format instead of JSON.

`-l, --language LANG`
: Language code for phonemization. Default: `a`.

`--chapters SELECTION`
: Chapters to export.

`--vocab-version VERSION`
: Vocabulary version. Default: `v1.0`.

`--split-mode MODE`
: Split mode: `paragraph`, `sentence`, or `clause`. Default: `sentence`.

`--max-chars INT`
: Maximum characters per segment. Default: `300`.

#### Examples

```bash
# Export to phonemes
ttsforge phonemes export book.epub

# Export as readable format
ttsforge phonemes export book.epub --readable -o book.readable.txt

# Export specific chapters
ttsforge phonemes export book.epub --chapters 1-5

# Use clause splitting for shorter segments
ttsforge phonemes export book.epub --split-mode clause
```

### phonemes convert

Convert a pre-tokenized phoneme file to audio.

```bash
ttsforge phonemes convert PHONEME_FILE [OPTIONS]
```

#### Arguments

`PHONEME_FILE`
: Path to the phoneme JSON file (required).

#### Options

`-o, --output PATH`
: Output file path.

`-f, --format FORMAT`
: Output audio format.

`-v, --voice VOICE`
: Voice to use for TTS.

`-s, --speed FLOAT`
: Speech speed. Default: `1.0`.

`--gpu / --no-gpu`
: Compatibility shortcut mapping to `auto` or `cpu`.

`--provider PROVIDER`
: ONNX Runtime execution provider or alias.

`--silence FLOAT`
: Silence between chapters. Default: `2.0`.

`--pause-clause FLOAT`
: Pause after clauses in seconds. Default: `0.5`.

`--pause-sentence FLOAT`
: Pause after sentences in seconds. Default: `0.7`.

`--pause-paragraph FLOAT`
: Pause after paragraphs in seconds. Default: `0.9`.

`--pause-variance FLOAT`
: Random variance added to pauses in seconds. Default: `0.05`.

`--pause-mode MODE`
: Pause mode: `tts`, `manual`, or `auto`. Default: `auto`.

`--short-sentence TEXT`
: Short-sentence handling config. Example:
  `mode=randomized,threshold=30,selection=auto,max-tries=3`.
  Can also reference a JSON config with `config=path/to/short_sentence.json`. See `ttsforge config short-sentence init`.

`--announce-chapters / --no-announce-chapters`
: Read chapter titles aloud before chapter content. Default: enabled.

`--chapter-pause FLOAT`
: Pause after chapter title announcement in seconds. Default: `2.0`.

`--chapters SELECTION`
: Select chapters to convert.

`--title TEXT`
: Audiobook title.

`--author TEXT`
: Audiobook author.

`--cover PATH`
: Cover image path.

`--voice-blend SPEC`
: Blend multiple voices.

`--voice-database PATH`
: Path to custom voice database.

`--streaming / --no-streaming`
: Use streaming mode (faster, no resume). Default: resumable.

`--keep-chapters`
: Keep intermediate chapter files.

`-y, --yes`
: Skip confirmation prompts.

#### Examples

```bash
# Convert phoneme file
ttsforge phonemes convert book.phonemes.json

# With voice and output
ttsforge phonemes convert book.phonemes.json -v am_adam -o book.m4b

# Streaming mode (faster but no resume)
ttsforge phonemes convert book.phonemes.json --streaming
```

### phonemes info

Show information about a phoneme file.

```bash
ttsforge phonemes info PHONEME_FILE [OPTIONS]
```

#### Options

`--stats`
: Show detailed token statistics.

#### Examples

```bash
# Basic info
ttsforge phonemes info book.phonemes.json

# With statistics
ttsforge phonemes info book.phonemes.json --stats
```

### phonemes preview

Preview phonemes for given text.

```bash
ttsforge phonemes preview TEXT [OPTIONS]
```

#### Options

`-l, --language LANG`
: Language code for phonemization. Default: `a`.

`-v, --voice VOICE`
: Voice to use for audio preview (when using `--play`).
  Can be a single voice or voice blend (e.g., `af_nicole:50,am_michael:50`).

`--play`
: Generate and play audio preview of the phonemes.

  **Note:** Playback requires the optional `ttsforge[audio]` extra.

`--tokens`
: Show token IDs in addition to phonemes.

`--vocab-version VERSION`
: Vocabulary version. Default: `v1.0`.

#### Examples

```bash
# Preview phonemes
ttsforge phonemes preview "Hello, world!"

# With tokens
ttsforge phonemes preview "Hello, world!" --tokens

# Different language
ttsforge phonemes preview "Bonjour!" -l f

# With audio playback
ttsforge phonemes preview "Test audio" --play

# With voice blend
ttsforge phonemes preview "Test blend" --voice "af_nicole:60,am_michael:40" --play
```
