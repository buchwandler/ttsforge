# Application architecture

TTSForge is an audiobook product layer over Readio `>=0.6.7,<0.7`. It supports the CLI
and the local HTTP API used by TTSForge Studio. Readio owns the render workflow,
persistent intent/profile formats, specialist integrations, stage reuse, composition,
and export. TTSForge owns the EPUB-facing workflow, project-directory convention, setup
resolution, and frontend contracts.

## Dependency direction

```text
TTSForge CLI                 TTSForge Studio (local HTTP API)
     |                                     |
     v                                     v
CLI presenters                         HTTP transport, auth,
                                      DTOs, and job resources
     |                                     |
     +-----------------+-------------------+
                       v
         Synchronous application services
                       |
                       v
      Readio adapter and presentation mapping
                       |
                       v
                readio.api
                       |
                       v
             Readio workflow gateway
```

The application layer resolves setup, persists setup when requested, builds preflight
views, and delegates rendering. Preflight may save setup or ensure spaCy, but it never
renders. The application layer does not depend on terminal or HTTP rendering. The Readio
adapter is the only production integration seam and imports Readio through `readio.api`
only.

The server package owns HTTP authentication, strict transport DTOs, and job supervision.
It uses the same application services as the CLI and does not import the CLI package.

## Conversion lifecycle

1. Inspect the EPUB through Readio's public source-inspection API.
2. Resolve the default or explicit TTSForge project directory and reject incompatible
   legacy project state without mutation.
3. Load saved intent/profile values and merge them with explicit CLI or API values,
   source metadata, Readio defaults, and any interactive selections.
4. Validate the completed setup and persist intent/profile through Readio before
   rendering.
5. Ask Readio to inspect the canonical render request and present its workflow plan.
6. After confirmation, delegate rendering and normalized progress events to Readio.

Studio uses `POST /api/v1/setup/resolve` to display the resolved request without saving
it, then `POST /api/v1/conversions/preflight` to prepare setup and workflow before
confirmation. Preflight may persist setup, provision spaCy, claim an imported source,
and create the default output parent. Actual rendering only starts after a job is
submitted. Jobs run through isolated worker processes; the local API process retains
status and bounded event history. Readio is the authority for workflow status, stage
selection, artifact reuse, and output ownership. TTSForge does not inspect specialist
artifacts or reconstruct Readio 0.4 project abstractions.

## Public API boundary

TTSForge supports both the CLI and the local Studio HTTP API as product interfaces. The
versioned HTTP contract is documented in the [Studio API reference](studio-api.md), with
its checked-in schema at [openapi-v1.json](api/openapi-v1.json).
`ttsforge.readio_backend`, the application services, and application models remain
internal Python implementation details. Python integrations should use Readio's public
`readio.api` directly; see the [API guide](api/index.md).
