# Projects and library discovery

TTSForge stores a primary Readio intent and narrator profile in the project directory.
Additional narration setups remain under `variants/<key>`; these keys are internal
configuration identities, not Readio render variants exposed as product concepts.

Discover projects under a collection root:

```bash
ttsforge projects list ~/Audiobooks --json
ttsforge projects info ~/Audiobooks/Novel.ttsforge --json
```

Discovery inspects candidates through TTSForge application services. A `.ttsforge`
suffix alone does not establish that a project is valid. Incomplete, unreadable, legacy,
or malformed candidates should remain visible with an error instead of disappearing from
results.

Project chapters are shared by all narrations.
`ttsforge chapters select PROJECT SELECTOR` validates the current saved selection. It
rejects a different selection and does not change the saved Readio intent. Create a
separate project for another chapter scope.

Do not inspect or edit Readio workflow, bundle, render, or export artifacts directly.
Readio owns workflow planning, stage reuse, synthesis, composition, and export.
