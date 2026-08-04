# Configuration

ttsforge stores its configuration in a JSON file and provides a CLI interface for
managing settings.

## Configuration File Location

The configuration file is stored at:

- **Linux**: `~/.config/ttsforge/config.json`
- **macOS**: `~/Library/Application Support/ttsforge/config.json`
- **Windows**: `%APPDATA%\ttsforge\config.json`

## Managing Configuration

View current configuration:

```bash
ttsforge config --show
```

Set a configuration option:

```bash
ttsforge config --set KEY VALUE
```

Set multiple options:

```bash
ttsforge config --set default_voice am_adam --set default_speed 1.1
```

Reset to defaults:

```bash
ttsforge config --reset
```

Advanced short-sentence JSON configuration:

```bash
ttsforge config short-sentence init
ttsforge config short-sentence show
ttsforge config short-sentence reset
```

The former `short-sentence-advanced-config` root command remains available as a
deprecated compatibility alias.

## Configuration Options

### spaCy model policy

The global spaCy settings apply to audiobook conversion and phoneme export:

- `use_spacy` (nullable boolean, default `null`) selects automatic local-model
  selection with fallback; `true` is strict and `false` disables spaCy.
- `spacy_model` (nullable string, default `null`) requests one exact local package.
- `spacy_model_size` (nullable `sm`, `md`, `lg`, or `trf`, default `null`) requests one
  exact tier.

When both model and tier are unset, TTSForge selects the highest installed compatible
model for each effective language and falls back without a local model. This is
local-only and never downloads a package. An exact model or tier is strict even when
`use_spacy` is null; `use_spacy=false` disables model discovery and makes both model
fields inactive. The requested tri-state value and concrete sentence/G2P selections
are persisted as resume identity.
The conversion summary shows the request; preflight and persisted state show concrete
sentence/G2P selections. Those selections are part of resume identity.

Examples:

```bash
# New quality-first default
ttsforge config --set spacy_model null --set spacy_model_size null

# Preserve a previous medium or small workflow
ttsforge config --set spacy_model_size md
ttsforge config --set spacy_model en_core_web_sm
ttsforge config --set use_spacy true
ttsforge config --set use_spacy false
ttsforge config --set use_spacy auto
```

Paragraph conversion retains one WAV per render unit: an optional chapter-title unit
and the spoken paragraph units that follow it. The workspace fixes the conversion
unit, generation fingerprint, and selected chapters; use `--fresh` to change them.
Valid units are skipped on resume, and a complete paragraph workspace can rebuild a
missing final audiobook without ONNX initialization. See `examples/paragraph_manifest.py`
for inspection-only validation.

Name extraction additionally accepts `--spacy-model`, `--spacy-model-size`, and
`--language`; its output metadata records the concrete NER-capable package. Existing
configurations without these keys migrate to automatic selection.

### SSMD 0.8 policies

The following keys configure SSMD rendering. Persistent configuration is lower
precedence than a document header; explicit CLI/API values are higher precedence. Do not
use persistent `pause_sentence` or `pause_paragraph` values as SSMD header overrides.

`ssmd_parse_header` (boolean, default `true`) : Parse an exact leading `---` block. Set
false only for literal header text.

`ssmd_unknown_header` (`warn`, `error`, or `ignore`) : Policy for unknown header keys.

`ssmd_missing_voice` (`error` or `use-default`) : Policy for logical voice references
that cannot be resolved.

`ssmd_validate_profile` and `ssmd_emphasis_mode` : Validate Kokoro-supported constructs
and choose `plain` (the default), `approximate`, `warn`, or `error` emphasis behavior.
Plain emphasis is spoken normally without automatic prosody; explicit SSMD prosody
remains active. Approximation can also be selected per conversion with
`--enable-ssmd-emphasis`.

`ssmd_voice_bindings` : Mapping such as `{"narrator": "af_sarah"}`; CLI/API bindings are
supplied with repeated `--ssmd-voice ROLE=VOICE`.

