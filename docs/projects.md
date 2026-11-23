# Projects and outputs

TTSForge provides the audiobook-facing setup and delegates workflow state, planning,
rendering, reuse, and export to Readio. The TTSForge project directory holds
Readio-owned intent, profile, and workspace data, plus optional TTSForge-owned audiobook
metadata overrides. It is not a second workflow database.

## Library discovery

Use `ttsforge projects list ROOT` to discover project candidates below a collection
directory and `ttsforge projects info PROJECT` to inspect one candidate. Discovery
checks project setup through TTSForge application services, not by reading Readio
workflow artifacts. Candidates with malformed or legacy setup remain visible with an
error. A `.ttsforge` suffix identifies a candidate only; it does not prove validity.

The Studio API exposes `GET /api/v1/library/projects?root=...` and
`GET /api/v1/library/projects/{project_id}`. Summaries include metadata, chapter
selection counts, narrations, configured outputs, QC state, recent activity, and an
optional active job ID.

## Default project layout

For `novel.epub`, the default project is a sibling directory named `novel.ttsforge`:

```text
novel.ttsforge/
├── render.readio.toml
├── narrator.renderprofile.toml
├── audiobook-metadata.json (created when metadata overrides are saved)
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

## Audiobook metadata

Use `ttsforge metadata show`, `set`, and `validate` to manage project-wide audiobook
metadata. TTSForge stores overrides in `audiobook-metadata.json` at the project root,
separate from the Readio-owned intent, narrator profile, and workspace. Effective
metadata combines source metadata, saved setup values, and TTSForge overrides.

## Narrations

An existing project can hold a primary narration and additional narration
configurations. Use the narration commands to create and render another voice or
synthesis target without reconverting or recompiling the prepared book:

```bash
ttsforge narration list novel.ttsforge
ttsforge narration create novel.ttsforge --name "Kokoro Heart" \
  --engine kokoro --target target-a --voice voice-a
ttsforge narration render novel.ttsforge <narration-id>
```

Creation requires a complete saved primary setup. The source, chapter scope, and shared
preparation settings remain inherited from that setup. Additional narration Readio
intent and profile files stay in the compatible
`novel.ttsforge/variants/<configuration-key>/` layout, and the project root and
`book.ssmd-bundle/` remain shared. TTSForge uses the persisted display name for the
default output, such as `novel [Kokoro Heart].m4b`; if that path is already assigned, it
adds a numeric suffix. The configuration ID stays distinct from Readio's specialist
render variant. Readio owns planning, reuse, rendering, and export.

`ttsforge narration delete` removes only an additional narration's setup. Existing
rendered audio is retained. The primary narration cannot be deleted.

`convert --new-variant` remains as a deprecated compatibility adapter to the narration
service. It keeps the same project constraints and emits a deprecation warning. Prefer
the explicit narration commands for new workflows.

`ttsforge info novel.epub` continues to list valid alternate setups and report
incomplete or invalid variant directories. `ttsforge status` continues to inspect the
root setup.

## Chapter selection

The chapter selector is persisted in the render intent. For example:

```bash
ttsforge convert novel.epub --chapters 2-8
```

Use the chapter commands to inspect chapter availability and the project's existing
selection:

```bash
ttsforge chapters list novel.epub
ttsforge chapters status novel.ttsforge
ttsforge chapters select novel.ttsforge 2-8
```

`chapters select` validates the supplied selector against the saved project selector; it
does not modify the Readio-owned render intent. A different selection requires another
project path or `--fresh`.

To use a different selection without changing the original project, choose another
project path or use `--fresh`:

```bash
ttsforge convert novel.epub --chapters 1-3 --fresh
```

`--fresh` creates a separate TTSForge project directory and preserves the existing one.
It does not imply output replacement or stage rebuilding.

## Product-level QC

`ttsforge check novel.ttsforge` aggregates safe checks for source readability, saved
narrations, metadata, chapter selection, output existence, and Readio workflow findings.
`--json` returns a stable report. Deep checks of M4B tags, chapter markers, and audio
quality remain unknown until Readio exposes an authoritative result. TTSForge does not
inspect specialist-owned artifacts.

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
