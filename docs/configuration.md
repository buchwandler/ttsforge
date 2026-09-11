# Configuration

ttsforge stores its configuration in a JSON file and provides a CLI interface for
managing settings.

The active generation stack targets PyKokoro 0.9.4 with kokorog2p 0.9.5, phrasplit
0.3.7, and SSMD 0.8.7. Omitted model and voice settings remain `None` so PyKokoro can
select language-aware metadata defaults.

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

## Configuration Options

### spaCy model policy

The global spaCy settings apply to audiobook conversion and phoneme export:

- `use_spacy` (nullable boolean, default `null`) selects automatic local-model selection
  with fallback; `true` is strict and `false` disables spaCy.
- `spacy_model` (nullable string, default `null`) requests one exact local package.
- `spacy_model_size` (nullable `sm`, `md`, `lg`, or `trf`, default `null`) requests one
  exact tier.

When both model and tier are unset, TTSForge selects the highest installed compatible
model for each effective language and falls back without a local model. This is
local-only and never downloads a package. An exact model or tier is strict even when
`use_spacy` is null; `use_spacy=false` disables model discovery and makes both model
fields inactive. The requested tri-state value and concrete sentence/G2P selections are
persisted as resume identity. The conversion summary shows the request; preflight and
persisted state show concrete sentence/G2P selections. Those selections are part of
resume identity.

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

Paragraph conversion retains one WAV per render unit: an optional chapter-title unit and
the spoken paragraph units that follow it. The workspace fixes the conversion unit,
selected chapters, and a schema-2 canonical generation identity; use `--fresh` to change
them. `--fresh` controls workspace lifecycle and is not part of generation identity.
Valid units are skipped on resume, and a complete paragraph workspace can rebuild a
missing final audiobook without ONNX initialization. See
`examples/paragraph_manifest.py` for inspection-only validation.

Progress is saved after every finalized WAV unit. Randomized paragraph preparation uses
a hidden persisted seed per chapter when no `--seed` value is supplied, making the
prepared descriptor identity stable across process restarts while keeping fresh
conversions independently randomized. `--seed 42` records and reuses the explicit seed
for every chapter. On resume, omitted audio-affecting settings come from the saved
identity rather than current configuration defaults; an explicit changed setting is
reported by field and rejected. A strong resume mismatch is an actionable error; use
`--fresh` for an intentional restart. Verifiable schema-6 state is migrated to schema 7
on its next atomic save. Unverifiable legacy state and its completed artifacts are
preserved rather than silently replaced.

Name extraction additionally accepts `--spacy-model`, `--spacy-model-size`, and
`--language`; its output metadata records the concrete NER-capable package. Existing
configurations without these keys migrate to automatic selection.

### SSMD 0.8.6 policies

The following keys configure SSMD rendering. Persistent configuration is lower
precedence than a document header; explicit CLI/API values are higher precedence. Do not
use persistent `pause_sentence` or `pause_paragraph` values as SSMD header overrides.

`ssmd_parse_header` (boolean, default `true`) : Parse an exact leading `---` block. Set
false only for literal header text.

`ssmd_unknown_header` (`warn`, `error`, or `ignore`) : Policy for unknown header keys.

`ssmd_missing_voice` (`error` or `use-default`) : Policy for logical voice references
that cannot be resolved.

`ssmd_validate_profile` and `ssmd_emphasis_mode` : Validate Kokoro-supported constructs
and choose the advanced `plain` (default), `approximate`, `warn`, or `error` policy.
Plain emphasis is spoken normally without automatic gain; explicit SSMD prosody remains
active. Normal audible strength should use `--emphasis-level`.

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
3. `emphasis_level` controls friendly gain-only audible strength while
   `ssmd_emphasis_mode` remains the advanced policy setting.

`emphasis_level` accepts `null`, `0` (Off), `1` (Light), `2` (Normal), and `3` (Strong).
The default is `null`, which falls back to the legacy `ssmd_emphasis_mode` value and
therefore remains audible-off with the normal `plain` default. Level 2 is equivalent to
the legacy flag. `ssmd_emphasis_mode` accepts `plain`, `approximate`, `warn`, and
`error`; the latter two remain advanced policies because they cannot be represented by a
numeric strength. If both keys are configured, equivalent `plain`/level-0 or
`approximate`/level-2 settings are accepted, while a strict `warn`/`error` policy
conflicts with a level.

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
ttsforge config --set emphasis_level 2
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

`tts.voice` : Optional default TTS voice. When `None`, PyKokoro selects the profile
default for the document language from metadata.

