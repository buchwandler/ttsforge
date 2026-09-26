# Voices and discovery

TTSForge does not ship a fixed voice list. The available voices, selectors, models, and
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

A voice row may include a selector, language/locale, model, engine, status, and whether
the runtime is available. Select a voice value that Readio reports for the engine/model
you plan to use; do not assume legacy Kokoro IDs or language-prefix conventions apply to
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

Pass the reported selector or voice ID to the audiobook command:

```bash
ttsforge convert novel.epub --engine kokoro --voice af_heart
ttsforge preview novel.epub --engine kokoro --voice af_heart
```

Voice and model details are engine-specific. TTSForge does not implement voice blending,
maintain voice recommendations, or promise that a voice selector will be available for
every engine. See
[Readio's catalog documentation](https://github.com/buchwandler/readio/blob/main/docs/api.md#discovery-and-roles)
for the public discovery contract.