### EPUB Markdown extraction, emphasis, and AudioSig prosody

These settings form three related but distinct layers:

1. `epub_content_mode` (`markdown`, default `markdown`) selects epub2text's structured
   chapter Markdown API. `plain` is an explicit compatibility/debug path; TTSForge does
   not silently fall back to it when the Markdown API is unavailable.
2. `detect_emphasis` (boolean, default `true`) preserves or unwraps EPUB italic and bold
   semantics while leaving headings, paragraphs, and scene breaks independent. CSS
   emphasis is resolved by epub2text in Markdown mode.
3. `ssmd_emphasis_mode` controls how preserved SSMD emphasis is rendered audibly.

`plain` preserves normal synthesis, `approximate` enables the current deterministic
gain-only approximation, and `warn`/`error` report or reject emphasis metadata. The
approximation does not provide configurable strength profiles.

`prosody_method` (default `wsola`) selects the AudioSig algorithm for explicit SSMD rate
and pitch annotations. Supported methods are `wsola`, `esola`, `td_psola`, `psola` (an
alias for `td_psola`), and `phase_vocoder`.

Additional persistent prosody settings are `prosody_fallback_methods` (JSON list,
default `["wsola", "phase_vocoder"]`), `prosody_strict`, `prosody_clip`,
`prosody_n_fft`, nullable `prosody_hop_length`, `prosody_filter_width`,
`prosody_rolloff`, and `prosody_boundary_blend_ms`. The default WSOLA path is the
general audiobook choice; ESOLA and PSOLA are speech-oriented alternatives, while phase
vocoder is primarily a reference or fallback path.

Examples:

```bash
ttsforge config --set detect_emphasis true --set ssmd_emphasis_mode approximate
ttsforge config --set epub_content_mode markdown
ttsforge config --set epub_content_mode plain
ttsforge config --set prosody_method esola --set prosody_fallback_methods '["wsola","phase_vocoder"]'
ttsforge config --set prosody_method psola
ttsforge config --set prosody_strict true --set prosody_fallback_methods '[]'
```

`ssmd_audio_allow_remote` (default `false`), `ssmd_audio_root`, `ssmd_audio_max_bytes`
(default `20000000`), and `ssmd_audio_max_duration_s` (default `120`) : Bound
local/HTTPS audio annotation resolution. Remote audio is opt-in.

### Voice and Language Settings

`default_voice` : Default TTS voice to use.

- Type: string
- Default: `af_heart`
- Example: `ttsforge config --set default_voice am_adam`

`default_language` : Default language code.

- Type: string
- Default: `a` (American English)
- Choices: `a`, `b`, `e`, `f`, `h`, `i`, `j`, `p`, `z`
- Example: `ttsforge config --set default_language b`

`phonemization_lang` : Override language for phonemization (e.g., `de`, `fr`, `en-us`).

- Type: string or null
- Default: `None`
- Example: `ttsforge config --set phonemization_lang de`

`default_speed` : Default speech speed multiplier.

- Type: float
- Default: `1.0`
- Range: `0.5` to `2.0`
- Example: `ttsforge config --set default_speed 1.1`

### Output Settings

`default_format` : Default output audio format.

- Type: string
- Default: `m4b`
- Choices: `wav`, `mp3`, `flac`, `opus`, `m4b`
- Example: `ttsforge config --set default_format mp3`

### Processing Settings

`onnx_provider` : ONNX Runtime execution provider used for synthesis. Use `auto`, `cpu`,
`cuda`, `openvino`, `directml`/`dml`, `coreml`, `nnapi`, `xnnpack`, or a full
`*ExecutionProvider` name. TTSForge validates the syntax and PyKokoro validates runtime
availability.

- Type: string
- Default: `cpu`
- Examples: `ttsforge config --set onnx_provider nnapi` and
  `ttsforge config --set onnx_provider NnapiExecutionProvider`

