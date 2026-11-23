# TTSForge documentation

TTSForge is an audiobook workflow product over Readio. It inspects EPUBs, resolves
audiobook setup in a TTSForge project directory, and delegates workflow planning and M4B
rendering to Readio. TTSForge supports its CLI and a local HTTP API for Studio.

The supported local HTTP API is Studio's backend interface. It is installed separately
and does not change the CLI workflow. See the [server guide](server.md), the
[Studio API reference](studio-api.md), and the checked-in
[OpenAPI schema](api/openapi-v1.json).

TTSForge requires Readio `>=0.6.8,<0.7`. The base installation remains provider-neutral;
engine integrations are installed separately. See [Installation](installation.md).

```{toctree}
:maxdepth: 2
:caption: User Guide

installation
migration-readio
Historical migration notes <migration-v0.4>
quickstart
cli
server
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
studio-api
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
