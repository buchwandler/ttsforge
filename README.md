[![PyPI - Version](https://img.shields.io/pypi/v/ttsforge)](https://pypi.org/project/ttsforge/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ttsforge)
![PyPI - Downloads](https://img.shields.io/pypi/dm/ttsforge)
[![codecov](https://codecov.io/gh/buchwandler/ttsforge/graph/badge.svg?token=iCHXwbjAXG)](https://codecov.io/gh/buchwandler/ttsforge)

# TTSForge

**TTSForge is an audiobook-oriented command-line frontend for Readio.** It turns EPUBs
into M4B audiobooks while Readio owns workflow planning, synthesis, composition,
progress, and export.

TTSForge requires `readio>=0.6.2,<0.7`. Its base dependencies are provider-neutral.
Install and configure a Readio engine integration separately when you want to synthesize
speech; use Readio's installation documentation for the integrations supported by your
platform.

## What it does

- Inspect EPUB metadata and chapters without creating a project.
- Guide audiobook setup and persist it for retries.
- Render and export an M4B through Readio's public workflow API.
- Inspect workflow status and discover Readio engines, targets, and voices.
- Keep existing TTSForge/Readio 0.4 project data untouched instead of attempting an
  automatic migration.

## Quick start

Install TTSForge, then inspect and convert a book:

```bash
python -m pip install ttsforge
ttsforge list novel.epub
ttsforge convert novel.epub
```

In an interactive terminal, conversion guides you through missing chapter and voice
setup, shows a read-only preflight, then asks before rendering. Setup is saved before
rendering, so a failed attempt can be retried with the saved choices.

For automation, specify the chapter selection and any setup values you want to pin:

```bash
ttsforge convert novel.epub --chapters 1-5 --engine ENGINE --target TARGET --voice VOICE --non-interactive
```

`--json` is also prompt-free. See [Quick start](docs/quickstart.md) and the
[CLI reference](docs/cli.md) for details.

## Projects and output

For `novel.epub`, the default project is `novel.ttsforge/` beside the source, and the
default output is `novel.m4b`. The project contains Readio's saved render intent and
narrator profile plus the persistent `book.ssmd-bundle/` workspace. Use `--project` to
choose another location or `--fresh` to start in a separate project directory. See
[Projects and outputs](docs/projects.md).

Output replacement and stage rebuild are separate explicit controls: use
`--replace-output` to authorize replacing an existing M4B, and `--rebuild-from STAGE` to
ask Readio to rebuild from a selected workflow stage.

## Discover engines and voices

```bash
ttsforge engines
ttsforge targets --engine ENGINE --language en-us
ttsforge voices --engine ENGINE --target TARGET --language en-us
```

Catalog contents and runtime availability depend on installed Readio integrations and
local configuration.

## Migration from TTSForge 0.4

TTSForge 0.5 uses Readio's 0.6.1 workflow-gateway API and a new `.ttsforge/` project
layout. Existing TTSForge or Readio 0.4 workspaces cannot be resumed by this version.
They are rejected without automatic migration or mutation. Keep them as-is and start a
separate project with `--fresh` or an explicit new `--project` path. See the
[migration guide](docs/migration-readio.md).

The former backend-specific commands and configuration interface are not part of the
audiobook CLI. TTSForge's supported interface is the command line; Python integrations
should use Readio's public `readio.api` directly. See the
[API boundary](docs/api/index.md).

## Documentation

- [Installation](docs/installation.md)
- [Quick start](docs/quickstart.md)
- [CLI reference](docs/cli.md)
- [Project lifecycle](docs/projects.md)
- [Saved setup](docs/configuration.md)
- [Engine and voice discovery](docs/voices.md)
- [Migration guide](docs/migration-readio.md)
- [Python API boundary](docs/api/index.md)
- [Examples](examples/README.md)
