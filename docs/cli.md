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
| `--new-variant`                 | Deprecated compatibility adapter. Prefer the `narration` commands.                                |
| `-y, --yes`                     | Skip final confirmation only.                                                                     |
| `--non-interactive`             | Disable prompts; new variants require explicit engine and target selectors.                       |
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

`--new-variant` is a deprecated compatibility adapter for creating and rendering an
additional narration. It inherits the base source, chapter scope, and preparation
settings, then selects an engine, target, and applicable voice. With `--non-interactive`
or `--json`, supply `--engine` and `--target`; supply `--voice` when the selected target
does not provide a default. It rejects `--fresh`, convert/compile rebuilds, and changes
to shared preparation settings. It does not enable `--replace-output`. JSON output
includes a structured warning; non-JSON output prints a deprecation warning.

Each additional narration keeps its own Readio intent and render profile below
`variants/<configuration-key>/`, while sharing the project's `book.ssmd-bundle/`. The
configuration key is TTSForge setup identity, not Readio's specialist render variant.
`info` lists valid and incomplete alternate setups; `status` continues to inspect the
root setup. TTSForge saves the resolved render intent and narrator profile before
rendering. A failed render can be retried with the saved setup. Readio owns preflight
decisions, stage reuse, and rendering. See [Projects and outputs](projects.md) for
persistence and precedence.

## `narration`

Use the narration commands to list, inspect, create, preflight, render, and delete saved
narrations in an existing TTSForge project:

```bash
ttsforge narration list novel.ttsforge
ttsforge narration create novel.ttsforge --name "Kokoro Heart" \
  --engine kokoro --target target-a --voice voice-a
ttsforge narration info novel.ttsforge <narration-id>
ttsforge narration preflight novel.ttsforge <narration-id>
ttsforge narration render novel.ttsforge <narration-id>
ttsforge narration delete novel.ttsforge <narration-id>
```

Creation requires a saved primary setup. The stable narration ID identifies the
synthesis configuration; the display name is used in the output filename and is
persisted separately. Deleting an additional narration removes only its TTSForge setup.
Rendered audio is kept. Use `--json` on list, info, create, preflight, and render for
structured output.

## `preview`

Synthesize explicit text with a saved narration and save the returned WAV to a path you
choose:

```bash
ttsforge preview novel.ttsforge \
  --narration <narration-id> \
  --text "The station lights went out one by one." \
  --output preview.wav
```

`--narration` defaults to `primary`. The command uses the narration's saved Readio
profile, does not render the full audiobook, and refuses to overwrite an existing
output. Preview audio stays in memory unless you request an output file. Chapter-derived
previews are unavailable until Readio exposes a public source excerpt API. Use `--json`
for audio metadata and the output path.

## `metadata`

Inspect and update project-wide audiobook metadata overrides:

```bash
ttsforge metadata show novel.ttsforge
ttsforge metadata set novel.ttsforge --title "Novel" --author "A. Writer" \
  --narrator "Reader" --year 2024 --cover cover.jpg
ttsforge metadata validate novel.ttsforge --json
```

`metadata set` accepts `--title`, `--subtitle`, `--author`, `--narrator`, `--series`,
`--series-number`, `--language`, `--publisher`, `--year`, and `--cover`. Overrides are
stored in the project as TTSForge-owned metadata, separate from Readio workflow state.
`metadata show` returns source metadata, saved overrides, and effective metadata.
Validation reports missing required fields as warnings and invalid values as errors.

## `chapters`

List chapter inventory, inspect the project's saved selection, or validate that a
requested selection matches the existing project scope:

```bash
ttsforge chapters list novel.epub --json
ttsforge chapters status novel.ttsforge --json
ttsforge chapters select novel.ttsforge 1-5 --json
```

`chapters select` does not change the project's saved selection. A different selection
requires a separate project path or `convert --fresh`. The top-level `list` command
remains available for source chapter inventory.

## `check`

Run TTSForge product-level checks for a saved project:

```bash
ttsforge check novel.ttsforge --json
ttsforge check novel.ttsforge --narration kokoro-heart
```

The report aggregates source, setup, metadata, chapter-selection, output-existence, and
Readio workflow findings. Exit codes are `0` when there are no error findings, `1` when
QC finds errors, and `2` for command or configuration failures. Deep M4B/audio QC is
reported as unknown until Readio exposes an authoritative public result; TTSForge does
not inspect specialist-owned artifacts.

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

## `projects`

Discover TTSForge project candidates below a collection root or inspect one directly:

```bash
ttsforge projects list ~/Audiobooks --json
ttsforge projects info ~/Audiobooks/Novel.ttsforge --json
```

Malformed and legacy candidates remain visible with an error. A `.ttsforge` suffix alone
does not establish project validity. JSON summaries include selected chapter counts,
narrations, outputs, QC state, and job activity.

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

## `serve`

Run the optional local HTTP API used by TTSForge Studio:

```bash
ttsforge serve --port 8765 --token "$TTSFORGE_TOKEN" \
  --state-dir ~/.local/state/ttsforge
```

The server extra is required. The default host is `127.0.0.1`; non-loopback bind
addresses are rejected. Use `--port 0` to request an ephemeral port. Startup writes one
JSON `server.ready` record to stdout with the actual port and API version. Normal
diagnostics go to stderr. The bearer token can be provided through `TTSFORGE_TOKEN`
instead of `--token`.

Use repeatable `--allow-origin ORIGIN` options only for trusted browser origins.
Wildcard origins are rejected. The command also accepts `--state-dir`, `--log-level`,
and `--debug`. `python -m ttsforge.server` provides the same options and launcher. See
the [server guide](server.md) and [Studio API reference](studio-api.md).

## Removed commands

The TTSForge 0.5 CLI focuses on `convert`, `narration`, `preview`, `metadata`,
`chapters`, `check`, `list`, `info`, `status`, `engines`, `targets`, `voices`, and
optional `serve`. Earlier commands such as `plan`, `config`, `models`, `formats`,
`doctor`, and `ssmd` are not registered in this workflow. The former backend-specific
`read`, `sample`, `demo`, `download`, and `phonemes` commands are also removed. See the
[migration guide](migration-readio.md).