`use_gpu` : Legacy compatibility setting. `true` maps to `onnx_provider=auto` and
`false` maps to `onnx_provider=cpu` when no provider is configured.

- Type: boolean
- Default: `false`
- Example: `ttsforge config --set use_gpu true`

`model_quality` : ONNX model quality/quantization.

- Type: string
- Default: `fp32`
- Choices: `fp32`, `fp16`, `q8`, `q8f16`, `q4`, `q4f16`, `uint8`, `uint8f16`
- Example: `ttsforge config --set model_quality fp16`

`model_variant` : Model variant to download.

- Type: string
- Default: `v1.0`
- Choices: `v1.0`, `v1.1-zh`, `v1.1-de`
- Example: `ttsforge config --set model_variant v1.1-de`

`auto_detect_language` : Automatically detect language from EPUB metadata.

- Type: boolean
- Default: `true`
- Example: `ttsforge config --set auto_detect_language false`

`default_split_mode` : Default text splitting mode for processing.

- Type: string
- Default: `auto`
- Choices: `auto`, `line`, `paragraph`, `sentence`, `clause`
- Example: `ttsforge config --set default_split_mode sentence`

`--conversion-unit` is intentionally separate from `default_split_mode`. It is a
per-workspace CLI choice: `chapter` (default) keeps existing chapter output, while
`paragraph` retains one WAV per spoken paragraph and resumes at unit boundaries. The
saved choice is restored on resume and cannot be changed without `--fresh`.

### Read Settings

`default_content_mode` : Default content mode for `read` (`chapters` or `pages`).

- Type: string
- Default: `chapters`
- Example: `ttsforge config --set default_content_mode pages`

`default_page_size` : Synthetic page size in characters for `read` pages mode.

- Type: integer
- Default: `2000`
- Example: `ttsforge config --set default_page_size 2500`

### Mixed-Language Settings

`use_mixed_language` : Enable automatic detection and handling of multiple languages in
text.

- Type: boolean
- Default: `false`
- Requires: `lingua-language-detector` package (`pip install lingua-language-detector`)
- Example: `ttsforge config --set use_mixed_language true`

`mixed_language_primary` : Primary/fallback language for mixed-language mode.

- Type: string or null
- Default: `None`
- Supported: `en-us`, `en-gb`, `de`, `fr-fr`, `es`, `it`, `pt`, `pl`, `tr`, `ru`, `ko`,
  `ja`, `zh`/`cmn`
- Example: `ttsforge config --set mixed_language_primary de`

`mixed_language_allowed` : List of languages allowed for auto-detection in
mixed-language mode.

- Type: list of strings or null
- Default: `None`
- Required when `use_mixed_language` is enabled
- Example: `ttsforge config --set mixed_language_allowed "['de', 'en-us']"`

`mixed_language_confidence` : Confidence threshold for language detection (0.0-1.0).

- Type: float
- Default: `0.7`
- Range: `0.0` to `1.0`
- Higher values require more confidence before switching languages
- Example: `ttsforge config --set mixed_language_confidence 0.8`

### Audio Timing Settings

`silence_between_chapters` : Silence duration between chapters in seconds.

- Type: float
- Default: `2.0`
- Example: `ttsforge config --set silence_between_chapters 3.0`

`pause_clause` : Pause after clauses in seconds.

- Type: float
- Default: `0.5`
- Example: `ttsforge config --set pause_clause 0.4`

`pause_sentence` : Pause after sentences in seconds.

- Type: float
- Default: `0.7`
- Example: `ttsforge config --set pause_sentence 0.6`

`pause_paragraph` : Pause after paragraphs in seconds.

- Type: float
- Default: `0.9`
- Example: `ttsforge config --set pause_paragraph 1.1`

`pause_variance` : Random variance added to pause durations in seconds.

- Type: float
- Default: `0.05`
- Example: `ttsforge config --set pause_variance 0.08`

`pause_mode` : Pause mode: `tts`, `manual`, or `auto`.

