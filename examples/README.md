# TTSForge examples

These examples use the TTSForge CLI and Readio-backed workflows. There are no TTSForge
examples that import PyKokoro or implement a renderer directly; synthesis, project
state, and exports belong to Readio.

## Inspect before creating a project

```bash
ttsforge list novel.epub --json > chapters.json
ttsforge info novel.epub --json > book.json
```

## Create, inspect, and resume through a Readio project

```bash
ttsforge convert novel.epub --chapters 1-8
ttsforge status novel.readio --json
ttsforge convert novel.epub --project novel.readio
```

The selected chapter scope is persisted in the project. Use a second project path for
another selection rather than expecting a reused project's scope to change:

```bash
ttsforge convert novel.epub --chapters 9-12 \
  --project novel-part-two.readio
```

## Preview and export

```bash
ttsforge preview novel.epub --selection first:3
ttsforge formats --json
ttsforge convert novel.epub --format mp3 --output novel.mp3
```

The available formats depend on the installed Readio services and local encoders. M4B
uses Readio's distinct audiobook export service.

## Python integrations

Use `readio.api` directly for typed project and export operations. TTSForge's Python
adapter is an internal implementation boundary, not a second public synthesis API. See
[the API guide](../docs/api/index.md) and
[Readio's API examples](https://github.com/buchwandler/readio/blob/main/docs/api.md).
