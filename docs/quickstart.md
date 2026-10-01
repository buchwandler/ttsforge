# Quick start

Install TTSForge with Readio `>=0.3.5`, then install a supported Readio engine extra if
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
reusable work. In an interactive terminal, TTSForge then guides you through synthesis
choices and displays the resolved Readio settings before confirmation.

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

## Guided synthesis setup

On a TTY, `ttsforge convert novel.epub` continues after chapter selection with a guided
setup for omitted synthesis values. It discovers catalog choices while the selection is
in progress, then asks Readio to strictly resolve the completed synthesis target.

The selection differs by engine:

- PyKokoro: choose a model, then a voice.
- Piper: choose a voice-bundle target. Its matching canonical voice is selected
  automatically, so users do not choose the same bundle twice.
- Pocket: choose a bundle, then a predefined named voice. Pocket speed is fixed at `1.0`
  unless an explicit CLI speed is supplied. An explicit value is preserved for Readio's
  final validation.

The remaining prompts cover language, runnable engine selection when needed, supported
quality and speed, spaCy and short-sentence policies, lexicon/G2P choices,
capability-gated voice level, pause handling, and sentence-versus-paragraph units.
TTSForge saves the resolved setup through Readio's public project-settings API only
after final resolution succeeds, before confirmation or build. A failed build can then
be retried without repeating setup questions. Use `--reconfigure` to revisit saved
choices with their saved values as defaults. Explicit CLI options pin and update only
their corresponding settings.

Piper is target-bound: choose a voice bundle once, and TTSForge automatically uses its
canonical voice instead of asking you to select the same identity again. Pocket
selection is bundle first, then a predefined named voice. Catalog choices are gathered
before the final strict Readio synthesis resolution; incomplete setup is not saved. The
current Pocket integration uses speed `1.0` when speed is not pinned explicitly. An
explicit `--speed` pin is retained for Readio to validate.

Use explicit options to pin settings and skip matching questions, for example:

```bash
ttsforge convert novel.epub --language en-us --model MODEL_ID --voice VOICE_ID --unit paragraph
```

`--yes` skips only the final confirmation. `--non-interactive` and `--json` disable
prompts and reuse settings already saved on the project. For a new or unconfigured
project, Readio resolves unspecified values from its defaults; CLI options override
them.

When stdin, stdout, and stderr are not all terminals, or when `--non-interactive` is
supplied, no chapter or synthesis setup prompts appear. A new project selects all
chapters unless `--chapters` was provided. `--json` also disables human-readable
progress. TTY build progress updates live by chapter. See
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