- Type: string
- Default: `auto`
- Example: `ttsforge config --set pause_mode manual`

### Chapter Announcement Settings

`announce_chapters` : Read chapter titles aloud before chapter content.

- Type: boolean
- Default: `true`
- Example: `ttsforge config --set announce_chapters false`

`chapter_pause_after_title` : Pause duration after the chapter title announcement in
seconds.

- Type: float
- Default: `2.0`
- Example: `ttsforge config --set chapter_pause_after_title 1.5`

### File Output Settings

`save_chapters_separately` : Save individual chapter audio files.

- Type: boolean
- Default: `false`
- Example: `ttsforge config --set save_chapters_separately true`

`merge_at_end` : Merge chapter files into final audiobook.

- Type: boolean
- Default: `true`
- Example: `ttsforge config --set merge_at_end false`

### Filename Template Settings

These settings control how output files are named. See {doc}`filename_templates` for
details.

`output_filename_template` : Template for final audiobook filenames.

- Type: string
- Default: `{book_title}`
- Example: `ttsforge config --set output_filename_template "{author}_{book_title}"`

`chapter_filename_template` : Template for chapter WAV file names during conversion.

- Type: string
- Default: `{chapter_num:03d}_{book_title}_{chapter_title}`
- Example:
  `ttsforge config --set chapter_filename_template "{chapter_num:03d}_{chapter_title}"`

`phoneme_export_template` : Template for phoneme export filenames.

- Type: string
- Default: `{book_title}`
- Example: `ttsforge config --set phoneme_export_template "{book_title}_phonemes"`

`default_title` : Fallback title when book has no metadata.

- Type: string
- Default: `Untitled`
- Example: `ttsforge config --set default_title "Unknown Book"`

## Complete Configuration Reference

```{list-table}
:header-rows: 1
:widths: 30 15 20 35

* - Option
  - Type
  - Default
  - Description
* - `default_voice`
  - string
  - `af_heart`
  - Default TTS voice
* - `default_language`
  - string
  - `a`
  - Default language code
* - `default_speed`
  - float
  - `1.0`
  - Speech speed multiplier
* - `default_format`
  - string
  - `m4b`
  - Output audio format
* - `use_gpu`
  - boolean
  - `false`
  - Legacy provider compatibility shortcut
* - `onnx_provider`
  - string
  - `cpu`
  - ONNX Runtime provider alias or full name
* - `model_quality`
  - string
  - `fp32`
  - Model quality/quantization
* - `model_variant`
  - string
  - `v1.0`
  - Model variant
* - `silence_between_chapters`
  - float
  - `2.0`
  - Silence between chapters (seconds)
* - `pause_clause`
  - float
  - `0.5`
  - Clause pause (seconds)
* - `pause_sentence`
  - float
  - `0.7`
  - Sentence pause (seconds)
* - `pause_paragraph`
  - float
  - `0.9`
  - Paragraph pause (seconds)
* - `pause_variance`
  - float
  - `0.05`
  - Pause variance (seconds)
* - `pause_mode`
  - string
  - `auto`
  - Pause mode (tts/manual/auto)
* - `announce_chapters`
  - boolean
  - `true`
  - Speak chapter titles
* - `chapter_pause_after_title`
  - float
  - `2.0`
  - Pause after chapter titles (seconds)
* - `save_chapters_separately`
  - boolean
  - `false`
  - Keep chapter audio files
* - `merge_at_end`
  - boolean
  - `true`
  - Merge chapters into final file
* - `auto_detect_language`
  - boolean
  - `true`
  - Auto-detect language from EPUB
* - `phonemization_lang`
  - string/null
  - `None`
  - Override phonemization language
* - `default_split_mode`
  - string
  - `auto`
  - Text splitting mode
* - `default_content_mode`
  - string
  - `chapters`
  - Default read mode (chapters/pages)
* - `default_page_size`
  - integer
  - `2000`
  - Page size for read pages mode
* - `output_filename_template`
  - string
  - `{book_title}`
  - Output filename template
* - `chapter_filename_template`
  - string
  - `{chapter_num:03d}_...`
  - Chapter filename template
* - `phoneme_export_template`
  - string
  - `{book_title}`
  - Phoneme export template
* - `default_title`
  - string
  - `Untitled`
  - Fallback title
* - `use_mixed_language`
  - boolean
  - `false`
  - Enable mixed-language mode
* - `mixed_language_primary`
  - string/null
  - `None`
  - Primary language for mixed mode
* - `mixed_language_allowed`
  - list/null
  - `None`
  - Allowed languages list
* - `mixed_language_confidence`
  - float
  - `0.7`
  - Language detection threshold
```

