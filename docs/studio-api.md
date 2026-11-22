# TTSForge Studio API

The local HTTP API is the supported TTSForge Studio contract at `/api/v1`. Install and
start the server as described in [Local API server](server.md). All versioned API paths
below include the `/api/v1` prefix. JSON request models reject unknown fields and
non-JSON values.

The local API is the supported HTTP interface for TTSForge Studio. It shares application
services with the CLI without making the HTTP server depend on CLI code. The versioned
OpenAPI 3.1 contract is checked in as [openapi-v1.json](api/openapi-v1.json). Runtime
Swagger UI and ReDoc are disabled. `GET /openapi.json` still serves the runtime schema
publicly as contract metadata. The checked-in, versioned copy is used for Studio tooling
and source documentation.

## Authentication and errors

Every `/api/v1` endpoint except `GET /api/v1/health` requires this header:

```text
Authorization: Bearer YOUR_TOKEN
```

The token is supplied when starting the server. The health endpoint returns
`{"ok": true}` and is an unauthenticated liveness endpoint. `GET /api/v1/system` returns
the API major version and supported capabilities. A client should check `api_version`
before relying on this contract.

Application errors use a structured body:

```json
{
  "error": {
    "type": "InputValidationError",
    "message": "A request value is invalid.",
    "category": null,
    "code": null,
    "stage": null,
    "package": null,
    "selector": null,
    "details": {}
  }
}
```

Authentication failures return HTTP 401 with `WWW-Authenticate: Bearer`. Invalid request
shapes and application inputs return HTTP 400, project conflicts return 409, blocked
workflows and ordinary workflow failures return 422, and unavailable offline resources
can return 503. Missing resources or jobs return 404. Oversized imports return 413.
Validation and framework-generated HTTP errors use the same error envelope shown above.
Unexpected server failures always return a generic response. `--debug` adds a
server-side traceback to logs; it does not expose exception details to the client.

## System and runtime

| Method and path              | Purpose                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| `GET /api/v1/health`         | Unauthenticated liveness and startup check.                          |
| `GET /api/v1/system`         | API version, TTSForge and Python versions, and capabilities.         |
| `GET /api/v1/system/runtime` | Normalized Python, package, AudioExport, FFmpeg, and FFprobe status. |

The capability map includes `jobs`, `job_events`, `cancel`, `source_upload`,
`setup_resolve`, `preflight`, `project_setup`, `spacy_ensure`, and `speech_profiles`.
Studio can use these flags rather than inferring support from installed packages.

`GET /api/v1/system` returns a capability map. This example advertises the complete
current Studio surface:

```json
{
  "api_version": 1,
  "ttsforge_version": "0.5.0",
  "python_version": "3.13.0",
  "capabilities": {
    "jobs": true,
    "job_events": true,
    "cancel": true,
    "source_upload": true,
    "setup_resolve": true,
    "preflight": true,
    "project_setup": true,
    "spacy_ensure": true,
    "speech_profiles": true
  }
}
```

The runtime response contains no environment variables. It reports `ready` and a
`problems` list with actionable missing-dependency codes and messages. Tool paths and
availability are reported, but the API does not install or download FFmpeg.

```json
{
  "python": {"version": "3.13.0", "executable": "/usr/bin/python"},
  "packages": {"ttsforge": "0.5.0", "readio": "0.6.7"},
  "audio": {
    "audioexport": {"available": true, "version": "0.1.8"},
    "ffmpeg": {"available": true, "path": "/usr/bin/ffmpeg"},
    "ffprobe": {"available": false, "path": null}
  },
  "ready": false,
  "problems": [
    {"code": "ffprobe_missing", "message": "ffprobe is not installed or not on PATH."}
  ]
}
```

## Sources, catalog, and projects

