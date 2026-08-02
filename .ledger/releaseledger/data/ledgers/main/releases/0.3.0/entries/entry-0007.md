---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0007
release_version: 0.3.0
kind: changed
summary:
  Changed Markdown EPUB extraction and emphasis preservation to be the default while
  keeping audible emphasis plain
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ttsforge/constants.py
  - ttsforge/cli/typer_conversion.py
  - docs/configuration.md
issues: []
prs: []
sources:
  - tl:task-0016
contributors: []
breaking: false
internal: false
order: 7
---

The CLI exposes --epub-content-mode markdown|plain and separates source emphasis
preservation from ssmd_emphasis_mode rendering.
