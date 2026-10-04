# Application architecture

TTSForge supports Readio `>=0.4.0,<0.5`. Readio owns projects, durable settings,
synthesis engines, composition, and export. TTSForge owns the audiobook-oriented request
policy and command-line interaction.

## Dependency direction

```text
Terminal commands and presenters (ttsforge.cli)
                    |
                    v
Synchronous application service (ttsforge.application)
                    |
                    v
           ApplicationBackend contract
                    ^
                    |
Readio adapter and DTO translation (ttsforge.readio_backend)
                    |
                    v
             readio.api 0.4
```

`ttsforge.application` has no dependency on Readio, Typer, Rich, or a GUI toolkit. Its
request and result models are frontend-neutral, its errors provide stable product
categories, and its events and progress reducer contain no terminal rendering. The
synchronous backend contract is fakeable for service tests and can be used by a future
frontend without adding that frontend to this migration.

`ttsforge.readio_backend` is the only production module that imports `readio.api`. It
translates public Readio DTOs, discovery queries, events, project operations, synthesis
settings, configuration, and SSMD authoring calls. It also turns Readio v0.3 migration
requirements and invalid workspaces into distinct actionable errors. TTSForge never
rewrites Readio-owned configuration or project state automatically.

## Conversion lifecycle

`AudiobookApplicationService` owns the synchronous product workflow:

1. Inspect the EPUB and find or prepare a managed project.
2. Preserve the existing project's chapter scope, or prepare a separate path for
   `--fresh`.
3. Load saved settings, merge them with explicitly supplied values, and invalidate
   dependent choices when language, engine, or model changes.
4. Resolve and persist synthesis settings before preflight and build confirmation.
5. Build only after confirmation. Declining confirmation leaves the project and saved
   setup available for a later non-interactive retry.

`ttsforge.cli` owns prompts, Rich tables, human-readable output, JSON serialization,
terminal progress, and confirmation. It delegates project preparation, setup merging,
resolution, persistence, preflight, and build to the application service. JSON mode
remains prompt-free.

`ttsforge.audiobook` retains `AudiobookConverter`, `ProjectSetup`, and preflight
compatibility imports. The converter can create an application service over its adapter;
existing Python callers do not need to construct a Readio adapter themselves.

## Scope

This boundary makes the workflow reusable, but this migration does not add a GUI, choose
a GUI toolkit, add background workers, or introduce frontend dependencies. A future
frontend can implement `ApplicationBackend` or use the existing Readio adapter without
moving terminal prompts into application code.
