# Installation

TTSForge is an audiobook frontend for Readio. It delegates rendering to Readio's public
workflow API and does not bundle a speech engine.

## Requirements

TTSForge requires Readio `>=0.6.7,<0.7`, which provides the workflow gateway,
render-intent helpers, source inspection, and engine discovery used by this CLI. A
Readio source checkout is not required for a normal installation.

TTSForge supports Python 3.10 or newer. Engine runtimes and audio tooling depend on the
selected Readio integration and platform.

## Install from PyPI

```bash
python -m pip install ttsforge
```

The base TTSForge installation is provider-neutral. Install a Readio engine integration
separately when speech synthesis is needed. Consult the
[Readio installation guide](https://github.com/buchwandler/readio/blob/main/docs/index.md)
for the supported integrations and their platform requirements. TTSForge does not guess
or provide a parallel set of engine extras.

## Development installation

For local development, check out TTSForge beside a Readio checkout that provides the
required `>=0.6.7,<0.7` API, then install both editable:

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ../readio -e ".[dev]"
```

The local Readio checkout must satisfy the declared API version floor. Installing an
older checkout editable does not provide the required contract.

## Verify the environment

```bash
ttsforge --help
ttsforge engines
ttsforge targets --engine ENGINE
```

`engines` reports the engines exposed by Readio. `targets` lists the runnable targets
for one engine. Availability depends on the installed Readio integrations and local
environment.

For a real workflow, inspect and convert an EPUB:

```bash
ttsforge list novel.epub
ttsforge convert novel.epub
```

## Tests and lint

From the TTSForge checkout with its development dependencies installed:

```bash
python -m pytest -q
ruff check .
mypy ttsforge
```
