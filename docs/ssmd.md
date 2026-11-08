# SSMD and Readio

TTSForge's v0.5 CLI does not provide standalone SSMD check, validation, analysis,
roundtrip, or materialization commands. The audiobook workflow delegates SSMD
compilation and rendering to Readio through the public workflow gateway.

The persistent `book.ssmd-bundle/` is part of a TTSForge project and is managed by
Readio and its workflow integrations. TTSForge does not implement an independent SSMD
renderer or authoring service.

For Python integrations that need SSMD authoring or analysis, use the corresponding
public API documented by Readio. SSMD syntax and semantics are defined by the
[SSMD project](https://github.com/buchwandler/ssmd). See the
[Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md) for
current service details.
