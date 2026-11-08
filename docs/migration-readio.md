# Migrating to TTSForge 0.5 and Readio 0.6.1

TTSForge 0.5 is a breaking migration from the Readio 0.4 project/facade API to Readio's
workflow-gateway API. It also replaces the former TTSForge renderer workspace with an
audiobook project directory. TTSForge requires Readio `>=0.6.1,<0.7`.

## No automatic project migration

TTSForge 0.4 workspaces and Readio 0.4 projects are not compatible with this workflow.
TTSForge rejects legacy project paths and leaves their contents unchanged. It does not
migrate, rename, copy, or delete old project data, render artifacts, SSMD files, or
resume metadata.

Keep the old directory as-is and start a separate project from the original EPUB:

```bash
ttsforge convert novel.epub --fresh
# Or choose an explicit new directory:
ttsforge convert novel.epub --project ./projects/novel-v05
```

The default project for `novel.epub` is now `novel.ttsforge/`. Its Readio-managed files
are `render.readio.toml`, `narrator.renderprofile.toml`, and `book.ssmd-bundle/`. The
default final output remains `novel.m4b`. See [Projects and outputs](projects.md).

Do not pass an old project directory to a Readio migration command as a way to make it
compatible. No TTSForge 0.4-to-0.5 project importer is provided.

## CLI changes

The v0.5 CLI focuses on EPUB audiobook conversion and workflow inspection:

```bash
ttsforge list novel.epub
ttsforge info novel.epub
ttsforge convert novel.epub
ttsforge status novel.ttsforge
ttsforge engines
ttsforge targets --engine ENGINE
ttsforge voices --engine ENGINE
```

The former backend-specific `read`, `sample`, `demo`, `download`, and `phonemes`
commands are removed. Earlier project/configuration commands such as `preview`, `plan`,
`config`, `models`, `formats`, `doctor`, and `ssmd` are not part of the v0.5 audiobook
workflow. Use Readio's public API and its engine integrations for capabilities outside
this CLI.

`convert` uses `--engine`, `--target`, and `--voice` for setup. Output is M4B.
`--replace-output` authorizes final-output replacement; `--rebuild-from STAGE`
independently requests a workflow rebuild. The old general-purpose `--force` flag is not
retained.

## Setup and configuration

TTSForge no longer provides a separate global backend-configuration command. Per-book
setup is stored through Readio's public render-intent and profile APIs in the project
directory. Explicit command-line values take precedence over saved values. Saved setup
is reused for retries; old TTSForge-specific settings are not automatically translated.

The base TTSForge package remains provider-neutral. Install and configure a supported
Readio integration separately, following Readio's current installation and configuration
documentation.

## Python integrations

TTSForge's supported product interface is its CLI; the internal adapter is not a stable
Python API. Python integrations should use Readio's public `readio.api` workflow gateway
directly. See the [API boundary](api/index.md) and
[Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md).
