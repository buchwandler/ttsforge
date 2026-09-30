---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0004
release_version: 0.4.1
kind: changed
summary: Changed catalogs to show Readio canonical voice identifiers
status: accepted
audience: null
scopes: []
source_refs:
  - git:00bb42787f11226592e20544296904001ae72a82
  - git:20bb74b9e537be4954cabbf081ea5c833a23a16f
paths:
  - ttsforge/ui/catalog.py
  - ttsforge/ui/synthesis.py
  - ttsforge/cli/app.py
  - docs/voices.md
issues: []
prs: []
sources:
  - git:00bb42787f11226592e20544296904001ae72a82
  - git:20bb74b9e537be4954cabbf081ea5c833a23a16f
contributors:
  - "@holgern"
breaking: false
internal: false
order: 4
---

Engine, model, and voice catalogs use compact text lists. Voice selection stores the
canonical Readio voice ID, with selectors shown as aliases and status or engine/model
details included where useful.
