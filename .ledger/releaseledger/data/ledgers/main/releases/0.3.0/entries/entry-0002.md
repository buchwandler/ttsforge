---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0002
release_version: 0.3.0
kind: added
summary:
  Added configurable SSMD prosody method selection with CLI overrides and persistent
  configuration
status: accepted
audience: null
scopes: []
source_refs:
  - git:5fdb48c08a1edbe4fd3c626ee965685e4cc23bda
  - git:fc2a81c775b6208fcc91cf09ab734e35d0dd7c83
paths:
  - ttsforge/prosody_support.py
  - ttsforge/constants.py
  - ttsforge/utils.py
  - ttsforge/cli/commands_conversion.py
  - ttsforge/cli/typer_conversion.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 2
---

Supported methods are WSOLA, ESOLA, TD-PSOLA (with psola alias), and phase vocoder with
configurable fallback chains, strict mode, clipping, FFT/hop parameters, and boundary
blending. The conversion summary displays the effective prosody method, fallbacks, and
advanced tuning values.
