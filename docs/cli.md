# CLI reference

TTSForge exposes a focused audiobook workflow over Readio's public services. Run
`ttsforge --help` or `ttsforge COMMAND --help` for help from the installed build. Use
`--json` on supported commands for machine-readable results and `--debug` for a
traceback after an error.

## `convert`

Inspect an EPUB, create or reuse its Readio project, and build/export an audiobook:

```bash
ttsforge convert novel.epub
```

| Option                                 | Meaning                                                                           |
| -------------------------------------- | --------------------------------------------------------------------------------- |
| `-o, --output PATH`                    | Output file path; defaults to the source stem and selected format.                |
| `-f, --format FORMAT`                  | Output format; default `m4b`. Use `ttsforge formats` for available formats.       |
| `--project PATH`                       | Project directory; default is `<source-stem>.readio` beside the EPUB.             |
| `--chapters SELECTION`                 | Chapter scope for a new project, such as `1-5`, `1,3,5`, or `all`.                |
| `--interactive-chapters`               | Deprecated compatibility flag; interactive terminals now prompt automatically.    |
| `--voice VOICE`                        | Engine voice/selector supported by Readio.                                        |
| `--language LANG`                      | Synthesis language/profile override.                                              |
| `--engine ENGINE`                      | Readio synthesis engine.                                                          |
| `--model MODEL`                        | Model selector forwarded to Readio.                                               |
| `--model-source SOURCE`                | Model-source selector forwarded to Readio.                                        |
| `--quality QUALITY`                    | Quality value forwarded to Readio.                                                |
| `--speed FLOAT`                        | Synthesis speed from `0.5` to `2.0`.                                              |
| `--spacy POLICY`                       | Readio spaCy policy for text processing.                                          |
| `--short-sentence POLICY`              | Readio short-sentence handling policy.                                            |
| `--lexicon SELECTOR`                   | Select a lexicon; repeatable for multiple selectors.                              |
| `--no-lexicons`                        | Disable lexicons; mutually exclusive with `--lexicon` and `--auto-lexicons`.      |
| `--auto-lexicons`                      | Let Readio select lexicons; mutually exclusive with explicit/disabled modes.      |
| `--g2p-fallback POLICY`                | Readio grapheme-to-phoneme fallback policy.                                       |
| `--lexicon-data-policy POLICY`         | Readio lexicon data selection policy.                                             |
| `--allow-experimental`                 | Permit experimental catalog choices where Readio supports them.                   |
| `--voice-level MODE`                   | Voice-level calibration, when supported by the selected engine.                   |
| `--pause-mode MODE`                    | Readio pause-handling policy.                                                     |
| `--unit UNIT`, `--synthesis-unit UNIT` | Choose sentence or paragraph synthesis units.                                     |
| `--bitrate VALUE`                      | Export bitrate where the selected format supports it.                             |
| `--target-lufs FLOAT`                  | Composition loudness target.                                                      |
| `--offline` / `--refresh`              | Control Readio's offline/resource-refresh behavior for this request.              |
| `--title TEXT`, `--author TEXT`        | Audiobook metadata overrides.                                                     |
| `--cover PATH`                         | Explicit cover image for audiobook export.                                        |
| `--force`                              | Ask Readio to replace an existing output it owns.                                 |
| `--fresh`                              | Create a separate project and preserve the existing one.                          |
| `-y, --yes`                            | Skip final confirmation; does not disable chapter or synthesis setup prompts.     |
| `--non-interactive`                    | Disable prompts; use saved setup and Readio defaults.                             |
| `--reconfigure`                        | Revisit unpinned saved synthesis choices, using their current values as defaults. |
| `--json`                               | Emit one JSON result, including saved-setup provenance; no prompts or progress.   |

## Conversion interaction and progress

When stdin, stdout, and stderr are terminals, conversion is interactive unless `--json`
or `--non-interactive` is selected. A new project without `--chapters` shows the
detected chapter table and prompts for a selection. An existing project uses its saved
chapter scope and does not prompt again.

Before preflight, `convert` merges saved project settings with explicitly supplied CLI
values and guides you through missing synthesis settings. Normal reuse skips valid saved
choices and opens catalogs only when a choice is needed. A project without saved
settings—including a legacy project—gets Readio's resolved defaults; TTSForge saves the
complete resolved setup through Readio's public project-settings API before confirmation
or build. A failed build can be retried without repeating setup. Readio remains the sole
owner of persisted project state.

