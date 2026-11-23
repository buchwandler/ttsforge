# Audiobook QC

Run safe product-level checks with:

```bash
ttsforge check PROJECT --json
ttsforge check PROJECT --narration NARRATION_ID --json
```

Findings cover source availability and inspection, primary and additional narration
setup, project metadata, chapter selection, Readio workflow executability, and safe
output checks. Errors make the report fail; warnings identify actionable quality gaps.

Deep embedded M4B metadata, chapter-marker correctness, loudness, and audio-quality
checks are not duplicated in TTSForge. They are reported as unknown or unavailable until
Readio exposes an authoritative public result. Do not inspect specialist-owned media or
workflow artifacts to infer those findings.
