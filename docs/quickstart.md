# Quick start

Install TTSForge and a Readio engine integration if you want to render speech. TTSForge
requires Readio `>=0.6.9,<0.7`; see [Installation](installation.md) for setup.

## Inspect and convert

Inspect an EPUB without creating a project:

```bash
ttsforge list novel.epub
ttsforge info novel.epub
```

Create or reuse its audiobook project and export the default M4B:

```bash
ttsforge convert novel.epub
```

The default project is `novel.ttsforge/` beside the EPUB, and the default output is
`novel.m4b`. In an interactive terminal, TTSForge prompts for missing chapter and voice
setup, displays a read-only workflow preflight, and asks for final confirmation. Setup
is saved before rendering so a failed render can be retried without repeating completed
setup.

## Select chapters

For a new project, an interactive terminal displays the chapter inventory and asks which
chapters to include. Selectors are 1-based, ranges are inclusive, and comma-separated
selections are supported. Examples include `all`, `4`, `2-7`, and `1,3,8-10`. TTSForge
also accepts an open-ended range such as `5-` and closes it against the inspected book.
Press Enter to select `all`.

Specify `--chapters` to skip the prompt:

```bash
ttsforge convert novel.epub --chapters 1-5
```

The chapter selection is saved in the project's render intent. Reusing a project without
`--chapters` keeps its saved selection. An explicit different selection is rejected
because chapter scope is part of the project; use another `--project` path or `--fresh`
to select a different scope.

## Choose an engine, target, and voice

Discover available choices through Readio:

```bash
ttsforge engines
ttsforge targets --engine ENGINE --language en-us
ttsforge voices --engine ENGINE --target TARGET --language en-us
```

The interactive converter presents the same engine, target, and voice choices. Pass
values explicitly to pin them and skip matching setup prompts:

```bash
ttsforge convert novel.epub --engine ENGINE --target TARGET --voice VOICE
```

Use `--engine-option KEY=VALUE` for an option exposed by the selected Readio engine.
`--speed` is limited to the range shown by `ttsforge convert --help`; Readio validates
the value for the selected target.

## Saved setup and automation

Explicit CLI values take precedence over saved project values. Saved values are reused
on later runs; source metadata and Readio defaults supply remaining values before
interactive prompts fill any missing choices. Changes to language, engine, or target
invalidate dependent saved selections so incompatible choices are gathered again.

`--yes` skips only final confirmation. In normal conversion, `--non-interactive`
disables prompts and uses the saved setup and Readio defaults. The deprecated
`--new-variant` adapter requires explicit engine and target selectors in non-interactive
and JSON modes; prefer `ttsforge narration create` for new workflows.

```bash
ttsforge convert novel.epub --chapters all --non-interactive --json
```

## Manage narrations

After a normal conversion has saved a complete base setup, create and render another
narration without reconverting or recompiling the prepared book:

```bash
ttsforge narration create novel.ttsforge --name "Kokoro Heart" \
  --engine kokoro --target target-a --voice voice-a
ttsforge narration list novel.ttsforge
ttsforge narration render novel.ttsforge <narration-id>
```

A narration inherits the source, chapter scope, and shared preparation settings from the
primary setup. Its Readio intent and profile are stored under
`novel.ttsforge/variants/<configuration-key>/`, while the project root and
`book.ssmd-bundle/` remain shared. The display name determines the default output name;
the stable narration ID identifies the synthesis configuration.
`ttsforge narration delete` removes only the additional setup and keeps rendered audio.

`convert --new-variant` remains as a deprecated compatibility adapter. New workflows
should use the explicit narration commands.

## Preview a narration

Use the saved primary or alternate profile to synthesize short user-provided text
without rendering the full audiobook:

```bash
ttsforge preview novel.ttsforge --narration <narration-id> \
  --text "The station lights went out one by one." --output preview.wav
```

Omit `--narration` to use `primary`. Preview audio is not cached, and the command will
not overwrite an existing WAV. Chapter-derived preview text is unavailable until Readio
exposes a public source excerpt API.

## Output, replacement, and rebuilds

M4B is the final audiobook format. Set the output path with `--output`:

```bash
ttsforge convert novel.epub --output ./audio/novel.m4b
```

These controls have separate meanings:

- `--replace-output` explicitly authorizes replacing an existing M4B output.
- `--rebuild-from STAGE` asks Readio to rebuild from `convert`, `compile`,
  `render_plan`, `render`, `compose`, or `export`.
- `--fresh` starts in a separate TTSForge project directory. It does not authorize
  output replacement or stage rebuilding.

## Inspect the workflow

```bash
ttsforge status novel.ttsforge
```

`status` asks Readio to inspect the saved workflow. TTSForge presents the returned stage
actions and does not infer artifact validity itself. See
[Projects and outputs](projects.md) and the [CLI reference](cli.md).
