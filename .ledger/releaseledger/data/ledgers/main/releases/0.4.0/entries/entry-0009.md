---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0009
release_version: 0.4.0
kind: fixed
summary: Fixed encoded audiobook finalization failing while writing marker sidecars
  by carrying the validated PCM sample rate through the audio merge
status: accepted
audience: null
scopes: []
source_refs:
- tl:task-0036
paths:
- ttsforge/audio_merge.py
- ttsforge/conversion.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 9
---
