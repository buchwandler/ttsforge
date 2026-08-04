---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 6
entry_id: entry-0001
release_version: 0.3.1
kind: changed
summary: Changed TTSForge to delegate silence generation and SSMD downmixing to AudioSig
status: accepted
audience: null
scopes: []
source_refs:
  - git:e26bed3c15fce6b81be6a9e18fd3535e325051ca
paths:
  - pyproject.toml
  - ttsforge/ssmd_audio.py
  - ttsforge/phoneme_conversion.py
  - ttsforge/cli/commands_utility.py
  - ttsforge/audio_merge.py
  - docs/installation.md
  - docs/ssmd.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

Retained secure local and remote source resolution, SoundFile decoding and encoding,
bounded WAV merging, FFmpeg integration, playback, audiobook orchestration, PyKokoro
SSMD transforms, conversion state, and audio-buffer lifecycle ownership in TTSForge.
