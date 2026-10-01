# Python API boundary

The supported TTSForge interface is its command line. TTSForge is intentionally a small
product layer over Readio rather than a second Python synthesis/project API. Its
internal adapter modules are implementation details and may change with the Readio
contract.

For Python integrations, use Readio's public API directly. It exposes typed inspection,
project, build, audiobook export, catalog, diagnostics, configuration, and SSMD
services:

```python
from pathlib import Path

from readio.api import Readio

app = Readio()
source = Path("novel.epub")

inspection = app.audiobooks.inspect(source)
print(inspection.metadata)
print([chapter.title for chapter in inspection.chapters])

created = app.audiobooks.create_project_result(
    source,
    chapters="1-5",
    output=Path("novel.readio"),
)
status = app.projects.status(created.project)
print(status.next_actions)
```

Readio `>=0.3.5` provides this public API, including expanded synthesis resolution and
persisted project settings. See [Installation](../installation.md) for the standard
package install and optional source-development setup.

## Audiobook export

Readio keeps M4B audiobook export distinct from generic audio export. A typical API
integration creates a project, builds composition, then calls the audiobook service.
Request types, defaults, output ownership, and build stages are documented by Readio; do
not duplicate those contracts in TTSForge code or assume that generic export handles
M4B.

See
[Readio's API guide](https://github.com/buchwandler/readio/blob/main/docs/api.md#projects-and-audiobooks)
and [project guide](https://github.com/buchwandler/readio/blob/main/docs/projects.md).

## TTSForge integration boundary

The implementation imports only `readio.api` for Readio integration. TTSForge's
audiobook options are translated at that boundary into Readio request types; progress
events are presented to CLI users without taking ownership of project state. The API
contract test verifies the public API version and required symbols used by the current
adapter.
