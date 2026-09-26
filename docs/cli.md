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

| Option                          | Meaning                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------ |
| `-o, --output PATH`             | Output file path. By default, use the source stem and selected format.         |
| `-f, --format FORMAT`           | Output format; default `m4b`. Use `ttsforge formats` to see available formats. |
| `--project PATH`                | Project directory; default is `<source-stem>.readio` beside the EPUB.          |
| `--chapters SELECTION`          | Initial project chapter scope, such as `1-5`, `1,3,5`, or `all`.               |
| `--interactive-chapters`        | Prompt for the initial chapter selection.                                      |
| `--voice VOICE`                 | Engine voice/selector supported by Readio.                                     |
| `--language LANG`               | Synthesis language/profile override.                                           |
| `--engine ENGINE`               | Readio synthesis engine.                                                       |
| `--speed FLOAT`                 | Synthesis speed from `0.5` to `2.0`.                                           |
| `--bitrate VALUE`               | Export bitrate where the selected format supports it.                          |
| `--target-lufs FLOAT`           | Composition loudness target.                                                   |
| `--offline` / `--refresh`       | Control Readio's offline/resource-refresh behavior for this request.           |
| `--title TEXT`, `--author TEXT` | Audiobook metadata overrides.                                                  |
| `--cover PATH`                  | Explicit cover image for audiobook export.                                     |
| `--force`                       | Ask Readio to replace an existing output it owns.                              |
| `--fresh`                       | Create a separate project and preserve the existing one.                       |
| `--json`                        | Emit a JSON result.                                                            |

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
conversion reuses it.

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
