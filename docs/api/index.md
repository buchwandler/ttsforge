# Python API boundary

TTSForge's supported product interface is its command line. The application adapter and
application models are implementation details, not a second public project or synthesis
API.

Python integrations should use Readio's public `readio.api` workflow gateway. TTSForge
requires Readio `>=0.6.7,<0.7` and uses its typed source-inspection, render-intent,
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
