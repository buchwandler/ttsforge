# Voices and discovery

TTSForge does not ship a fixed voice list. The available voices, references, models, and
runtime status come from Readio's discovery catalog and depend on the installed engine
integrations and selected model/profile.

## List voices

```bash
ttsforge voices
ttsforge voices --language en-us
ttsforge voices --engine kokoro
ttsforge voices --engine piper --model MODEL_ID
```

Filters include `--engine`, `--language`, `--model`, and `--gender`. Use `--offline` to
avoid network discovery and `--refresh` to refresh cached catalog data. `--json` returns
catalog items together with discovery information.

Human-readable output shows the canonical Readio voice ID (`VoiceInfo.id`) as the
primary name, with the semantic reference (`VoiceInfo.ref`) when available. If no
reference is available, the qualified voice ID can be used. also include
language/locale, model, engine, status, and runtime availability. Readio owns these
identities; do not assume legacy Kokoro IDs or language-prefix conventions apply to
every engine.

## Inspect models and engines

```bash
ttsforge models
ttsforge models --engine kokoro --language en-us
ttsforge engines
ttsforge doctor
```

`models` reports Readio model/synthesis targets and their status. `engines` lists
registered synthesis engines and their installed/runnable state. `doctor` includes
missing runtime dependencies and format availability.

## Use a discovered voice

For explicit `--voice` values, use the canonical voice ID or semantic reference reported
by Readio:

```bash
ttsforge convert novel.epub --engine kokoro --voice af_heart
ttsforge preview novel.epub --engine kokoro --voice af_heart
```

## Guided selection during conversion

`ttsforge convert` uses the same Readio discovery services interactively on a TTY. It
shows filtered choices as compact vertical lists. Enter a row number or exact
identifier. Voice entries show the canonical Readio voice ID first and the semantic
reference (`VoiceInfo.ref`) when available. Guided voice prompts accept a row number,
canonical voice ID, semantic reference, or qualified ID, then keep the selected row's
canonical ID. Catalogs are filtered by language and engine, and by model for voices.
Explicit `--model` and `--voice` options bypass matching prompts.

The engine-specific selection layouts are:

- Kokoro: model, then voice.
- Piper: choose a voice-bundle target. The matching voice has the same canonical
  identity and is selected automatically, without a duplicate prompt.
- Pocket: choose a model bundle, then a predefined named voice.

The completed selection is strictly resolved by Readio after catalog choices are
gathered. Pocket speed defaults to `1.0`. TTSForge does not expose Readio's Pocket
reference WAV `voice_file` option in `ttsforge convert`. Voice and model details remain
engine-specific. TTSForge does not implement voice blending or maintain voice
recommendations. See
[Readio's catalog documentation](https://github.com/buchwandler/readio/blob/main/docs/api.md#discovery-and-roles)
for the public discovery contract.

## Selection layouts

The interactive converter follows each engine's public Readio catalog semantics:

```text
Kokoro: model -> voice
Piper:    voice-bundle target
Pocket:   bundle -> predefined named voice
```

For Piper, the selected bundle is stored in Readio's neutral `model` request field, and
its matching canonical voice is selected automatically. Pocket stores the bundle in
`model` and the chosen predefined voice in `voice`.
