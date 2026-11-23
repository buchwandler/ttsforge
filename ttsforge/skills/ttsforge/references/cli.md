# CLI reference

## Project discovery

```bash
ttsforge projects list ~/Audiobooks --json
ttsforge projects info ~/Audiobooks/Novel.ttsforge --json
```

The list command discovers candidate project directories below a library root. Invalid
candidates remain visible with an `error` field.

## Create or reuse an audiobook project

```bash
ttsforge convert novel.epub --chapters 1-5
ttsforge info novel.epub --project novel.ttsforge --json
ttsforge status --project novel.ttsforge --json
```

Use `--project PATH` to choose a project explicitly. Existing projects retain their
saved chapter selection. Use another project path or `--fresh` for a different
selection.

## Chapter selection and preview

```bash
ttsforge chapters list novel.ttsforge --json
ttsforge chapters status novel.ttsforge --json
ttsforge preview novel.ttsforge --narration primary \
  --text "An explicit sentence to audition." --output preview.wav
```

Preview synthesizes the supplied text with a saved narration profile. It does not
extract chapter text.

## Quality checks

```bash
ttsforge check novel.ttsforge --json
ttsforge check novel.ttsforge --narration alternate-id
```

The report is product-level. See [QC reference](qc.md) for check boundaries and severity
meanings.

## Studio

Start the authenticated local API with `ttsforge serve`. Studio clients use the
versioned routes documented in the TTSForge Studio API. Job retry creates a new job and
reruns normal preflight.
