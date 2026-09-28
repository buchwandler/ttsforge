# Installation

TTSForge is an audiobook frontend for Readio. Readio supplies persistent projects,
synthesis engines, and export services; install engine integrations as Readio extras
rather than installing a TTSForge-specific backend.

## Requirements

TTSForge requires Readio `>=0.3.3`, which provides the public audiobook project,
expanded synthesis-resolution, and M4B export APIs used by the CLI. This is the declared
dependency floor; a local Readio checkout is not required for a normal installation.

## Development installation

For local development, check out TTSForge beside the Readio repository and install both
editable. For Kokoro-backed synthesis, include Readio's `kokoro` extra:

```bash
# From a directory where both repositories will live
git clone https://github.com/buchwandler/readio.git
git clone https://github.com/buchwandler/ttsforge.git
cd ttsforge

python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e "../readio[kokoro]" -e ".[dev]"
```

Readio also provides optional `piper` and `pocket` engine extras where those engines are
supported. They are installed and diagnosed through Readio, not through
TTSForge-specific backend extras. Consult the
[Readio installation guide](https://github.com/buchwandler/readio/blob/main/docs/index.md)
for engine requirements and platform-specific setup.

To install only TTSForge's development and test tools against the local Readio checkout,
omit the engine extra:

```bash
python -m pip install -e ../readio -e ".[dev]"
```

## Verify the environment

```bash
ttsforge --help
ttsforge doctor
ttsforge engines
ttsforge formats
```

`doctor` reports Readio's detected runtimes, dependencies, paths, and available formats.
Install an engine extra if no synthesis engine is runnable. For a real workflow, first
inspect an EPUB and then create a project:

```bash
ttsforge list novel.epub
ttsforge convert novel.epub
```

## Install from PyPI

Install TTSForge with its declared Readio dependency floor:

```bash
python -m pip install ttsforge
# Optional example: install Readio's Kokoro engine extra
python -m pip install "readio[kokoro]"
```

Then install a Readio engine extra if needed, using the package extra documented for
that engine and platform. `ttsforge doctor` and `ttsforge formats` report the active
environment.

## Supported Python

TTSForge and Readio support Python 3.10 or newer. Engine runtime availability and
audio-format encoders vary by platform; use `ttsforge doctor` and `ttsforge formats` for
the active environment rather than assuming a provider or format is installed.
