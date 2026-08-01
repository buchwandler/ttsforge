---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 3
entry_id: entry-0001
release_version: v0.3.0
kind: changed
summary: Changed TTSForge to delegate silence generation and SSMD downmixing to AudioSig
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0014
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
