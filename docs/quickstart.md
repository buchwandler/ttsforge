# Quick start

Install a working local Readio checkout and TTSForge first; the published Readio release
does not yet contain TTSForge's required API. See [Installation](installation.md).

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

Choose the chapter scope when the project is first created:

```bash
ttsforge convert novel.epub --chapters 1-5
```

Use `--interactive-chapters` to choose from a prompt. The selected chapters belong to
the persistent project; changing the selection later requires a separate project, for
example:

```bash
ttsforge convert novel.epub --chapters 1-5 --fresh
```

See [Projects and outputs](projects.md) for how `--fresh`, `--project`, and old TTSForge
workspaces behave.

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

You can provide voice, language, engine, speed, bitrate, loudness, metadata, and cover
choices on `convert`. Voice and model options are supplied by Readio's installed engines
and catalog, not by a TTSForge-maintained voice list:

```bash
ttsforge voices --language en-us
ttsforge convert novel.epub --voice af_heart --speed 1.1 --cover cover.jpg
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
