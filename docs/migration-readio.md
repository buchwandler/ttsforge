# Migrating to the Readio-backed TTSForge

This is a breaking architecture change. TTSForge is now an audiobook-focused frontend
for Readio's public API, not the owner of an EPUB-to-audio rendering pipeline. Readio
owns projects, planning, synthesis, composition, resumability, invalidation, and export.

## Compatibility and installation

TTSForge requires Readio `>=0.3.3`. Install the published package with:

```bash
python -m pip install ttsforge
```

Install a supported Readio engine extra if you need synthesis. A sibling Readio checkout
is needed only when developing against Readio source; see
[Installation](installation.md).

## What changes

| Former TTSForge behavior                        | Readio-backed workflow                                                            |
| ----------------------------------------------- | --------------------------------------------------------------------------------- |
| TTSForge-owned conversion and resume workspaces | Persistent Readio project, normally beside the EPUB as `<stem>.readio`            |
| TTSForge-rendered M4B and generic audio output  | Readio project build plus the appropriate Readio export service                   |
| TTSForge-local voice and engine lists           | Readio discovery: `voices`, `models`, `engines`, and `formats`                    |
| TTSForge backend configuration                  | Readio configuration through `ttsforge config`                                    |
| Local EPUB preview and processing internals     | `list`, `info`, `preview`, `plan`, `status`, and `convert` call Readio services   |
| TTSForge SSMD rendering/policy implementation   | Readio-backed `ssmd check`, `validate`, `analyze`, `roundtrip`, and `materialize` |

The project selection persists: `--chapters` chooses scope when the project is created.
Reusing a project keeps its saved chapter selection. Use a new `--project` path or
`--fresh` for another selection. See [Projects and outputs](projects.md).

## Existing workspaces are not migrated

Directories created by the former TTSForge renderer are not Readio projects. Their
resume state, intermediate audio, SSMD files, and artifacts are not imported,
interpreted, or deleted by this migration. TTSForge refuses to treat a colliding legacy
workspace as a Readio project.

Keep the old directory as a backup. Start a distinct project using either:

```bash
ttsforge convert novel.epub --fresh
# or choose an explicit path
ttsforge convert novel.epub --project novel-readio.readio
```

A fresh project does not resume old TTSForge progress. Existing final audio is left
alone unless an output replacement is explicitly requested.

## Configuration migration

TTSForge no longer reads a separate TTSForge backend config. Its `config` commands
inspect and update Readio's persisted settings:

```bash
ttsforge config path
ttsforge config show
ttsforge config set reader.voice af_heart
ttsforge config set reader.speed 1.1
ttsforge config languages
```

Old TTSForge settings are not automatically translated. Review them and reapply only
equivalent values using Readio's current configuration keys and semantics.
Engine-specific settings and optional engine installation are owned by Readio; consult
its
[configuration documentation](https://github.com/buchwandler/readio/blob/main/docs/index.md).

## Guided audiobook setup

In an interactive terminal, `convert` now guides you through synthesis values that were
not specified on the command line, using Readio's catalogs and effective defaults.
Explicit options such as `--language`, `--model`, `--voice`, `--spacy`, `--pause-mode`,
and `--unit` pin their values and skip matching questions. `--yes` bypasses only final
confirmation; `--non-interactive` and `--json` remain prompt-free. Preview retains its
smaller option set and does not run the conversion wizard.

## Removed commands and ownership

The former backend-specific commands are not aliases and are not maintained in parallel:
`read`, `sample`, `demo`, `download`, and `phonemes` are removed. TTSForge no longer
provides PyKokoro runner controls, phoneme pre-tokenization, direct streaming playback,
or TTSForge-owned renderer workspaces. Use Readio's installed engine integrations and
public services where appropriate. The TTSForge CLI focuses on the EPUB audiobook
workflow and Readio discovery/configuration.

## New workflow

```bash
ttsforge list novel.epub
ttsforge preview novel.epub
ttsforge convert novel.epub
ttsforge status novel.readio
```

For API examples and exact project/export semantics, see
[Readio's public API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md)
and [project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md).
