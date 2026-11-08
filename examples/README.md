# TTSForge examples

These examples use the TTSForge CLI and Readio's workflow gateway. TTSForge does not
implement a renderer directly; Readio owns persistent workflow state, synthesis,
composition, and export.

## Inspect a source before conversion

```bash
ttsforge list novel.epub --json > chapters.json
ttsforge info novel.epub --json > book.json
```

These commands inspect the EPUB without creating a project.

## Create and inspect a project

```bash
ttsforge convert novel.epub --chapters 1-8
ttsforge status novel.ttsforge --json
ttsforge convert novel.epub --project ./projects/novel
```

The chapter selection and setup are saved in the project. Choose a different project
path or use `--fresh` for a separate chapter selection:

```bash
ttsforge convert novel.epub --chapters 9-12 \
  --project ./projects/novel-part-two
```

## Discover choices and set up conversion

```bash
ttsforge engines
ttsforge targets --engine ENGINE --language en-us
ttsforge voices --engine ENGINE --target TARGET --language en-us
ttsforge convert novel.epub --engine ENGINE --target TARGET --voice VOICE
```

## Output and rebuild controls

```bash
ttsforge convert novel.epub --output ./audio/novel.m4b
ttsforge convert novel.epub --replace-output
ttsforge convert novel.epub --rebuild-from render
```

`--replace-output` authorizes replacing the final M4B. `--rebuild-from` asks Readio to
rebuild from a workflow stage. M4B is the supported final audiobook format.

## Python integrations

Use `readio.api` directly for typed workflow operations. TTSForge's adapter is an
internal implementation boundary, not a second public synthesis API. See the
[TTSForge API guide](../docs/api/index.md) and
[Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md).
