# SSMD 0.8

ttsforge treats SSMD 0.8 as a document format, not as decorated plain text. Generated,
edited, and direct `.ssmd` documents are validated with the public `ssmd` APIs and the
pykokoro Kokoro profile before synthesis. Header metadata is never sent to speech.

## Basic workflow

```bash
ttsforge convert book.epub --generate-ssmd
# edit the .ssmd files in the chapter directory
ttsforge ssmd validate .book_chapters/chapter_001.ssmd --strict
ttsforge convert book.epub
```

The generated files use truncated SHA-256 content hashes. An edited invalid file stops
its chapter and is never silently replaced; an existing audio file is retained until a
valid synthesis and its sidecars succeed.

## Portable document example

```text
---
title: Review podcast
voice_bindings:
  kokoro:
    moderator: af_sarah
    positive: af_bella
pause_defaults:
  enabled: true
  sentence: 250ms
  paragraph: 700ms
  voice_change: 350ms
---
<div voice="moderator">
Welcome to the review.
</div>

<div voice="positive">
The new format is portable. @approved
</div>
```

`title` is metadata and is not spoken. Logical roles resolve through
`voice_bindings.kokoro`. Explicit `...100ms` breaks beat implicit defaults; simultaneous
implicit paragraph and voice changes use the longest duration. `@approved` is retained
as a marker event and exported to marker sidecars.

## Syntax

Canonical inline annotations use `[text]{key="value"}`:

```text
[Hermione]{ph="hɝmˈIni"}
[Bonjour]{lang="fr-FR"}
[100]{as="cardinal"}
[XML]{sub="extensible markup language"}
[fast words]{rate="fast" volume="loud"}
...c ...s ...p ...250ms
```

Moderate, strong, reduced, and none emphasis are parsed. EPUB processing has three
layers: epub2text performs semantic extraction, TTSForge preserves the resulting
controlled Markdown in SSMD, and the SSMD emphasis policy controls audible rendering.
Emphasis is spoken plainly by default: it does not add automatic gain, rate, or pitch
changes, and its metadata is preserved. Use `--emphasis-level 1`, `2`, or `3` for Light,
Normal, or Strong gain-only audible emphasis; level 2 is the current legacy behavior.
Use `--ssmd-emphasis approximate` or the deprecated `--enable-ssmd-emphasis` only as
advanced/compatibility controls, and use `warn` or `error` for stricter behavior.
Explicit document prosody such as `[fast words]{rate="fast"}` remains active in plain
mode. Language, voice, prosody, say-as, substitution, phoneme, break, mark, paragraph,
heading, and supported audio attributes are passed to the renderer.

### Automatic written-to-spoken preparation vs explicit say-as

Ordinary unannotated text flows through the PyKokoro/kokorog2p 0.8.x preparation
boundary. For supported languages and forms, kokorog2p may prepare dates, times,
measurements, currency, ordinals, and abbreviations as speakable text before G2P.
TTSForge does not rewrite source SSMD into automatic annotations or duplicate that
upstream normalization.

Explicit author intent remains separate: annotations such as `[100]{as="cardinal"}` and
other SSMD `say-as` values are document semantics and remain active overrides. The
renderer applies explicit SSMD intent according to its upstream contract rather than
treating every ordinary source form as an author annotation.

## Direct SSMD input

An exact leading `---` line opens front matter and a matching `---` or `...` closes it.
A `----` line is ordinary body text. Use `--no-ssmd-header` when an exact leading block
is literal spoken text.

For a direct `.ssmd` input, title precedence is explicit `--title` or API title, then
header `title`, then the filename stem. The complete source, including front matter, is
preserved for rendering.

## Policies and diagnostics

Useful conversion options include:

```bash
--ssmd-unknown-header warn|error|ignore
--ssmd-missing-voice error|use-default
--emphasis-level 0|1|2|3
--ssmd-emphasis plain|approximate|warn|error
--enable-ssmd-emphasis
--detect-emphasis
--ssmd-voice narrator=af_sarah
--pause-voice-change 0.35
--ssmd-audio-root ./audio
--ssmd-remote-audio
--ssmd-fail-on-warning
```

Diagnostics have stable codes and source locations. Inspect without loading ONNX using
`ttsforge ssmd inspect FILE` or `ttsforge ssmd inspect FILE --json`. Validate with
`ttsforge ssmd validate FILE`; `--strict` promotes warnings to failures.

### Prosody method selection

`prosody_method` is independent of `detect_emphasis` and `ssmd_emphasis_mode`. It
chooses the AudioSig algorithm used when an SSMD segment contains `rate` or `pitch`
metadata. `wsola` is the default speech-oriented audiobook choice; `esola` is an
experimental speech-oriented alternative; `psola` is accepted as an alias for AudioSig's
canonical `td_psola`; and `phase_vocoder` is a generic reference/fallback path. Keep
fallbacks enabled unless testing strict behavior.

The current `emphasis_level` profile changes gain only. Selecting ESOLA, WSOLA, or PSOLA
does not change those fixed emphasis gains; the selected prosody method is used for
explicit SSMD rate and pitch annotations. `plain` disables emphasis approximation but
does not disable explicit rate, pitch, or volume annotations. Omit `--emphasis-level`
when resuming so the saved renderer policy remains authoritative.

Audio annotations use a document-relative local resolver with byte and duration limits.
Remote audio is disabled by default; when enabled, only bounded HTTPS sources are
accepted. Unresolved audio uses SSMD fallback text and emits an `ssmd.audio_fallback` or
`ssmd.audio_unresolved` diagnostic. Audio files are decoded and downmixed to mono before
pykokoro applies SSMD transformations. TTSForge retains source resolution, security
limits, SoundFile decoding, and output orchestration; AudioSig supplies the reusable
array downmix, while PyKokoro remains responsible for SSMD speed, gain, and resampling.

## Intentional Kokoro limitations

- SSMD voice language, gender, and variant hints are preserved as metadata but do not
  select a Kokoro voice.
- SSMD extensions are rejected by default for the Kokoro profile.
- Emphasis is spoken plainly by default. EPUB Markdown extraction and SSMD rendering are
  independent; use `--epub-content-mode plain` only for legacy comparison,
  `--no-detect-emphasis` to unwrap inline emphasis, and `--emphasis-level` for audible
  strength.
- Remote audio is opt-in and bounded.
- Marks are exported as `chapter_NNN.markers.json` and an aggregate output sidecar
  rather than embedded in every audiobook container.

## See also

- {doc}`quickstart`
- {doc}`cli`
- {doc}`configuration`
