---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0007
release_version: 0.4.1
kind: internal
summary: Improved CLI help test handling for ANSI output
status: accepted
audience: null
scopes: []
source_refs:
  - git:c3c8b37bd91361454e394deb1e6db552490aa2ae
paths:
  - tests/test_readio_cli.py
issues: []
prs: []
sources:
  - git:c3c8b37bd91361454e394deb1e6db552490aa2ae
contributors: []
breaking: false
internal: true
order: 6
---

Test-only normalization for terminal styling before checking the CLI help contract; no
runtime behavior changed. Hidden from public changelog output.