| Method and path                                  | Request or query                                              | Purpose                                                                                                       |
| ------------------------------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `POST /api/v1/sources/inspect`                   | JSON `{ "path": "/books/book.epub" }`                         | Inspect a readable local source without creating a project.                                                   |
| `POST /api/v1/sources/import`                    | Multipart form field `file`                                   | Copy and inspect an uploaded book. The response includes `source_id`, the stored `path`, and inspection data. |
| `GET /api/v1/sources/imports/{source_id}`        | `source_id`                                                   | Read managed import ownership and retention metadata.                                                         |
| `DELETE /api/v1/sources/imports/{source_id}`     | `source_id`                                                   | Explicitly delete a server-managed import.                                                                    |
| `GET /api/v1/catalog/engines`                    | None                                                          | List Readio-discovered engines.                                                                               |
| `GET /api/v1/catalog/targets`                    | `engine`, optional `language`, `offline`, `refresh`           | List available targets for an engine.                                                                         |
| `GET /api/v1/catalog/voices`                     | `engine`, `target`, optional `language`, `offline`, `refresh` | List voices available for a target.                                                                           |
| `GET /api/v1/catalog/engine-options`             | `engine`, optional `target`                                   | Describe engine-specific options.                                                                             |
| `GET /api/v1/resources/spacy`                    | `language`                                                    | List normalized spaCy model availability.                                                                     |
| `POST /api/v1/resources/spacy/ensure`            | JSON `{ "language": "en", "tier": "lg", "offline": false }`   | Inspect or provision the requested model through Readio.                                                      |
| `GET /api/v1/resources/speech-profiles`          | `directory`                                                   | Discover valid speech replacement profiles in one directory.                                                  |
| `POST /api/v1/resources/speech-profiles/inspect` | JSON `{ "path": "/profiles/custom.toml" }`                    | Validate one profile.                                                                                         |
| `GET /api/v1/projects/status`                    | `project` path                                                | Inspect workflow status for a project.                                                                        |
| `GET /api/v1/projects/variants`                  | `project` path, optional `source` path                        | List alternate project setups.                                                                                |
| `GET /api/v1/projects/setup`                     | `project`, optional `variant`                                 | Read the saved base or variant setup.                                                                         |
| `GET /api/v1/projects/info`                      | `project`                                                     | Read saved setup, workflow plan, and variant summaries.                                                       |
| `POST /api/v1/setup/resolve`                     | Job-style request body                                        | Resolve setup without saving it or starting conversion.                                                       |
| `POST /api/v1/conversions/preflight`             | Job-style request body                                        | Prepare setup and workflow without rendering.                                                                 |

### Example catalog responses

Each catalog route returns a complete array of its response DTO. Representative results:

```json
[
  {
    "id": "kokoro",
    "version": "1.0",
    "installed": true,
    "runnable": true,
    "features": ["voices"],
    "reason": null
  }
]
```

```json
[
  {
    "id": "target-a",
    "languages": ["en-US"],
    "status": "available",
    "runtime_available": true,
    "default_voice": "voice-a",
    "voice_count": 1,
    "qualities": [],
    "voice_mode": "named",
    "sample_rate": 24000,
    "features": ["voices"],
    "reference_only": false
  }
]
```

```json
[
  {
    "id": "voice-a",
    "language": "en-US",
    "locale": "en-US",
    "language_label": "English",
    "gender": "female",
    "default": true,
    "runtime_available": true
  }
]
```

```json
[
  {
    "name": "quality",
    "value_type": "string",
    "required": false,
    "default": "standard",
    "choices": ["standard", "high"],
    "minimum": null,
    "maximum": null,
    "description": "Synthesis quality",
    "identity_affecting": true,
    "runtime_only": false
  }
]
```

`GET /api/v1/resources/spacy` returns an array of these model records. The ensure route
returns one record with the same fields:

```json
[
  {
    "language": "en-US",
    "tier": "lg",
    "model": "en_core_web_lg",
    "installed": true,
    "spacy_version": "3.8",
    "model_version": "3.8.0"
  }
]
```

