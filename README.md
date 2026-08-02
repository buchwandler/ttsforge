[![PyPI - Version](https://img.shields.io/pypi/v/ttsforge)](https://pypi.org/project/ttsforge/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ttsforge)
![PyPI - Downloads](https://img.shields.io/pypi/dm/ttsforge)
[![codecov](https://codecov.io/gh/buchwandler/ttsforge/graph/badge.svg?token=iCHXwbjAXG)](https://codecov.io/gh/buchwandler/ttsforge)

# ttsforge

Convert EPUB files to audiobooks using Kokoro ONNX TTS.

ttsforge is a command-line tool that transforms EPUB ebooks into high-quality audiobooks
with support for 54 neural voices across 9 languages.

## Features

- **EPUB to Audiobook**: Convert EPUB files to M4B, MP3, WAV, FLAC, or OPUS
- **54 Neural Voices**: High-quality TTS in 9 languages
- **SSMD Editing**: Edit intermediate SSMD files to fine-tune pronunciation and pacing
- **Custom Phoneme Dictionary**: Control pronunciation of names and technical terms
- **Auto Name Extraction**: Automatically extract names from books for phoneme
  customization
- **Mixed-Language Support**: Auto-detect and handle multiple languages in text
- **Resumable Conversions**: Interrupt and resume long audiobook conversions
- **Phoneme Pre-tokenization**: Pre-process text for faster batch conversions
- **Configurable Filenames**: Template-based output naming with book metadata
- **Voice Blending**: Mix multiple voices for custom narration
- **ONNX Runtime Providers**: CPU, CUDA, NNAPI, XNNPACK, and other PyKokoro providers
- **Chapter Support**: M4B files include chapter markers from EPUB
- **EPUB Structure Preservation**: Markdown extraction keeps chapter headings,
  paragraphs, scene breaks, and inline emphasis in generated SSMD
- **Streaming Read**: Listen to EPUB/text directly with the `read` command
- **Reduced Memory Retention**: Release chapter audio buffers before the next synthesis

## Installation

```bash
pip install ttsforge
```

The base installation includes the CPU ONNX Runtime provider. Provider-dependent modules
are loaded only when rendering audio, so `import ttsforge` and `ttsforge --help` remain
usable for configuration and inspection operations.

Optional extras:

```bash
# Audio playback (required for --play and read)
pip install "ttsforge[audio]"

# Bundled ffmpeg (if you cannot install system ffmpeg)
pip install "ttsforge[static_ffmpeg]"

# GPU acceleration (CUDA; use a fresh environment when replacing the CPU provider)
pip install "ttsforge[gpu]"
```

TTSForge requires PyKokoro 0.7.5 or newer within the 0.7 release line. It uses compact
segment results and releases completed chapter audio before the next chapter starts.
Whole-chapter synthesis remains buffered; streaming synthesis is future work.

To log opt-in process-memory snapshots during conversion:

```bash
TTSFORGE_MEMORY_DEBUG=1 ttsforge convert book.epub
```

Diagnostics report RSS, peak RSS, available memory, and the effective ONNX provider at
runner, chapter, merge, and cleanup phases. A stable high RSS after release can reflect
native allocator high-water behavior and does not by itself prove a provider leak.

### Dependencies

- **ffmpeg**: Required for MP3/FLAC/OPUS/M4B output and chapter merging
- **espeak-ng**: Required for phonemization
- **spaCy (optional)**: Required for sentence splitting, name extraction, and
  spaCy-aware phonemization workflows
- **sounddevice (optional)**: Required for audio playback (`--play`, `read`)

**Ubuntu/Debian:**

```bash
sudo apt-get install ffmpeg espeak-ng
```

**macOS:**

```bash
brew install ffmpeg espeak-ng
```

**spaCy models (optional):**

```bash
pip install spacy
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_md
```

## Quick Start

```bash
# Convert an EPUB to audiobook (M4B with chapters)
ttsforge convert book.epub

# Use a specific voice
ttsforge convert book.epub -v am_adam

# Convert specific chapters
ttsforge convert book.epub --chapters 1-5

# List available voices
ttsforge voices

# Generate a voice demo
ttsforge demo

# Read an EPUB aloud (streaming playback)
ttsforge read book.epub
```

## Usage

### Basic Conversion

```bash
ttsforge convert book.epub
```

Creates `book.m4b` with default settings (voice: `af_heart`, format: M4B).

### Voice Selection

```bash
# List all voices
ttsforge voices

# List voices for a language
ttsforge voices -l b  # British English

# Convert with specific voice
ttsforge convert book.epub -v bf_emma
```

### Output Formats

```bash
ttsforge convert book.epub -f mp3    # MP3
ttsforge convert book.epub -f wav    # WAV (uncompressed)
ttsforge convert book.epub -f flac   # FLAC (lossless)
ttsforge convert book.epub -f opus   # OPUS
ttsforge convert book.epub -f m4b    # M4B audiobook (default)
```

### Chapter Selection

```bash
# Preview chapters
ttsforge list book.epub

# Convert range
ttsforge convert book.epub --chapters 1-5

# Convert specific chapters
ttsforge convert book.epub --chapters 1,3,5,7

# Mixed selection
ttsforge convert book.epub --chapters 1-3,5,10-15
```

### Speed Control

```bash
ttsforge convert book.epub -s 1.2   # 20% faster
ttsforge convert book.epub -s 0.9   # 10% slower
```

### Resumable Conversions

Conversions are resumable by default. If interrupted, re-run the same command:

```bash
ttsforge convert book.epub  # Resumes from last chapter
ttsforge convert book.epub --fresh  # Start over
```

### Phoneme Workflow

For large books or batch processing, pre-tokenize to phonemes:

```bash
# Export to phonemes (fast, CPU-only)
ttsforge phonemes export book.epub

# Convert phonemes to audio (can run on different machine)
ttsforge phonemes convert book.phonemes.json -v am_adam
```

### Configuration

```bash
# View settings
ttsforge config --show

# Set defaults
ttsforge config --set default_voice am_adam
ttsforge config --set default_format mp3
ttsforge config --set onnx_provider nnapi

# Reset to defaults
ttsforge config --reset
```

The legacy two-token configuration option remains available and may be repeated. Values
beginning with a dash are accepted as values rather than being interpreted as options:

```bash
ttsforge config --set default_speed 1.1 --set default_title -draft
```

Advanced short-sentence handling can be managed with a JSON config:

```bash
# Create and link the advanced short-sentence config
ttsforge config short-sentence init

# Show the advanced short-sentence config
ttsforge config short-sentence show

# Reset the advanced short-sentence config to defaults
ttsforge config short-sentence reset
```

The former `short-sentence-advanced-config` root command remains available as a
deprecated compatibility alias.

### Filename Templates

Customize output filenames with metadata:

```bash
ttsforge config --set output_filename_template "{author} - {book_title}"
```

Available variables: `{book_title}`, `{author}`, `{chapter_title}`, `{chapter_num}`,
`{input_stem}`, `{chapters_range}`

## Voices

ttsforge includes 54 voices across 9 languages:

| Language             | Code | Voices | Default       |
| -------------------- | ---- | ------ | ------------- |
| American English     | `a`  | 20     | `af_heart`    |
| British English      | `b`  | 8      | `bf_emma`     |
| Spanish              | `e`  | 3      | `ef_dora`     |
| French               | `f`  | 1      | `ff_siwis`    |
| Hindi                | `h`  | 4      | `hf_alpha`    |
| Italian              | `i`  | 2      | `if_sara`     |
| Japanese             | `j`  | 5      | `jf_alpha`    |
| Brazilian Portuguese | `p`  | 3      | `pf_dora`     |
| Mandarin Chinese     | `z`  | 8      | `zf_xiaoxiao` |

Voice naming: `{lang}{gender}_{name}` (e.g., `am_adam` = American Male "Adam")

### Voice Demo

```bash
# Demo all voices
ttsforge demo

# Demo specific language
ttsforge demo -l a

# Save individual voice files
ttsforge demo --separate -o ./voices/
```

### Voice Blending

Mix multiple voices for custom narration:

```bash
# Using --voice parameter (auto-detects blend format)
ttsforge convert book.epub --voice "af_nicole:50,am_michael:50"

# Using --voice-blend parameter (traditional method)
ttsforge convert book.epub --voice-blend "af_nicole:50,am_michael:50"

# Weighted blends (70% Nicole, 30% Michael)
ttsforge convert book.epub --voice "af_nicole:70,am_michael:30"

# Works with all commands
ttsforge sample "Hello world" --voice "af_sky:60,bf_emma:40" -p
ttsforge phonemes preview "Test blend" --voice "am_adam:50,am_michael:50" --play
```

### Mixed-Language Support

For books with multiple languages (e.g., German text with English technical terms):

```bash
# Enable mixed-language auto-detection
ttsforge convert book.epub \
  --use-mixed-language \
  --mixed-language-primary de \
  --mixed-language-allowed de,en-us

# Test with a sample
ttsforge sample \
  "Das ist ein deutscher Satz. This is an English sentence." \
  --use-mixed-language \
  --mixed-language-primary de \
  --mixed-language-allowed de,en-us
```

**Requirements**: Install `lingua-language-detector` for automatic language detection:

```bash
pip install lingua-language-detector
```

**Configuration options:**

- `--use-mixed-language` - Enable mixed-language mode
- `--mixed-language-primary LANG` - Primary language (e.g., `de`, `en-us`)
- `--mixed-language-allowed LANGS` - Comma-separated list of allowed languages
- `--mixed-language-confidence FLOAT` - Detection confidence threshold (0.0-1.0,
  default: 0.7)

Supported languages: `en-us`, `en-gb`, `de`, `fr-fr`, `es`, `it`, `pt`, `pl`, `tr`,
`ru`, `ko`, `ja`, `zh`/`cmn`

### SSMD Editing

ttsforge uses SSMD (Speech Synthesis Markdown) as an intermediate format between your
EPUB and the final audio. This allows you to fine-tune pronunciation, pacing, and
emphasis before conversion.

#### How It Works

During conversion, ttsforge automatically generates `.ssmd` files for each chapter:

```
.{book_title}_chapters/
├── chapter_001_intro.ssmd      # Editable text with speech markup
├── chapter_001_intro.wav
├── chapter_002_chapter1.ssmd
├── chapter_002_chapter1.wav
```

When you resume a conversion, ttsforge detects if you've edited any SSMD files and
automatically regenerates the audio.

#### Basic Workflow

```bash
# 1. Start conversion
ttsforge convert book.epub

# 2. Pause conversion (Ctrl+C)

# 3. Edit SSMD files to fix pronunciation or pacing
vim .book_chapters/chapter_001_intro.ssmd

# 4. Resume - automatically detects edits and regenerates audio
ttsforge convert book.epub
```

#### SSMD Syntax

SSMD files use a simple markdown-like syntax:

**Structural Breaks** (control pauses):

```
...p    # Paragraph break (0.5-1.0s pause)
...s    # Sentence break (0.1-0.3s pause)
...c    # Clause break (shorter pause)
```

**Emphasis**:

```
*text*      # Moderate emphasis
**text**    # Strong emphasis
```

EPUB processing has three independent layers:

1. **Semantic extraction**: epub2text converts EPUB navigation, headings, paragraphs,
   scene breaks, semantic emphasis, and CSS emphasis into chapter Markdown.
2. **SSMD generation**: TTSForge preserves that controlled Markdown in `.ssmd` files;
   `##` headings and `*`/`**` spans remain editable and parseable.
3. **Audible rendering**: `ssmd_emphasis_mode` controls whether emphasis is spoken
   normally, approximated, warned on, or rejected.

Markdown extraction and emphasis preservation are enabled by default, while audible
emphasis remains plain:

```bash
# Default: Markdown structure and emphasis are preserved; audio remains plain
ttsforge convert book.epub

# Unwrap emphasis while retaining headings and scene breaks
ttsforge convert book.epub --no-detect-emphasis

# Compare with the legacy flattened extraction path
ttsforge convert book.epub --epub-content-mode plain

# Detect styling and explicitly opt into the current gain-only approximation
ttsforge convert book.epub --detect-emphasis --enable-ssmd-emphasis

# Choose the persisted/default policy explicitly
ttsforge config --set ssmd_emphasis_mode plain
ttsforge convert book.epub --ssmd-emphasis approximate

# Select AudioSig prosody for explicit SSMD rate/pitch annotations
ttsforge config --set prosody_method esola
ttsforge convert book.epub --prosody-method psola
```

`epub_content_mode`, `detect_emphasis`, `ssmd_emphasis_mode`, and `prosody_method` are
separate settings. The first selects Markdown or explicit legacy plain extraction; the
second preserves or unwraps inline emphasis without affecting headings; the third
controls SSMD emphasis policy; and the fourth selects AudioSig processing for explicit
rate and pitch annotations. The current approximate emphasis profile changes gain only
and does not expose custom strength values. `psola` is accepted as an alias for
AudioSig's canonical `td_psola`.

The available policies are `plain`, `approximate`, `warn`, and `error`. Explicit SSMD
prosody such as `[fast words]{rate="fast"}` remains active in plain emphasis mode.

**Custom Phonemes**:

```
[Hermione]{ph="hɝmˈIni"}    # Override pronunciation
[API]{ph="ˌeɪpiˈaɪ"}        # Technical terms
```

**Language annotations** (supported):

```
[Bonjour]{lang="fr"}    # Mark text as French
```

#### Example SSMD File

```ssmd
Chapter One ...p

[Harry]{ph="hæɹi"} Potter was a *highly unusual* boy in many ways. ...s
For one thing, he **hated** the summer holidays more than any other
time of year. ...s For another, he really wanted to do his homework,
but was forced to do it in secret, in the dead of the night. ...p

And he also happened to be a wizard. ...p
```

#### When to Use SSMD Editing

- **Pronunciation issues**: Character names, technical terms, foreign words
- **Pacing problems**: Adjust paragraph and sentence breaks
- **Emphasis corrections**: Add or remove emphasis on specific words
- **Combine with phoneme dictionary**: Phoneme dictionary applied automatically to SSMD

For detailed SSMD 0.8 syntax, validation, policy options, and Kokoro limitations, see
[docs/ssmd.md](docs/ssmd.md).

### Custom Phoneme Dictionary

Control pronunciation of character names, technical terms, and foreign words with custom
phoneme dictionaries.

#### Quick Start

```bash
# 1. Extract names from your book (requires spacy)
ttsforge extract-names mybook.epub

# 2. Review the generated custom_phonemes.json file
ttsforge list-names custom_phonemes.json

# 3. Test pronunciation with sample
ttsforge sample "Hermione loves Kubernetes" --phoneme-dict custom_phonemes.json -p

# 4. Convert with custom pronunciations
ttsforge convert mybook.epub --phoneme-dict custom_phonemes.json
```

#### Requirements

For automatic name extraction (optional but recommended):

```bash
pip install spacy
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_md
```

#### Workflow

**1. Extract names from your book:**

```bash
# Extract frequent names (≥3 occurrences)
ttsforge extract-names mybook.epub

# Preview without saving
ttsforge extract-names mybook.epub --preview

# Only very frequent names (≥10 occurrences)
ttsforge extract-names mybook.epub --min-count 10 -o names.json

# Include all proper nouns, not just detected person names
ttsforge extract-names mybook.epub --include-all
```

This creates a `custom_phonemes.json` file with auto-generated phoneme suggestions.

**2. Review and edit the dictionary:**

```bash
# List all entries
ttsforge list-names custom_phonemes.json

# Sort alphabetically
ttsforge list-names custom_phonemes.json --sort-by alpha
```

Edit `custom_phonemes.json` to fix any incorrect phonemes. The file format is:

```json
{
  "_metadata": {
    "generated_from": "mybook.epub",
    "language": "en-us"
  },
  "entries": {
    "Hermione": {
      "phoneme": "hɝmˈIni",
      "occurrences": 847,
      "verified": false
    },
    "Kubernetes": {
      "phoneme": "kubɚnˈɛtɪs",
      "occurrences": 12,
      "verified": false
    }
  }
}
```

Or use the simple format:

```json
{
  "Hermione": "hɝmˈIni",
  "Kubernetes": "kubɚnˈɛtɪs"
}
```

**3. Test pronunciation:**

```bash
# Test specific names
ttsforge sample "Hermione and Harry" --phoneme-dict custom_phonemes.json -p

# Test and save to file
ttsforge sample "Hermione and Harry" --phoneme-dict custom_phonemes.json -o test.wav
```

**4. Convert your book:**

```bash
# Use the dictionary for conversion
ttsforge convert mybook.epub --phoneme-dict custom_phonemes.json

# Case-sensitive matching (default is case-insensitive)
ttsforge convert mybook.epub \
  --phoneme-dict custom_phonemes.json \
  --phoneme-dict-case-sensitive
```

#### Manual Dictionary Creation

You can create a dictionary manually without extraction:

```json
{
  "Katniss": "kætnɪs",
  "Peeta": "pitə",
  "Panem": "pænəm"
}
```

#### Getting IPA Phonemes

To find the correct IPA phonemes for a word:

1. Use `ttsforge sample "word" -p` to hear the default pronunciation
2. Look up IPA pronunciation online (e.g., Wiktionary, IPA dictionaries)
3. Or use the auto-generated phonemes as a starting point

**Note:** Phoneme matching is case-insensitive by default and respects word boundaries
(e.g., "test" won't match "testing").

## Commands

The CLI is built from explicit typed Typer command wrappers. Help and version paths do
not initialize the ONNX provider; only executing a backend-dependent command imports its
implementation module.

| Command            | Description                          |
| ------------------ | ------------------------------------ |
| `convert`          | Convert EPUB to audiobook            |
| `list`             | List chapters in EPUB                |
| `info`             | Show EPUB metadata                   |
| `sample`           | Generate sample audio                |
| `read`             | Stream playback from EPUB/text       |
| `voices`           | List available voices                |
| `demo`             | Generate voice demo                  |
| `extract-names`    | Extract names for phoneme dictionary |
| `list-names`       | List names in phoneme dictionary     |
| `download`         | Download ONNX models                 |
| `config`           | Manage configuration                 |
| `phonemes export`  | Export EPUB to phonemes              |
| `phonemes convert` | Convert phonemes to audio            |
| `phonemes info`    | Show phoneme file info               |
| `phonemes preview` | Preview text as phonemes             |

## ONNX Runtime Providers

Select an ONNX Runtime execution provider globally or per command. The value may be an
alias (`auto`, `cpu`, `cuda`, `openvino`, `directml`/`dml`, `coreml`, `nnapi`, or
`xnnpack`) or a full `*ExecutionProvider` name:

```bash
ttsforge config --set onnx_provider nnapi
ttsforge sample "NNAPI test" --provider nnapi
ttsforge sample "CPU test" --provider CPUExecutionProvider
```

The legacy Boolean flags remain compatibility shortcuts: `--gpu` maps to `auto` and
`--no-gpu` maps to `cpu`. NNAPI and XNNPACK are execution providers, not GPU modes.
PyKokoro applies its documented `ONNX_PROVIDER` environment override after TTSForge
resolves configuration.

```bash
ttsforge convert book.epub --gpu
ttsforge convert book.epub --provider xnnpack
```

For Termux/Android, install a PyKokoro v0.7.5-compatible ONNX Runtime build, then use
`--provider nnapi` or `--provider xnnpack`. Configure GitHub model assets explicitly
when using that source:

```bash
ttsforge config --set model_source github --set onnx_provider nnapi
ttsforge config --show
```

`config --show` reports the configured source/variant/quality. If that set is incomplete
but the other supported source has a complete set, it reports the alternate without
switching sources automatically.

## Configuration Options

| Option                      | Default        | Description                              |
| --------------------------- | -------------- | ---------------------------------------- |
| `default_voice`             | `af_heart`     | Default TTS voice                        |
| `default_language`          | `a`            | Default language code                    |
| `default_speed`             | `1.0`          | Speech speed (0.5-2.0)                   |
| `default_format`            | `m4b`          | Output format                            |
| `onnx_provider`             | `cpu`          | ONNX Runtime provider alias or full name |
| `use_gpu`                   | `false`        | Legacy shortcut (`true` => `auto`)       |
| `model_quality`             | `fp32`         | Model quality/quantization               |
| `model_variant`             | `v1.0`         | Model variant                            |
| `silence_between_chapters`  | `2.0`          | Chapter gap (seconds)                    |
| `pause_clause`              | `0.5`          | Clause pause (seconds)                   |
| `pause_sentence`            | `0.7`          | Sentence pause (seconds)                 |
| `pause_paragraph`           | `0.9`          | Paragraph pause (seconds)                |
| `pause_variance`            | `0.05`         | Pause variance (seconds)                 |
| `pause_mode`                | `auto`         | Pause mode (`tts`, `manual`, `auto`)     |
| `enable_short_sentence`     | `None`         | Handle short sentences                   |
| `announce_chapters`         | `true`         | Speak chapter titles                     |
| `chapter_pause_after_title` | `2.0`          | Pause after chapter title                |
| `phonemization_lang`        | `None`         | Override phonemization language          |
| `output_filename_template`  | `{book_title}` | Output filename template                 |
| `default_content_mode`      | `chapters`     | `read` mode (`chapters`/`pages`)         |
| `default_page_size`         | `2000`         | Page size for `read` pages mode          |
| `use_mixed_language`        | `false`        | Enable mixed-language mode               |
| `mixed_language_primary`    | `None`         | Primary language for mixed mode          |
| `mixed_language_allowed`    | `None`         | Allowed languages (list)                 |
| `mixed_language_confidence` | `0.7`          | Language detection threshold             |

## Documentation

Full documentation: https://ttsforge.readthedocs.io/

Build locally:

```bash
pip install -r docs/requirements.txt
make html
```

## Requirements

- Python 3.10+
- ffmpeg (for MP3/FLAC/OPUS/M4B output and chapter merging)
- espeak-ng (for phonemization)
- ~330MB disk space (ONNX models)
- sounddevice (optional, for audio playback)

## License

MIT License

## Credits

- [Kokoro](https://github.com/hexgrad/kokoro) - TTS model
- [espeak-ng](https://github.com/espeak-ng/espeak-ng) - Phonemization
- [ONNX Runtime](https://onnxruntime.ai/) - Model inference
