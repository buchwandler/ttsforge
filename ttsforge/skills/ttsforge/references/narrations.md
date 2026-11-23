# Narrations

A project has one primary narration and may have additional narrations. Use stable
narration IDs for operations and display names for people. Additional setups use the
existing `variants/<key>` storage layout, but the key is internal.

```bash
ttsforge narration list PROJECT --json
ttsforge narration info PROJECT NARRATION_ID --json
ttsforge narration create PROJECT --name "Warm voice" \
  --engine ENGINE --target TARGET [--voice VOICE]
ttsforge narration preflight PROJECT NARRATION_ID
ttsforge narration render PROJECT NARRATION_ID
ttsforge narration delete PROJECT NARRATION_ID
```

Deleting an additional narration removes only its TTSForge setup. It does not delete
rendered audio. The primary narration cannot be deleted. Additional output names use the
display name.

`ttsforge convert --new-variant` remains a deprecated compatibility adapter. Prefer the
`narration` commands.

For Studio, use the `/api/v1/projects/narrations` endpoints and persistent job
endpoints. Retry a failed job through `/api/v1/jobs/{job_id}/retry`; this creates a new
job and reruns worker preflight.