Uploads are limited to 2 GiB. An imported file is stored at
`<state-dir>/imports/<source_id>/<sanitized-filename>` with metadata recorded by the
server. The default state directory is `~/.local/state/ttsforge`. Unclaimed imports
older than the configured retention period (30 days by default) are removed at server
startup. Claimed imports are never removed by startup cleanup and can be deleted
explicitly through the source-delete route.

When an imported source has no explicit project or output path, TTSForge allocates
`<state-dir>/projects/<source_id>` and
`<state-dir>/outputs/<source_id>/<source-basename>.m4b`. Imports, managed projects, and
outputs are separate. Local source paths supplied directly by a client are not copied or
owned by the server. Incoming `~` path prefixes are expanded at the HTTP boundary.

A source status response contains `source_id`, `path`, `managed`, `temporary`,
`retention_days`, `claimed`, `created_at`, and `last_used_at`. The upload response adds
an `inspection` object with source metadata and chapter entries. Explicit deletion
returns `{ "source_id": "abc123", "deleted": true }`. A source is claimed when preflight
or job submission uses it. Setup resolution alone does not claim it.

```json
{
  "source_id": "abc123",
  "path": "/state/imports/abc123/book.epub",
  "managed": true,
  "temporary": false,
  "retention_days": 30,
  "claimed": true,
  "created_at": "2025-01-01T12:00:00+00:00",
  "last_used_at": "2025-01-01T12:10:00+00:00"
}
```

The upload response has the same fields plus a complete `inspection` object:

```json
{
  "source_id": "abc123",
  "path": "/state/imports/abc123/book.epub",
  "managed": true,
  "temporary": true,
  "retention_days": 30,
  "claimed": false,
  "created_at": "2025-01-01T12:00:00+00:00",
  "last_used_at": null,
  "inspection": {
    "source": "/state/imports/abc123/book.epub",
    "kind": "book",
    "title": "A Book",
    "author": "An Author",
    "language": "en",
    "chapters": [
      {"number": 1, "title": "Chapter 1", "source_id": "chapter-1", "char_count": 1200}
    ],
    "cover": null
  }
}
```

`POST /api/v1/sources/inspect` returns the same complete `inspection` object by itself,
without import lifecycle metadata.

## Setup, preflight, and project inspection

`POST /api/v1/setup/resolve` accepts the same
`{ "request": ..., "explicit_fields": [...] }` shape as job submission. It returns the
resolved project, variant, source inspection, resolved request, and field origins.
Resolution is read-only: it does not save setup, claim an import, create output
directories, or render.

`POST /api/v1/conversions/preflight` returns the proposed workflow and any requested
spaCy model state. It may persist setup, provision spaCy, claim an imported source, and
create the default output parent. It never calls the render/execute operation. Use this
endpoint before asking the user to confirm a conversion.

Example resolved setup response:

```json
{
  "project": "/state/projects/abc123",
  "configuration_variant": null,
  "reused_setup": false,
  "inspection": {
    "source": "/state/imports/abc123/book.epub",
    "kind": "book",
    "title": "A Book",
    "author": "An Author",
    "language": "en",
    "chapters": [
      {"number": 1, "title": "Chapter 1", "source_id": "chapter-1", "char_count": 1200}
    ],
    "cover": null
  },
  "request": {
    "source": "/state/imports/abc123/book.epub",
    "project": "/state/projects/abc123",
    "chapters": null,
    "output": "/state/outputs/abc123/book.m4b",
    "language": "en",
    "engine": null,
    "target": null,
    "voice": null,
    "engine_options": {},
    "speed": null,
    "spacy": null,
    "speech_profile": null,
    "pause_timing": null,
    "bitrate": null,
    "target_lufs": null,
    "title": "A Book",
    "author": "An Author",
    "cover": null,
    "offline": false,
    "refresh": false,
    "rebuild_from": null,
    "replace_output": false,
    "fresh": false,
    "new_variant": false
  },
  "origins": {"explicit": [], "project": [], "derived": []}
}
```

