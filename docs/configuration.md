# Saved audiobook setup

TTSForge 0.5 does not provide a separate global configuration command or duplicate
Readio's settings schema. Setup for a book is persisted through Readio's public intent
and profile APIs in that book's TTSForge project.

## Project setup files

A default project contains:

```text
novel.ttsforge/
├── render.readio.toml
├── narrator.renderprofile.toml
└── book.ssmd-bundle/
```

The render intent stores the source, chapter selection, persistent workspace, output,
and render choices. The narrator profile stores the voice binding and engine-specific
options. Readio owns these file formats and validates their contents.

## Precedence and retries

For each setup value, explicit CLI options take precedence over saved project values.
Saved values take precedence over source-derived values and Readio defaults. Interactive
prompts supply any still-missing choices. A successfully resolved intent and profile are
saved before preflight confirmation and rendering, so a failed render can be retried
with the same setup.

Changing language, engine, or target invalidates dependent selections as needed. Readio
remains responsible for validating the final profile and deciding which workflow stages
can be reused.

Use `ttsforge info SOURCE --project PROJECT` to inspect saved setup. Use
`ttsforge status PROJECT` to inspect the saved workflow. Pass setup options directly to
`convert`; see `ttsforge convert --help` and the [CLI reference](cli.md).

## Engine configuration

Engine installation, runtime configuration, and provider-specific options are owned by
Readio and the selected integration. Discover installed engines and runnable targets
with:

```bash
ttsforge engines
ttsforge targets --engine ENGINE
```

For configuration supported by a specific integration, follow the current
[Readio documentation](https://github.com/buchwandler/readio/blob/main/docs/index.md).
TTSForge does not translate former TTSForge-specific configuration files automatically.
