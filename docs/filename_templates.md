# Output paths (formerly filename templates)

Older TTSForge versions offered renderer-owned filename templates. Those settings were
part of the retired TTSForge pipeline and are not applied by the Readio-backed frontend.

## Choose an output path

The default output uses the EPUB filename stem and selected format. Override the exact
file path with `--output`:

```bash
ttsforge convert novel.epub
ttsforge convert novel.epub --format mp3 --output "./Author - Novel.mp3"
```

Quote paths containing spaces in your shell. Readio owns output artifacts, reuse, and
replacement safety; use `--force` only when you intend to replace an output according to
Readio's ownership rules.

## Choose a project path separately

Project state and exported audio are different paths. Use `--project` to place project
data and `--output` to place the final audiobook:

```bash
ttsforge convert novel.epub \
  --project novel-custom.readio \
  --output novel.m4b
```

The project's chapter selection is persistent. For a separate project variant, use
another `--project` path or `--fresh`. See [Projects and outputs](projects.md).

Old keys such as `output_filename_template`, `chapter_filename_template`, and
`phoneme_export_template` are not read or migrated. TTSForge no longer creates
TTSForge-owned chapter WAV/phoneme export workspaces.
