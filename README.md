[![PyPI - Version](https://img.shields.io/pypi/v/ttsforge)](https://pypi.org/project/ttsforge/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ttsforge)
![PyPI - Downloads](https://img.shields.io/pypi/dm/ttsforge)
[![codecov](https://codecov.io/gh/buchwandler/ttsforge/graph/badge.svg?token=iCHXwbjAXG)](https://codecov.io/gh/buchwandler/ttsforge)

# TTSForge

**TTSForge is an audiobook-focused command-line frontend for
[Readio](https://github.com/buchwandler/readio).** It gives EPUB audiobook workflows a
concise CLI; Readio owns the persistent project, speech planning, synthesis,
composition, progress, and export.

TTSForge does not implement or bundle a parallel speech engine. Use Readio's public
application API and its engine integrations; TTSForge maps audiobook choices to those
services.

TTSForge requires Readio `>=0.3.3`, which provides the public audiobook API and the
expanded synthesis-resolution contract used by guided setup. Install TTSForge normally,
then add a Readio engine integration as needed; see [Installation](docs/installation.md)
for setup and development instructions.

## What it does

- Inspect EPUB metadata and chapter structure.
- Create or reuse a persistent Readio project for an audiobook.
- Select chapters, preview speech, plan a project, and check authoritative project
  status.
- Export M4B audiobooks or formats supported by Readio's generic export service.
- Discover voices, models, engines, and formats through Readio.
- Use Readio's configuration and SSMD authoring/checking services.

## Quick start

Install TTSForge and a Readio engine integration using the Readio extra for your
platform; see [Installation](docs/installation.md) for details. Then run:

```bash
ttsforge convert novel.epub
```

In an interactive terminal, a new project shows the detected chapters and prompts for a
selection, then guides you through any synthesis settings you have not supplied.
Readio's model and voice catalogs are displayed for selection, and the resolved
audiobook settings appear before confirmation. Reusing a project uses its saved chapter
scope. Build progress updates live by chapter.

For automation, specify `--chapters` and pass any desired synthesis options explicitly.
`--yes` skips only final confirmation; `--non-interactive` and `--json` remain
prompt-free. Without an explicit chapter selection, non-interactive runs include all
chapters. Useful follow-up commands:

```bash
ttsforge list novel.epub
ttsforge convert novel.epub --chapters 5-17 --fresh
ttsforge status novel.readio
ttsforge preview novel.epub
ttsforge voices --language en-us
ttsforge doctor
```

By default, the project is `novel.readio` beside `novel.epub`; the default output is
`novel.m4b`. Re-running the command reuses that Readio project and its persistent
chapter selection. See [Projects and outputs](docs/projects.md) for reuse, fresh
projects, and legacy workspaces.

## Readio engines and configuration

Engine availability and voices depend on Readio's installed optional engine integrations
and local configuration. Discover the active catalog and diagnose the environment with:

```bash
ttsforge engines
ttsforge models
ttsforge voices --engine kokoro
ttsforge formats
ttsforge doctor
```

TTSForge reads and updates Readio configuration rather than keeping a separate TTSForge
backend configuration:

```bash
ttsforge config show
ttsforge config set reader.voice af_heart
ttsforge config set reader.speed 1.1
```

## Migration notes

This is a breaking change from the former TTSForge-owned Kokoro conversion pipeline. Old
renderer workspaces are not Readio projects and cannot be resumed by this frontend. They
are left untouched; use `--fresh` or an explicit new `--project` path to start
separately. Backend-specific commands such as `read`, `sample`, `demo`, `download`, and
`phonemes` are no longer part of TTSForge. See the
[migration guide](docs/migration-readio.md) before switching an existing setup.

## Documentation

- [Installation](docs/installation.md)
- [Quick start](docs/quickstart.md)
- [CLI reference](docs/cli.md)
- [Project and output lifecycle](docs/projects.md)
- [Readio configuration](docs/configuration.md)
- [Voices and discovery](docs/voices.md)
- [SSMD tools](docs/ssmd.md)
- [Migration guide](docs/migration-readio.md)
- [Python API boundary](docs/api/index.md)
- [Command-line examples](examples/README.md)

Implementation details and the public service contracts are documented in
[Readio's API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md) and
[project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md).
