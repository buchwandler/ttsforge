---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0006
release_version: 0.3.0
kind: added
summary: Added EPUB chapter structure and emphasis preservation through epub2text
  Markdown extraction
status: accepted
audience: null
scopes: []
source_refs:
- tl:task-0016
paths:
- ttsforge/input_reader.py
- ttsforge/epub_markdown.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 6
---
Generated SSMD now carries chapter titles, subheadings, paragraphs, semantic scene breaks, italic and strong spans, CSS-derived emphasis, navigation metadata, and extraction diagnostics.
