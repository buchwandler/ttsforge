# Output paths

Earlier TTSForge versions offered renderer-owned filename templates. The v0.5 audiobook
workflow does not read or migrate those settings. Readio owns generated workspace
artifacts; TTSForge exposes the final M4B output path.

## Choose an output path

The default output uses the source filename stem with the `.m4b` extension. Override the
path with `--output`:

```bash
ttsforge convert novel.epub
ttsforge convert novel.epub --output "./audio/Author - Novel.m4b"
```

Quote paths containing spaces in your shell. To replace an existing M4B, pass
`--replace-output`; TTSForge does not silently authorize replacement.

## Choose a project path separately

Project state and exported audio are separate paths. Use `--project` for the project
directory and `--output` for the final M4B:

```bash
ttsforge convert novel.epub \
  --project ./projects/novel-custom \
  --output ./audio/novel.m4b
```

Old renderer filename-template keys and generated chapter-audio paths are not imported.
See [Projects and outputs](projects.md).
