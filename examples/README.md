# TTSForge examples

The paragraph examples demonstrate the 0.3.0 render-unit workflow.

- `paragraph_conversion.py` converts an EPUB with `conversion_unit="paragraph"`. It
  needs ONNX model assets and audio dependencies.
- `paragraph_resume.py` runs a compatible conversion twice. Use `--fresh` when the first
  pass must create a new workspace; the second pass demonstrates resume.
- `paragraph_manifest.py` is inspection-only. It uses the standard library, does not
  initialize ONNX, validates contiguous sequence numbers, and checks every referenced
  WAV and marker sidecar.
- `pykokoro_paragraph_units.py` is a developer-facing low-level example. It needs
  PyKokoro, ONNX model assets, and writes each result before requesting the next.

Paragraph conversion retains one WAV per render unit: an optional announced title unit
followed by spoken paragraph units. Files live under `<stem>_paragraphs/` with
fixed-width sequence names, `manifest.json`, marker sidecars, and `playlist.m3u8`.

The workspace can resume only when the input, selected chapters, generation fingerprint,
and `conversion_unit` remain compatible. Valid WAVs are skipped. A complete workspace
can be merged without initializing ONNX. Each low-level result must be persisted or
copied before advancing iteration, and `release_audio()` must run on success,
cancellation, and error paths.

Chapter mode remains chapter-buffered. Paragraph mode prepares a chapter once and
renders bounded units sequentially. Use the CLI examples as the supported high-level
workflow; use the PyKokoro example only when integrating at the unit boundary.