A preflight response has this complete shape. `spacy_model` is null when spaCy is not
requested.

```json
{
  "project": "/state/projects/abc123",
  "configuration_variant": null,
  "reused_setup": false,
  "spacy_model": {
    "language": "en",
    "tier": "lg",
    "model": "en_core_web_lg",
    "installed": true,
    "spacy_version": "3.8",
    "model_version": "3.8.0"
  },
  "request": {
    "source": "/state/imports/abc123/book.epub",
    "project": "/state/projects/abc123",
    "chapters": null,
    "output": "/state/outputs/abc123/book.m4b",
    "language": "en",
    "engine": "kokoro",
    "target": "voice-target",
    "voice": "voice-a",
    "engine_options": {},
    "speed": null,
    "spacy": "lg",
    "speech_profile": null,
    "pause_timing": null,
    "bitrate": null,
    "target_lufs": null,
    "title": "A Book",
    "author": "An Author",
    "cover": null,
    "offline": false,
    "refresh": false,
    "rebuild_from": null,
    "replace_output": false,
    "fresh": false,
    "new_variant": false
  },
  "workflow": {
    "source": "/state/imports/abc123/book.epub",
    "workspace": "/state/projects/abc123",
    "workspace_mode": "modern",
    "output": "/state/outputs/abc123/book.m4b",
    "steps": [
      {
        "stage": "render",
        "package": "voicerender",
        "action": "execute",
        "selector": "all",
        "reason": "The selected render stage is required.",
        "state": "ready"
      }
    ],
    "warnings": [],
    "variant": null
  }
}
```

`GET /api/v1/projects/setup?project=...&variant=...` reads saved setup.
`GET /api/v1/projects/info?project=...` combines saved setup, the current workflow plan,
and variant summaries. Neither endpoint renders.

For an empty project, setup and info responses are:

```json
{"project": "/projects/book.ttsforge", "variant": null, "saved_setup": null}
```

```json
{
  "project": "/projects/book.ttsforge",
  "saved_setup": null,
  "workflow": null,
  "variants": []
}
```

`GET /api/v1/projects/status` returns the complete workflow plan.
`GET /api/v1/projects/variants` returns variant summaries:

```json
{
  "source": "/books/book.epub",
  "workspace": "/projects/book.ttsforge",
  "workspace_mode": "modern",
  "output": "/books/book.m4b",
  "steps": [],
  "warnings": [],
  "variant": null
}
```

```json
[
  {
    "variant_key": "kokoro-en-voice-a",
    "output": null,
    "engine": "kokoro",
    "target": "target-a",
    "voice": "voice-a",
    "error": null
  }
]
```

Speech profile discovery is also available to Studio without importing the CLI package:

```json
{
  "directory": "/profiles",
  "profiles": [{"path": "/profiles/custom.toml", "name": "custom.toml"}]
}
```

The inspect route returns `{ "path": "/profiles/custom.toml", "valid": true }`.
Discovery is non-recursive and only returns TOML files with the supported SSMDConvert
profile schema.

## Conversion jobs

Jobs use the same `ConversionCoordinator` as the CLI. Setup, validation, preflight, and
execution remain in the application layer, and Readio owns workflow planning and
rendering.

### Submit a job

`POST /api/v1/jobs` accepts a `request` object and an optional list of
`explicit_fields`. Path values are strings in JSON and become `Path` values at the
application boundary. `explicit_fields` records which request values the caller
selected. Each entry must be a unique field name from the request model.

```json
{
  "request": {
    "source": "/books/Platform Decay.epub",
    "project": null,
    "chapters": "5-17",
    "output": "/books/Platform Decay.m4b",
    "language": "en-US",
    "engine": "kokoro",
    "target": "akinvox-multispeaker-v1",
    "voice": "AV_cori",
    "engine_options": {},
    "speed": null,
    "spacy": "lg",
    "speech_profile": null,
    "pause_timing": "engaging",
    "bitrate": null,
    "target_lufs": -18.0,
    "title": "Platform Decay",
    "author": "Martha Wells",
    "cover": null,
    "offline": false,
    "refresh": false,
    "rebuild_from": null,
    "replace_output": false,
    "fresh": false,
    "new_variant": false
  },
  "explicit_fields": ["chapters", "engine", "target", "voice"]
}
```

