# Application architecture

TTSForge is a small audiobook product layer over Readio `>=0.6.7,<0.7`. Readio owns the
render workflow, persistent intent/profile formats, specialist integrations, stage
reuse, composition, and export. TTSForge owns the EPUB-facing CLI, project-directory
convention, setup prompts, and presentation.

## Dependency direction

```text
Terminal commands and presenters (ttsforge.cli)
                    |
                    v
Synchronous application service (ttsforge.application)
                    |
                    v
Readio adapter and presentation-focused translation
                    |
                    v
             readio.api
                    |
                    v
        Readio workflow gateway
```

The application layer coordinates setup persistence, read-only preflight, confirmation,
and render delegation. It does not depend on terminal rendering. The Readio adapter is
the only production integration seam and imports Readio through `readio.api` only.

## Conversion lifecycle

1. Inspect the EPUB through Readio's public source-inspection API.
2. Resolve the default or explicit TTSForge project directory and reject incompatible
   legacy project state without mutation.
3. Load saved intent/profile values and merge them with explicit CLI values, source
   metadata, Readio defaults, and any interactive selections.
4. Validate the completed setup and persist intent/profile through Readio before
   rendering.
5. Ask Readio to inspect the canonical render request and present its workflow plan.
6. After confirmation, delegate rendering and normalized progress events to Readio.

Readio is the authority for workflow status, stage selection, artifact reuse, and output
ownership. TTSForge does not inspect specialist artifacts or reconstruct Readio 0.4
project abstractions.

## Public API boundary

TTSForge supports its CLI as its product interface. `ttsforge.readio_backend` is
internal. Python integrations should use Readio's public `readio.api` directly; see the
[API guide](api/index.md).
