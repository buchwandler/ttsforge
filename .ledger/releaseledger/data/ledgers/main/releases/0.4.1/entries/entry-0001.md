---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.4.1
kind: added
summary:
  Added guided audiobook setup with Readio catalogs for models, voices, and synthesis
  policies
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0041
paths:
  - ttsforge/cli/app.py
  - ttsforge/ui/synthesis.py
  - docs/cli.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

Interactive convert prompts for synthesis choices that are not pinned by CLI options and
shows Readio's resolved setup before confirmation. --yes skips only final confirmation;
non-interactive and JSON modes remain prompt-free.