A successful submission returns HTTP 202:

```json
{"id": "<job-id>", "state": "queued"}
```

For example:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/jobs \
  -H "Authorization: Bearer $TTSFORGE_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @job.json
```

### List jobs

`GET /api/v1/jobs` lists job summaries without event histories. It accepts optional
`state`, `limit` (default 50, maximum 100), and `before` parameters. Results are newest
first. Use the last job `id` from one page as the exclusive `before` cursor for the next
page.

```json
{
  "jobs": [
    {
      "id": "9d2b...",
      "state": "completed",
      "created_at": "2025-01-01T12:00:00+00:00",
      "started_at": "2025-01-01T12:00:01+00:00",
      "finished_at": "2025-01-01T12:04:00+00:00",
      "project": "/books/book.ttsforge",
      "output": "/books/book.m4b",
      "event_sequence": 42
    }
  ]
}
```

At most 100 terminal jobs are retained. When this limit is exceeded, the oldest terminal
records are removed. Queued, preparing, and running jobs are never pruned. Job records
and event history remain in memory only and are cleared when the server restarts.

### Poll status

`GET /api/v1/jobs/{job_id}` returns the current state, timestamps, resolved project and
output paths, latest progress event, result or structured error, and the latest event
sequence number. States are `queued`, `preparing`, `running`, `completed`, `failed`, and
`cancelled`.

The `progress` value is the latest normalized application event. Its fields include
`stage`, `kind`, optional `message`, `package`, and `selector`, optional `current` and
`total`, `elapsed_seconds`, and chapter information in `details`. Consumers should use
these stage values directly. Do not average stage progress into a synthetic overall
percentage.

A completed job has a `result` containing the output path, workspace, workspace mode,
executed and reused stages, warnings, and variant information. Failed jobs have an
`error` with the normalized application error fields. The unused `result` or `error` is
`null`.

### Poll events

`GET /api/v1/jobs/{job_id}/events?after=N` returns retained events whose sequence is
strictly greater than `N`. `first` is the earliest retained sequence, `next` is the
latest sequence, and `truncated` is true when `N < first - 1`.

```json
{
  "first": 151,
  "next": 220,
  "truncated": true,
  "events": [
    {
      "seq": 220,
      "timestamp": "2025-01-01T12:00:01+00:00",
      "event": {
        "type": "workflow.event",
        "event": {
          "stage": "render",
          "kind": "stage.progress",
          "message": null,
          "package": null,
          "selector": null,
          "current": 2,
          "total": 3,
          "elapsed_seconds": 4.5,
          "details": {"chapter_number": 6}
        }
      }
    }
  ]
}
```

When `truncated` is true, refresh `GET /api/v1/jobs/{job_id}` for current status and
continue from `next`. Event history is bounded per job. State, prepared, and workflow
events have distinct payloads, all inside the `event` field. Events use the application
event model rather than CLI or terminal text.

### Cancel a job

`POST /api/v1/jobs/{job_id}/cancel` requests cancellation and returns the resulting job
status. The server terminates the isolated worker process tree, waits briefly, and
escalates to a kill if needed. The server remains running. Cancelling a terminal job
returns its current status; an unknown ID returns 404.

Jobs and event history are in memory only. A server restart clears them. The MVP runs
one conversion worker at a time and does not provide pause or resume.

## Versioning

Within `/api/v1`, additive response fields and endpoints are compatible changes.
Existing field meanings are not changed, and removals or incompatible changes require a
new API major version. Clients should handle unknown additive fields and enum values
defensively.
