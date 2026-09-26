# Projects and outputs

TTSForge's EPUB workflow is a thin frontend to Readio's persistent project services.
Readio owns project state, planning, synthesis, composition, reusable work,
invalidation, and output export. TTSForge does not maintain a second conversion
workspace or duplicate Readio's project schema.

## Default project and reuse

For `novel.epub`, TTSForge uses a sibling project directory named `novel.readio` unless
`--project` supplies another path:

```bash
ttsforge convert novel.epub
ttsforge status novel.readio
```

The first conversion creates the project and records its chapter scope. Later
conversions open the same project and ask Readio to build/export from its authoritative
state. Completed compatible work can be reused; Readio determines what needs to be
planned, synthesized, composed, or exported again. Consult
[Readio's project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md)
for stage and invalidation details.

Use `--project` to choose an explicit project location. This is useful for multiple
audiobook variants or when project files should live outside the source directory:

```bash
ttsforge convert novel.epub --project novel-en.readio
```

## Chapter selection is project scope

A chapter selection is applied when creating a project. For example:

```bash
ttsforge convert novel.epub --chapters 2-8
```

That scope is persistent. Opening the project again does not silently replace its
selected chapters with a new `--chapters` value. To work on a different selection,
create another project with `--project` or use `--fresh`:

```bash
ttsforge convert novel.epub --chapters 1-3 --fresh
```

`--interactive-chapters` prompts for an initial selection. `list` and `info` inspect the
source EPUB without creating a project.

## Fresh projects and outputs

`--fresh` preserves the current project and chooses a new sibling project path. If
`novel.readio` already exists, the fresh project is typically `novel.fresh.readio`; if
that path exists, TTSForge chooses another available numbered path. Use `--project` when
an exact path is required.

The default output for the default M4B format is `novel.m4b`. Supply `--output` to
choose another path, or `--format` to select a generic Readio export format.
`ttsforge formats` reports formats available in the current installation. M4B uses
Readio's audiobook export service; it is not treated as a generic audio format.

Output replacement is deliberately explicit. `--force` requests replacement of an
existing output according to Readio's ownership rules. TTSForge does not remove a
project's source, state, or unrelated output files as a side effect of starting a fresh
project.

## Former TTSForge workspaces

Workspaces created by the previous TTSForge-owned Kokoro renderer are not Readio
projects. This migration does not convert their state, completed audio, SSMD files, or
resume metadata. If the default project path collides with an old workspace, TTSForge
stops with migration guidance instead of overwriting or attempting to resume it.

Keep the old directory as-is. To start separately, choose a new `--project` path or use
`--fresh`. Existing final audio files are also left in place unless an explicit output
replacement is requested.

## Status and planning

Use Readio-backed commands to inspect and advance project state:

```bash
ttsforge status novel.readio
ttsforge plan novel.readio
ttsforge preview novel.epub --project novel.readio --selection first:3
ttsforge convert novel.epub --project novel.readio
```

`status` reports stage states and next actions. `plan` creates or refreshes Readio
speech plans. `preview` creates or reuses the project and renders a small selection
through the same Readio project pipeline used by conversion.