- Type: string or null
- Default: `None`
- Example: `ttsforge config set tts.voice am_adam`

`tts.language` : Canonical BCP-47 document language, or `auto`.

- Type: string
- Default: `auto`
- Examples: `de`, `en-us`, `fr-fr`

`tts.speed` : Default speech speed multiplier.

- Type: float
- Default: `1.0`
- Range: `0.5` to `2.0`

### Output Settings

`audio.format` : Default output audio format.

- Type: string
- Default: `m4b`
- Choices: `wav`, `mp3`, `flac`, `opus`, `m4b`

### Processing Settings

`runtime.provider` : ONNX Runtime execution provider used for synthesis. Use `auto`,
`cpu`, `cuda`, `openvino`, `directml`/`dml`, `coreml`, `nnapi`, `xnnpack`, or a full
`*ExecutionProvider` name.

- Type: string
- Default: `cpu`
- Example: `ttsforge config set runtime.provider nnapi`

`model.quality` : Optional ONNX model quality/quantization. When `None`, PyKokoro
resolves the profile-supported default quality.

- Type: string or null
- Default: `None`
- Choices: `fp32`, `fp16`, `q8`, `q8f16`, `q4`, `q4f16`, `uint8`, `uint8f16`
- Example: `ttsforge config set model.quality fp16`

`model.source` : Optional model source. Omit it for PyKokoro metadata-driven selection.

- Type: string or null
- Default: `None`
- Choices: `github`, `huggingface`

`model.id` : Optional model profile variant. Omit it for automatic selection.

- Type: string or null
- Default: `None`
- Examples: `v1.0` and `v1.2-de-martin` (voice `martin`)

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

TTSForge does not automatically detect language changes. Mark each change explicitly in
SSMD, for example `[Welt]{lang="de"}`. The document language is still required for the
overall pipeline and model selection.

`use_mixed_language` is a deprecated compatibility setting. `true` is rejected with
migration guidance, and `false` is accepted only as a transitional value.
`mixed_language_primary`, `mixed_language_allowed`, and `mixed_language_confidence` are
obsolete and non-default values are rejected.

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
* - `tts.language`
  - string
  - `auto`
  - Canonical BCP-47 document language
* - `tts.speed`
  - float
  - `1.0`
  - Speech speed multiplier
* - `audio.format`
  - string
  - `m4b`
  - Output audio format
* - `runtime.provider`
  - string
  - `cpu`
  - ONNX Runtime provider alias or full name
* - `model.quality`
  - string or null
  - automatic
  - Model quality/quantization
* - `model.id`
  - string or null
  - automatic
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
  - boolean (deprecated compatibility setting)
  - `false`
  - `true` is rejected; use explicit SSMD `lang` spans
* - `mixed_language_primary`
  - deprecated/obsolete
  - —
  - Not used for automatic detection
* - `mixed_language_allowed`
  - deprecated/obsolete
  - —
  - Not used for automatic detection
* - `mixed_language_confidence`
  - deprecated/obsolete
  - —
  - Not used for automatic detection
```

## Example Configuration File

Here's an example `config.json` with custom settings:

```json
{
  "default_voice": "am_adam",
  "default_language": "a",
  "default_speed": 1.1,
  "default_format": "m4b",
  "onnx_provider": "auto",
  "model_quality": null,
  "model_source": null,
  "model_variant": null,
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

Provider resolution uses explicit `--provider`, then `runtime.provider`, then the CPU
default. PyKokoro may apply its documented `ONNX_PROVIDER` environment override during
runtime provider resolution.

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

TTSForge requires PyKokoro `>=0.9.4,<0.10`, uses compact segment results, and releases
completed chapter audio before the next chapter synthesis. Whole-chapter synthesis
remains buffered and streaming is future work.

## Model source status

Set `model.source` to `github` when using the GitHub asset set. `ttsforge config show`
uses PyKokoro's source/variant/quality-aware asset paths and reports missing assets. If
the configured set is incomplete but the alternate supported source is complete, the
command reports that alternate and gives an activation command without silently
switching sources.

On Termux/Android, a typical setup is:

```bash
ttsforge config --set model_source github --set model_variant v1.0 \
   --set model_quality fp32 --set onnx_provider nnapi
ttsforge config --show
ttsforge download
ttsforge sample "Termux provider test" --provider nnapi
```

With the required patched PyKokoro release, GitHub `v1.0` uses the embedded standard
vocabulary and does not download Hugging Face `config.json`. The configured source is
never switched automatically. Provider availability depends on the installed Android
ONNX Runtime build, so use another available provider if NNAPI is not exposed.
