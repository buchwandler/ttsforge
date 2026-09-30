---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 3
entry_id: entry-0001
release_version: 0.4.1
kind: added
summary: Added guided audiobook setup with persistent Readio project settings
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0041
  - tl:task-0042
  - git:7977a59b58f28e575c60d942ad9830b50172a2cb
  - git:c449ae96314bd3d6440c5aba80c63d51fd438390
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

Interactive setup prompts for missing language, engine, model, voice, and synthesis
choices using Readio catalogs, then displays the effective configuration. Resolved
settings are saved through Readio before confirmation or build; resumes and retries
reuse saved values, explicit CLI options update corresponding settings, and
--reconfigure revisits unpinned choices.
