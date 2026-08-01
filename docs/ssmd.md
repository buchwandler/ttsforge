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

Moderate, strong, reduced, and none emphasis are parsed. Emphasis is spoken plainly by
default: it does not add automatic volume, rate, or pitch changes, and its metadata is
preserved. Use `--ssmd-emphasis approximate` or the convenience flag
`--enable-ssmd-emphasis` to opt into segment-level volume/rate approximation; use `warn`
or `error` for stricter behavior. Explicit document prosody such as
`[fast words]{rate="fast"}` remains active in plain mode. Language, voice, prosody,
say-as, substitution, phoneme, break, mark, paragraph, heading, and supported audio
attributes are passed to the renderer.

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
experimental speech-oriented alternative; `psola` is accepted as an alias for
AudioSig's canonical `td_psola`; and `phase_vocoder` is a generic reference/fallback
path. Keep fallbacks enabled unless testing strict behavior.

The current `ssmd_emphasis_mode=approximate` profile changes gain only. Selecting ESOLA,
WSOLA, or PSOLA does not change those fixed emphasis gains; the selected prosody method
is used for explicit SSMD rate and pitch annotations. `plain` disables emphasis
approximation but does not disable explicit rate, pitch, or volume annotations.

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
- Emphasis is spoken plainly by default. EPUB styling detection and SSMD rendering are
  independent; use `--detect-emphasis` to extract italic/bold HTML and
  `--enable-ssmd-emphasis` to opt into approximation.
- Remote audio is opt-in and bounded.
- Marks are exported as `chapter_NNN.markers.json` and an aggregate output sidecar
  rather than embedded in every audiobook container.

## See also

- {doc}`quickstart`
- {doc}`cli`
- {doc}`configuration`
