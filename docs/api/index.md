# Python API boundary

TTSForge supports the command line and the local HTTP API used by TTSForge Studio as
product interfaces. Its application services, adapter, and models are implementation
details, not a separate supported Python project or synthesis API.

The versioned Studio contract is documented in the
[Studio API reference](../studio-api.md); the [OpenAPI 3.1 schema](openapi-v1.json) is
checked in with the source documentation.

The Studio library endpoints expose project discovery and summaries. The TTSForge
audiobook Skill and its CLI, project, narration, and QC references are packaged with the
distribution.

Python integrations should use Readio's public `readio.api` workflow gateway. TTSForge
requires Readio `>=0.6.8,<0.7` and uses its typed source-inspection, render-intent,
profile, discovery, workflow-inspection, and render operations.

## Inspect and render a saved intent

A TTSForge project contains a Readio render intent. A direct Readio integration can load
it, build the canonical request, inspect the proposed workflow, and render through the
same gateway:

```python
from pathlib import Path

from readio.api import Readio, load_render_intent

project = Path("novel.ttsforge")
readio = Readio()
intent = load_render_intent(project / "render.readio.toml")
request = readio.request_from_intent(intent)

plan = readio.inspect(request)
for step in plan.steps:
    print(step.stage, step.action, step.reason)

result = readio.render(request)
print(result.output)
```

`Readio.inspect()` is the read-only workflow preflight. `Readio.render()` executes the
request and emits public `WorkflowEvent` progress through its callback when one is
provided. Request options, output ownership, and workflow-stage semantics belong to
Readio.

## TTSForge integration boundary

Production TTSForge code imports Readio only through `readio.api`. The adapter
translates TTSForge's audiobook choices to Readio request types and maps normalized
workflow events and errors for CLI presentation. It does not call specialist packages
directly or reproduce Readio's workflow-state decisions.

Use the [Readio API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md)
and [project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md)
for the complete public contract. See [Installation](../installation.md) for the
dependency floor and development setup.
