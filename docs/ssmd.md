# SSMD tools

TTSForge provides access to Readio's public SSMD authoring and analysis services. It
does not implement an independent SSMD renderer or a TTSForge-specific SSMD policy
stack.

## Check and validate

```bash
ttsforge ssmd check chapter.ssmd
ttsforge ssmd validate chapter.ssmd
ttsforge ssmd analyze chapter.ssmd
ttsforge ssmd roundtrip chapter.ssmd
```

- `check` reports Readio's SSMD diagnostics.
- `validate` additionally requires voice references to resolve.
- `analyze` summarizes voice references and unresolved bindings.
- `roundtrip` runs Readio's authoring roundtrip check.

Use `--roundtrip` with `check` or `validate` to include the roundtrip check. Add
`--json` for structured output. Commands that find issues return a non-zero exit status.

## Materialize voice bindings

If a document uses logical voice references, map them explicitly through Readio:

```bash
ttsforge ssmd materialize chapter.ssmd \
  --bindings '{"narrator":"af_heart"}' \
  --output chapter.materialized.ssmd
```

The bindings argument must be a JSON object mapping reference strings to voice strings.
By default, the command writes a separate output. Use `--in-place` only when
intentionally replacing the source document. `--provider` may select an SSMD provider
supported by Readio.

## Format and semantics

SSMD syntax, supported annotations, voice-resolution behavior, and diagnostics are
defined by Readio and the SSMD format implementation. Use the upstream
[Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md) for
authoring-service details and the [SSMD project](https://github.com/buchwandler/ssmd)
for format reference.
