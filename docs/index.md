# TTSForge documentation

TTSForge is an audiobook-focused command-line frontend for Readio. Readio owns the
persistent project lifecycle, synthesis engines, composition, reuse, and exports;
TTSForge presents an EPUB audiobook workflow and maps choices to Readio's public
services.

TTSForge requires Readio `>=0.3.1`, whose public API supplies its audiobook project,
synthesis preflight, and export workflows. See [Installation](installation.md) for user
and development setup.

```{toctree}
:maxdepth: 2
:caption: User Guide

installation
migration-readio
Historical migration notes <migration-v0.4>
quickstart
cli
projects
configuration
voices
ssmd
filename_templates
testing
changelog
```

```{toctree}
:maxdepth: 2
:caption: API Reference

api/index
```

## Workflow overview

```bash
ttsforge list novel.epub
ttsforge preview novel.epub
ttsforge convert novel.epub
ttsforge status novel.readio
```

TTSForge creates or reuses a Readio project, normally `<book-stem>.readio` beside the
EPUB. Readio manages project state and decides which work can be reused. M4B is produced
through Readio's audiobook export service; generic formats use its project export
service.

See the [Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md)
and [project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md)
for service details. TTSForge deliberately does not duplicate Readio's internal project
schema or engine documentation. For reproducible command-line recipes, see the
[TTSForge examples](https://github.com/buchwandler/ttsforge/blob/main/examples/README.md).

## License

TTSForge is released under the MIT License.

## Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
