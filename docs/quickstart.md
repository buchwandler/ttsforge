# Quick start

Install TTSForge with Readio `>=0.3.1`, then install a supported Readio engine extra if
you want to synthesize speech. See [Installation](installation.md) for platform and
development instructions.

## Inspect and convert

List the chapters Readio detects in an EPUB:

```bash
ttsforge list novel.epub
ttsforge info novel.epub
```

Create or reuse its audiobook project and export the default M4B:

```bash
ttsforge convert novel.epub
```

The default project is `novel.readio` beside the source EPUB, and the default output is
`novel.m4b`. Re-running the command uses the existing project's saved chapter scope and
reusable work.

## Select chapters

For a new project, an interactive terminal automatically displays the detected chapters
and prompts for a selection; no extra flag is required. Use `--chapters` to select
explicitly and skip that prompt:

```bash
ttsforge convert novel.epub --chapters 1-5
```

The selected scope is saved with the project. Reusing it does not ask for chapters
again, and a conflicting `--chapters` value is rejected rather than silently ignored.
Use `--project` or `--fresh` to create another project with a different selection.
`--interactive-chapters` is deprecated; normal TTY behavior is automatic.

When stdin, stdout, and stderr are not all terminals, or when `--non-interactive` is
supplied, and selects all chapters unless `--chapters` was provided. `--yes` skips only
the final confirmation; `--json` disables all prompts and human-readable progress. See
[Projects and outputs](projects.md) for project scope and reuse details.

## Preview, plan, and status

A preview uses the same Readio project pipeline as a full conversion:

```bash
ttsforge preview novel.epub --selection first:3
ttsforge plan novel.readio
ttsforge status novel.readio
```

`preview` creates or reuses the default project if necessary. `status` reports Readio's
current stage state and next actions.

## Choose an output and synthesis settings

M4B is the default audiobook export. Readio also provides generic audio exports; inspect
formats and availability for the current environment:

```bash
ttsforge formats
ttsforge convert novel.epub --format mp3 --output ./novel.mp3
```

You can set voice, language, engine, model, model source, quality, and speed, plus
export bitrate, loudness, metadata, and cover. Readio resolves effective synthesis
values; the preflight view shows those resolved values before you commit to the build.
Model selectors and quality values are forwarded opaquely to Readio and installed
engines:

```bash
ttsforge voices --language en-us
ttsforge convert novel.epub --voice af_heart --model kokoro-v1 --model-source github --quality fp32 --speed 1.1 --cover cover.jpg
```

Run `ttsforge convert --help` for the complete options available in this build.

## Configuration and troubleshooting

TTSForge accesses Readio's persistent configuration directly:

```bash
ttsforge config show
ttsforge config set reader.voice af_heart
ttsforge config set reader.speed 1.1
ttsforge doctor
```

The frontend does not create a parallel configuration file. For engine setup and project
semantics, see the
[Readio documentation](https://github.com/buchwandler/readio/tree/main/docs).
