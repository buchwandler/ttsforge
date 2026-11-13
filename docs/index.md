# TTSForge documentation

TTSForge is an audiobook-oriented command-line frontend for Readio. It inspects EPUBs,
saves audiobook setup in a TTSForge project directory, and delegates workflow planning
and M4B rendering to Readio.

TTSForge requires Readio `>=0.6.7,<0.7`. The base installation remains provider-neutral;
engine integrations are installed separately. See [Installation](installation.md).

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
application-architecture
changelog
Documentation sources <README>
```

```{toctree}
:maxdepth: 2
:caption: API Reference

api/index
```

## Workflow overview

```bash
ttsforge list novel.epub
ttsforge convert novel.epub
ttsforge status novel.ttsforge
```

The default project is `novel.ttsforge/` beside the EPUB. It contains a Readio render
intent, narrator profile, and persistent SSMD bundle. The default final output is
`novel.m4b`. Readio owns workflow state, reuse decisions, and rendering.

See the [Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md)
and [project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md)
for service details. TTSForge does not duplicate Readio's internal project schema or
engine documentation.

## License

TTSForge is released under the MIT License.

## Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
