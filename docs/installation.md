# Installation

TTSForge is an audiobook frontend for Readio. It delegates rendering to Readio's public
workflow API and does not bundle a speech engine.

## Requirements

TTSForge requires Readio `>=0.6.9,<0.7`, which provides the workflow gateway,
render-intent helpers, source inspection, engine discovery, and normalized engine-model
inventory and lifecycle APIs used by the CLI and Studio. A Readio source checkout is not
required for a normal installation.

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

## Packaged audiobook Skill

The distribution includes the TTSForge audiobook Skill and its CLI, project, narration,
and QC references under `ttsforge/skills/ttsforge/`. Access the installed resource with
`importlib.resources`; the Skill routes audiobook production to TTSForge and generic
speech or document rendering to Readio.

## Optional Studio server

The HTTP API is optional and does not install a frontend. Install its dependencies with:

```bash
python -m pip install "ttsforge[server]"
```

The `studio` extra installs the HTTP server dependencies and Readio's optional spaCy
support. It does not install a synthesis-engine integration. Install a supported Readio
engine integration separately when synthesis is needed. See the
[server guide](server.md) for startup, token, and origin policy options, and the
[Studio API reference](studio-api.md) for the HTTP contract.

Set `TTSFORGE_TOKEN` and start the local server with an ephemeral port:

```bash
export TTSFORGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
ttsforge serve --port 0
```

The default host is loopback. The launcher prints one JSON readiness record to stdout
with the selected port; server diagnostics go to stderr.

## Development installation

For local development, check out TTSForge beside a Readio checkout that provides the
required `>=0.6.9,<0.7` API, then install both editable:

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
