---
name: ttsforge-audiobook
description: Produce and manage audiobooks from EPUB sources with TTSForge.
---

# TTSForge audiobook production

Use TTSForge for audiobook-specific work: creating EPUB projects, selecting chapters,
managing narrations, previewing narration text, producing M4B files, checking project
quality, and monitoring Studio jobs.

## Route requests

- EPUB to audiobook, chapter selection, audiobook preview, M4B production, audiobook QC,
  narration setup, and Studio audiobook jobs: use TTSForge.
- Literal text-to-speech, DOCX/PDF/general document rendering, generic engine or runtime
  management, and generic speech MCP: use Readio.
- Debugging specialist workflow artifacts: use the relevant specialist CLI or Readio
  guidance. Do not parse TTSForge or Readio workspace internals yourself.

## Start with discovery

For an existing collection, run `ttsforge projects list ROOT`. Inspect a project with
`ttsforge projects info PROJECT`. A listed project may include an error when its setup
is incomplete or invalid. Do not assume a directory is valid just because its name ends
in `.ttsforge`.

Use `ttsforge --help` and the focused command references for command options. Use
`--json` when structured output is needed.

## Boundaries

Readio owns workflow planning, artifact reuse, synthesis, composition, export, and
workflow inspection. Use TTSForge's application commands and Studio API instead of
reading specialist-owned files or independently deciding which workflow stages to reuse.

Preview accepts explicit text only. Chapter-derived preview text is unavailable until
Readio exposes a public excerpt API. TTSForge QC reports safe product checks; deep
embedded M4B, chapter-marker, and audio-quality checks may be `unknown` when no
authoritative Readio result exists.

Chapter selection is project-scoped. Changing the saved selection requires a separate
project; `chapters select` validates the current selection and does not mutate it.

## References

- [CLI commands](references/cli.md)
- [Projects and library discovery](references/projects.md)
- [Narrations](references/narrations.md)
- [Audiobook QC](references/qc.md)
