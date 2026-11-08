# Engines, targets, and voices

TTSForge does not ship a fixed voice list or a provider-specific engine implementation.
Engine, runnable target, and voice information comes from Readio's public discovery API
and depends on installed integrations and local configuration.

## Discover engines and targets

```bash
ttsforge engines
ttsforge targets --engine ENGINE
ttsforge targets --engine ENGINE --language en-us
```

`engines` lists engines exposed by Readio. `targets` requires an engine and lists
runnable targets for it. Add `--offline` to avoid online discovery or `--refresh` to
refresh discovery results when supported. Use `--json` for structured output.

## List voices

```bash
ttsforge voices
ttsforge voices --engine ENGINE --target TARGET --language en-us
```

The engine, target, and language filters are optional. Voice identifiers and metadata
are supplied by Readio; use the identifier shown for the selected target rather than
assuming another engine's naming convention.

## Use a discovered voice

Pass the discovered engine, target, and voice to conversion:

```bash
ttsforge convert novel.epub --engine ENGINE --target TARGET --voice VOICE
```

On an interactive terminal, `convert` uses Readio discovery to guide missing choices.
Explicit options pin their matching setup values. Readio validates the completed profile
and determines whether a target supports each option.

TTSForge does not expose a `models` command or maintain a second provider-specific
catalog. See the [CLI reference](cli.md) for discovery options and the
[Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md) for the
public discovery contract.
