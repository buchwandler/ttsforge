---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0003
release_version: 0.4.1
kind: added
summary: Added guided chapter selection when creating an audiobook project
status: accepted
audience: null
scopes: []
source_refs:
  - git:8d25d2e006f226b0c98fe5704587c0e59081d30e
paths:
  - ttsforge/chapter_selection.py
  - ttsforge/ui/chapters.py
  - ttsforge/audiobook.py
  - docs/projects.md
issues: []
prs: []
sources:
  - git:8d25d2e006f226b0c98fe5704587c0e59081d30e
contributors:
  - "@holgern"
breaking: false
internal: false
order: 3
---

Interactive terminals show the detected chapters and prompt for the initial project
scope. Reused projects keep their saved chapter selection, while non-interactive
creation defaults to all chapters unless a scope is provided.
