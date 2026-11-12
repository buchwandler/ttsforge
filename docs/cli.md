# CLI reference

TTSForge exposes a focused audiobook workflow over Readio's public API. Run
`ttsforge --help` or `ttsforge COMMAND --help` for the installed build. `--json` selects
structured output on supported commands, and `--debug` includes a traceback after an
error.

## `convert`

Inspect an EPUB, create or reuse its TTSForge project, inspect the workflow, then
render/export an M4B:

```bash
ttsforge convert novel.epub
```

| Option                          | Meaning                                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------------------- |
| `--project PATH`                | Project directory. Defaults to `<source-stem>.ttsforge` beside the EPUB.                          |
| `--chapters SELECTOR`           | Chapter selection for the book workflow, for example `1-5`, `1,3,5`, or `all`.                    |
| `-o, --output PATH`             | M4B output path; defaults to `<source-stem>.m4b`.                                                 |
| `--language LANG`               | Language used for the audiobook setup.                                                            |
| `--engine ENGINE`               | Readio synthesis engine.                                                                          |
| `--target TARGET`               | Runnable target exposed by the selected engine.                                                   |
| `--voice VOICE`                 | Voice selector supported by the selected target.                                                  |
| `--engine-option KEY=VALUE`     | Engine-specific option; repeatable. Use options exposed by Readio for that engine and target.     |
| `--speed FLOAT`                 | Speech speed in the range shown by help; the selected engine may impose stricter support.         |
| `--bitrate VALUE`               | M4B export bitrate.                                                                               |
| `--target-lufs FLOAT`           | Composition loudness target.                                                                      |
| `--title TEXT`, `--author TEXT` | Audiobook metadata overrides.                                                                     |
| `--cover PATH`                  | Cover image for the audiobook.                                                                    |
| `--offline` / `--refresh`       | Control Readio discovery/resource behavior for this request.                                      |
| `--rebuild-from STAGE`          | Ask Readio to rebuild from `convert`, `compile`, `render_plan`, `render`, `compose`, or `export`. |
| `--replace-output`              | Explicitly authorize replacing an existing M4B output.                                            |
| `--fresh`                       | Use a separate new TTSForge project directory. Does not replace output or force a rebuild.        |
| `-y, --yes`                     | Skip final confirmation only.                                                                     |
| `--non-interactive`             | Disable prompts and use saved setup and Readio defaults.                                          |
| `--json`                        | Emit structured output without prompts or progress prose.                                         |
| `--debug`                       | Show a traceback after an error.                                                                  |

Chapter selectors are 1-based and ranges are inclusive. Use `all`, a number such as `4`,
a range such as `2-7`, or comma-separated combinations such as `1,3,8-10`. Open-ended
ranges such as `5-` are accepted and normalized to the inspected chapter count.

A new interactive project displays the chapter inventory and prompts for a selection
when `--chapters` is omitted. Press Enter to select `all`. Explicit `--chapters` skips
the prompt. Existing projects reuse their saved selector when the option is omitted, and
a different explicit selector is rejected. Use `--fresh` or pass a different project
path to create a project with a different chapter scope. `--non-interactive` and
`--json` never prompt; a new project defaults to `all`.

TTSForge saves the resolved render intent and narrator profile before rendering. A
failed render can be retried with the saved setup. Readio owns preflight decisions,
stage reuse, and rendering. See [Projects and outputs](projects.md) for persistence and
precedence.

## `list`

List the chapters discovered in a source EPUB without creating a project:

```bash
ttsforge list novel.epub
```

Supports `--json` and `--debug`.

## `info`

Show source metadata and any saved audiobook setup:

```bash
ttsforge info novel.epub
ttsforge info novel.epub --project novel.ttsforge
```

Supports `--project PATH`, `--json`, and `--debug`.

## `status`

Inspect the saved workflow for a source or project directory:

```bash
ttsforge status novel.ttsforge
```

The source argument is optional; `--project PATH` can select a project explicitly.
Supports `--json` and `--debug`.

## Discovery commands

```bash
ttsforge engines
ttsforge targets --engine ENGINE [--language LANG] [--offline] [--refresh]
ttsforge voices [--engine ENGINE] [--target TARGET] [--language LANG] [--offline] [--refresh]
```

`engines` lists engines exposed by Readio. `targets` requires an engine and lists its
runnable targets. `voices` lists voices available for the optional
engine/target/language filters. Discovery results depend on the installed Readio
integrations and local environment. All three commands support `--json` and `--debug`.

## Removed commands

The TTSForge 0.5 CLI focuses on `convert`, `list`, `info`, `status`, `engines`,
`targets`, and `voices`. Earlier commands such as `preview`, `plan`, `config`, `models`,
`formats`, `doctor`, and `ssmd` are not registered in this workflow. The former
backend-specific `read`, `sample`, `demo`, `download`, and `phonemes` commands are also
removed. See the [migration guide](migration-readio.md).