Use `--reconfigure` to revisit unpinned setup fields with saved values as defaults.
Explicit CLI values pin and update only their corresponding settings. Changing language,
engine, or model causes dependent unpinned choices to be selected again; CLI-pinned
dependents remain.

TTSForge asks for language, runnable engine selection where applicable, and model/voice
catalog choices when needed. Remaining questions cover supported quality, speed, spaCy
and short-sentence policies, lexicons, G2P fallback and lexicon data, supported
voice-level calibration, pause mode, and synthesis unit. Readio owns catalogs,
capabilities, and resolution rules; the `Audiobook Setup` table shows the effective
values used.

Explicit synthesis options pin and update their corresponding saved settings. `--yes`
skips only final confirmation; it does not skip any setup questions still needed.
`--reconfigure` reopens unpinned saved setup questions with their current values as
defaults.

For a new project in non-interactive mode, chapter selection defaults to `all` unless
`--chapters` is explicit. Non-interactive runs reuse valid project settings and let
Readio resolve any unspecified values without prompting; CLI options override saved
values. JSON mode never prompts or emits progress prose on stdout; its single result
includes `settings_source` and `settings_saved` metadata. Existing projects keep their
persisted chapter scope. If an explicit `--chapters` value conflicts with that saved
scope, conversion fails with guidance to use `--fresh` or another `--project` path.

A TTY conversion uses a live, chapter-aware progress display. Redirected/non-interactive
runs print milestone lines rather than every segment; JSON mode has no human-readable
progress.

Chapter selection is project scope: it is persisted when the project is first created.
Reusing a project does not replace its saved chapter scope. Use another `--project` or
`--fresh` for a different selection. See [Projects and outputs](projects.md).

M4B is exported through Readio's audiobook service; generic formats use Readio's project
export. TTSForge does not encode audio itself. Readio's public API determines output
reuse and replacement safety.

## Inspecting and managing projects

```bash
ttsforge list novel.epub
ttsforge info novel.epub
ttsforge status novel.readio
ttsforge plan novel.readio
```

- `list EPUB` displays chapters and character counts.
- `info EPUB` displays EPUB metadata and chapter count.
- `status [PROJECT]` reports Readio's stage states and next actions. The argument
  defaults to the current directory.
- `plan PROJECT` creates or updates speech plans through Readio.

## `preview`

Render a small preview through the project pipeline:

```bash
ttsforge preview novel.epub --selection first:3
```

Options include `--project`, `--chapters`, `--selection`, `--voice`, `--language`,
`--engine`, `--speed`, `--target-lufs`, and `--json`. The default selection is
`first:3`. If no project exists, preview creates the default project; subsequent
conversion reuses it. `preview` has a smaller option set and does not run the guided
`convert` setup wizard.

## Readio discovery

```bash
ttsforge voices [--engine ENGINE] [--language LANG] [--model MODEL] [--gender GENDER]
ttsforge models [--engine ENGINE] [--language LANG] [--status STATUS]
ttsforge engines
ttsforge formats
ttsforge doctor
```

`voices` and `models` accept `--offline`, `--refresh`, and `--json`. Catalog contents
and runtime availability depend on the installed Readio engines and local environment.
`doctor` reports Readio version, configuration, engines, dependencies, formats, and
paths.

## `config`

All configuration operations use Readio's persisted settings; TTSForge does not maintain
a duplicate settings file:

```bash
ttsforge config path
ttsforge config show
ttsforge config set reader.voice af_heart
ttsforge config init
ttsforge config languages
ttsforge config language en-us
```

`config set KEY VALUE` accepts one value; JSON values such as numbers, booleans, arrays,
and objects are parsed as JSON, otherwise the value is stored as text. `--path PATH`
selects an alternate configuration file on `show` and `set`.

## `ssmd`

Readio-backed SSMD commands are:

```bash
ttsforge ssmd check FILE [--roundtrip]
ttsforge ssmd validate FILE [--roundtrip]
ttsforge ssmd analyze FILE
ttsforge ssmd roundtrip FILE
ttsforge ssmd materialize FILE --bindings '{"narrator":"af_heart"}' [--output OUT]
```

`validate` additionally requires resolvable voice references. `materialize` writes
explicit bindings to a new file by default; `--in-place` opts into updating the source
file. These commands use Readio's SSMD authoring API; see [SSMD tools](ssmd.md).

## Removed commands

`read`, `sample`, `demo`, `download`, and `phonemes` belonged to the former TTSForge
rendering backend and are no longer registered. TTSForge does not maintain compatibility
aliases or a parallel engine implementation. See the
[migration guide](migration-readio.md).
