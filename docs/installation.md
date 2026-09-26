# Installation

TTSForge is an audiobook frontend for Readio. Readio supplies persistent projects,
synthesis engines, and export services; install engine integrations as Readio extras
rather than installing a TTSForge-specific backend.

## Compatibility gate

TTSForge requires Readio's public application API v1, including persistent projects and
the audiobook-specific M4B export service. The published Readio `v0.2.4` predates these
APIs. A compatible release is not yet available on PyPI.

The project intentionally has no guessed Readio version floor. A compatible published
pin, clean PyPI installation, `pip check`, and installed-package CLI smoke test remain
blocked until the required API is actually released. Do not treat `pip install ttsforge`
from the current PyPI dependency set as a verified installation.

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

## Later PyPI installation

Once a compatible Readio release is published and the release gate is cleared, the
intended user installation is:

```bash
python -m pip install ttsforge
```

Then install a Readio engine extra if needed, using the package extra documented by that
compatible Readio release. The exact minimum Readio version will be recorded here only
after it exists and has been tested; it is deliberately unspecified for now.

## Supported Python

TTSForge and Readio support Python 3.10 or newer. Engine runtime availability and
audio-format encoders vary by platform; use `ttsforge doctor` and `ttsforge formats` for
the active environment rather than assuming a provider or format is installed.
