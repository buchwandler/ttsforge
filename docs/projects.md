# Projects and outputs

TTSForge provides the audiobook-facing setup and delegates workflow state, planning,
rendering, reuse, and export to Readio. The TTSForge project directory is a location for
Readio-owned intent, profile, and workspace data, not a second workflow database.

## Default project layout

For `novel.epub`, the default project is a sibling directory named `novel.ttsforge`:

```text
novel.ttsforge/
├── render.readio.toml
├── narrator.renderprofile.toml
└── book.ssmd-bundle/
```

TTSForge selects these paths. Readio's public API creates, loads, validates, and uses
the render intent, narrator profile, and persistent SSMD bundle. TTSForge does not
duplicate their schemas or edit workflow artifacts directly.

Use the default project or choose an explicit directory:

```bash
ttsforge convert novel.epub
ttsforge status novel.ttsforge
ttsforge convert novel.epub --project ./projects/novel-en
```

## Saved setup and retry

Setup values are saved through Readio before preflight confirmation and rendering. The
explicit CLI values take precedence over saved project values; saved values take
precedence over source-derived values and Readio defaults. Interactive prompts fill
values that are still missing.

A failed render leaves the saved intent and profile available. Re-run the same
conversion to reuse them. When a changed language, engine, or target makes dependent
selections incompatible, TTSForge gathers the affected selections again and asks Readio
to validate the resulting setup.

`info` reports saved setup when present. `status` asks Readio to inspect the saved
workflow and presents its stage actions; it does not make its own artifact-validity
decisions.

## Chapter selection

The chapter selector is persisted in the render intent. For example:

```bash
ttsforge convert novel.epub --chapters 2-8
```

To use a different selection without changing the original project, choose another
project path or use `--fresh`:

```bash
ttsforge convert novel.epub --chapters 1-3 --fresh
```

`--fresh` creates a separate TTSForge project directory and preserves the existing one.
It does not imply output replacement or stage rebuilding.

## M4B output and workflow controls

The default final output is `novel.m4b`. Use `--output` for another `.m4b` path.
TTSForge's audiobook conversion does not offer generic WAV/MP3 output formats.

Output replacement and stage rebuilding are independent:

- `--replace-output` explicitly authorizes replacing an existing M4B.
- `--rebuild-from STAGE` asks Readio to rebuild from a selected workflow stage.

Without output-replacement authorization, an existing output is not silently replaced.
TTSForge does not delete unrelated project data when starting a fresh project.

## Former TTSForge and Readio 0.4 projects

Workspaces created by the former TTSForge renderer and Readio 0.4 projects are
incompatible with the TTSForge 0.5 workflow. TTSForge rejects them rather than
interpreting, migrating, renaming, or deleting their state, audio, SSMD files, or resume
data.

Keep the old directory unchanged. Start separately with `--fresh` or an explicit new
`--project` path. Existing final audio is left in place unless `--replace-output` is
explicitly supplied. See the [migration guide](migration-readio.md).
