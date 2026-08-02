---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0008
release_version: 0.3.0
kind: changed
summary: Changed resume handling to invalidate flattened EPUB artifacts when the rendering
  source representation changes
status: accepted
audience: null
scopes: []
source_refs: []
paths:
- ttsforge/conversion.py
- tests/test_resume_integrity.py
issues: []
prs: []
sources:
- tl:task-0016
contributors: []
breaking: false
internal: false
order: 8
---
Conversion state version 4 records source format, source id, exact Markdown body hashes, extraction schema, and representation-aware render fingerprints.
