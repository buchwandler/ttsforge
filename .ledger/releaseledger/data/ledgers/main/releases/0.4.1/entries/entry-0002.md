---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: 0.4.1
kind: changed
summary: Changed audiobook conversion to use Readio-managed projects
status: accepted
audience: null
scopes: []
source_refs:
  - git:8832d319b935712b5734979304b81a98a31c6cbf
paths:
  - pyproject.toml
  - ttsforge/audiobook.py
  - ttsforge/readio_backend.py
  - ttsforge/cli/app.py
  - docs/migration-readio.md
issues: []
prs: []
sources:
  - git:8832d319b935712b5734979304b81a98a31c6cbf
contributors:
  - "@holgern"
breaking: true
internal: false
order: 2
---

Readio now owns EPUB project setup, synthesis, resumability, builds, and exports. This
is a breaking migration: the former TTSForge rendering pipeline and the read, sample,
demo, download, and phonemes commands are not carried forward. Existing TTSForge
workspaces are not migrated; see docs/migration-readio.md.
