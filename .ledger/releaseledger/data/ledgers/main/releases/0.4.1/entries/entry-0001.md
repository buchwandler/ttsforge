---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0001
release_version: 0.4.1
kind: added
summary: Added persistent audiobook setup and saved Readio project settings
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0041
  - tl:task-0042
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

Resolved setup is saved through Readio's public project-settings API before confirmation
or build. Normal resumes and retries reuse saved values; explicit CLI options update
their corresponding settings. --reconfigure revisits unpinned choices with saved values
as defaults, and non-interactive/JSON modes remain prompt-free.
