---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.5.0
kind: changed
summary:
  Moved audiobook conversion to Readio 0.6.1 and a new incompatible TTSForge project
  layout
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0047
paths:
  - ttsforge/readio_backend.py
  - ttsforge/application
  - ttsforge/cli
issues: []
prs: []
sources: []
contributors: []
breaking: true
internal: false
order: 1
---

TTSForge 0.5 projects persist Readio intent, profile, and bundle state. Existing v0.4
projects are not migrated or modified.
