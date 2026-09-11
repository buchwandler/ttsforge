# TTSForge 0.4 migration guide

TTSForge 0.4 is a breaking release. Existing v0.3 command lines, configuration files,
and resumable workspaces are not treated as a compatible public contract.

## Dependencies and providers

The core package is provider-neutral. Install exactly one provider extra, such as
`ttsforge[cpu]` or `ttsforge[gpu]`, in a fresh environment. Do not combine provider
extras. The supported backend floors are PyKokoro `>=0.9.4,<0.10`, kokorog2p
`>=0.9.5,<1.0`, SSMD `>=0.8.7,<0.9`, and phrasplit `>=0.3.7,<0.4`.

## Configuration

Configuration is migrated to schema 2 with nested sections. Use commands such as:

```text
ttsforge config set runtime.provider cpu
ttsforge config set tts.language en-us
ttsforge config set model.quality q8
```

Legacy one-letter language values are migrated to canonical BCP-47 values. New
configuration should use values such as `en-us`, `en-gb`, `de`, `es`, `fr-fr`, `it`,
`ja`, `pt-br`, and `zh`. Legacy GPU, mixed-language, and flat provider settings are not
part of the v0.4 public API.

## Commands and options

Use `ttsforge doctor` to inspect package versions, providers, model assets,
configuration, and cache paths. Use `convert --model`, `--quality`, and `--source` for
explicit model selection. The old GPU switches, one-letter language options,
short-sentence command, and SSMD emphasis switches have been removed.

Automatic mixed-language detection is removed. Mark language changes explicitly in SSMD:

```ssmd
[Bonjour le monde]{lang="fr-fr"}
```

## Voices and models

Voice and model lists come from PyKokoro metadata discovery. Do not rely on the removed
static TTSForge voice inventory or voice-name prefixes. `ttsforge voices` reports the
discovered model, language, and default selection.

## Resume and audio state

Use `--fresh` when a saved workspace is rejected. v0.4 state records the effective
conversion plan, prepared-unit hashes, and runtime sample rates. Runtime package
diagnostics are kept separate from semantic resume identity. Existing artifacts are
preserved when migration cannot verify them, but they are not reused unsafely.

## Compatibility statement

There is no compatibility promise for removed v0.3 CLI options, flat configuration keys,
legacy language codes in new API calls, static voice inventories, mixed-language
auto-detection, or v0.3 renderer state. Recreate configuration with
`ttsforge config show` and start an explicit fresh conversion when required.