## Example Configuration File

Here's an example `config.json` with custom settings:

```json
{
  "default_voice": "am_adam",
  "default_language": "a",
  "default_speed": 1.1,
  "default_format": "m4b",
  "use_gpu": true,
  "model_quality": "fp32",
  "model_variant": "v1.0",
  "silence_between_chapters": 2.5,
  "pause_clause": 0.5,
  "pause_sentence": 0.7,
  "pause_paragraph": 0.9,
  "pause_variance": 0.05,
  "pause_mode": "auto",
  "enable_short_sentence": null,
  "announce_chapters": true,
  "chapter_pause_after_title": 2.0,
  "save_chapters_separately": false,
  "merge_at_end": true,
  "auto_detect_language": true,
  "phonemization_lang": null,
  "default_split_mode": "sentence",
  "default_content_mode": "chapters",
  "default_page_size": 2000,
  "output_filename_template": "{author} - {book_title}",
  "chapter_filename_template": "{chapter_num:03d}_{chapter_title}",
  "phoneme_export_template": "{book_title}",
  "default_title": "Untitled",
  "use_mixed_language": false,
  "mixed_language_primary": null,
  "mixed_language_allowed": null,
  "mixed_language_confidence": 0.7
}
```

## Command-Line Override

Configuration values can be overridden on the command line. Command-line options take
precedence over configuration file settings:

```bash
# Use configured voice, but override speed
ttsforge convert book.epub -s 1.2

# Override voice and format
ttsforge convert book.epub -v bf_emma -f mp3

# Select a provider for one command
ttsforge sample "Provider test" --provider xnnpack
```

Provider precedence is explicit `--provider`, then `--gpu`/`--no-gpu`, then
`onnx_provider`, then legacy `use_gpu`, then CPU. PyKokoro may apply its documented
`ONNX_PROVIDER` environment override during runtime provider resolution.

## Environment Variables

TTSForge configuration has no separate environment-variable file format. The PyKokoro
runtime may still honor its documented `ONNX_PROVIDER` environment override after
TTSForge resolves the configured provider.

Set `TTSFORGE_MEMORY_DEBUG=1` to enable dependency-free process-memory diagnostics
during conversion. Logs include RSS, peak RSS, available memory, and the effective ONNX
provider around runner initialization, chapter synthesis, WAV writing, result release,
state saves, final merging, and converter cleanup. RSS may remain elevated because
native allocators retain high-water pages; that alone is not evidence of a provider
leak.

TTSForge requires PyKokoro `>=0.8.1,<0.9`, uses compact segment results, and releases
completed chapter audio before the next chapter synthesis. Whole-chapter synthesis
remains buffered and streaming is future work.

## Model source status

Set `model_source` to `github` when using the GitHub asset set. `ttsforge config --show`
uses PyKokoro's source/variant/quality-aware asset paths and reports missing assets. If
the configured set is incomplete but the alternate supported source is complete, the
command reports that alternate and gives an activation command without silently
switching sources.

On Termux/Android, a typical setup is:

```bash
ttsforge config --set model_source github --set model_variant v1.0 \
   --set model_quality fp32 --set onnx_provider nnapi
ttsforge config --show
```
