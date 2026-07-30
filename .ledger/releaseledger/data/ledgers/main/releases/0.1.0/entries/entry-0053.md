---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0053
release_version: 0.1.0
kind: changed
summary: Changed Refactored pause mode and improved audio merge
status: accepted
audience: null
scopes: []
source_refs:
  - git:8417a383d128bd7e2cf17894048075b816dbeb0b
paths:
  - .codecrate.toml
  - pyproject.toml
  - tests/test_chapter_announcement.py
  - tests/test_phoneme_conversion.py
  - tests/test_phoneme_dictionary.py
  - tests/test_tokenizer.py
  - ttsforge/__init__.py
  - ttsforge/audio_merge.py
  - ttsforge/chapter_selection.py
  - ttsforge/cli/commands_phonemes.py
  - ttsforge/constants.py
  - ttsforge/conversion.py
  - ttsforge/input_reader.py
  - ttsforge/kokoro_lang.py
  - ttsforge/kokoro_runner.py
  - ttsforge/phoneme_conversion.py
  - ttsforge/ssmd_generator.py
issues: []
prs: []
sources:
  - git:8417a383d128bd7e2cf17894048075b816dbeb0b
contributors: []
breaking: false
internal: false
order: 53
---
