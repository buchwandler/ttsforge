# TTSForge Studio API

The optional local API is a versioned frontend contract at `/api/v1`. Install and start
the server as described in [Local API server](server.md). All paths below include the
`/api/v1` prefix. JSON request models reject unknown fields and non-JSON values.

## Authentication and errors

Every `/api/v1` endpoint except `GET /api/v1/health` requires this header:

```text
Authorization: Bearer YOUR_TOKEN
```

The token is supplied when starting the server. The health endpoint returns
`{"ok": true}` and is intended for readiness checks. `GET /api/v1/system` returns the
API major version and supported capabilities. A client should check `api_version` before
relying on this contract.

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

Authentication failures return HTTP 401. Invalid application inputs return 400, project
conflicts return 409, blocked workflows and ordinary workflow failures return 422, and
unavailable offline resources can return 503. Missing jobs return 404. Oversized imports
return 413. Unexpected server failures return a generic message unless debug mode is
enabled.

## System and runtime

| Method and path              | Purpose                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| `GET /api/v1/health`         | Unauthenticated liveness and startup check.                          |
| `GET /api/v1/system`         | API version, TTSForge and Python versions, and capabilities.         |
| `GET /api/v1/system/runtime` | Normalized Python, package, AudioExport, FFmpeg, and FFprobe status. |

The runtime response contains no environment variables. Tool paths and availability are
reported, but the API does not install or download FFmpeg.

## Sources, catalog, and projects

| Method and path                       | Request or query                                              | Purpose                                                                                                       |
| ------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `POST /api/v1/sources/inspect`        | JSON `{ "path": "/books/book.epub" }`                         | Inspect a readable local source without creating a project.                                                   |
| `POST /api/v1/sources/import`         | Multipart form field `file`                                   | Copy and inspect an uploaded book. The response includes `source_id`, the stored `path`, and inspection data. |
| `GET /api/v1/catalog/engines`         | None                                                          | List Readio-discovered engines.                                                                               |
| `GET /api/v1/catalog/targets`         | `engine`, optional `language`, `offline`, `refresh`           | List available targets for an engine.                                                                         |
| `GET /api/v1/catalog/voices`          | `engine`, `target`, optional `language`, `offline`, `refresh` | List voices available for a target.                                                                           |
| `GET /api/v1/catalog/engine-options`  | `engine`, optional `target`                                   | Describe engine-specific options.                                                                             |
| `GET /api/v1/resources/spacy`         | `language`                                                    | List normalized spaCy model availability.                                                                     |
| `POST /api/v1/resources/spacy/ensure` | JSON `{ "language": "en", "tier": "lg", "offline": false }`   | Inspect or provision the requested model through Readio.                                                      |
| `GET /api/v1/projects/status`         | `project` path                                                | Inspect workflow status for a project.                                                                        |
| `GET /api/v1/projects/variants`       | `project` path, optional `source` path                        | List alternate project setups.                                                                                |

The upload limit is 2 GiB. Imported files are placed under the server state directory,
not inside a TTSForge project. The default state directory is `~/.local/state/ttsforge`;
imports older than 30 days are removed at server startup.

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
strictly greater than `N`. The response's `next` value is the job's latest sequence
number. Use that value as the next cursor:

```json
{
  "next": 3,
  "events": [
    {
      "seq": 2,
      "timestamp": "2025-01-01T12:00:00+00:00",
      "event": {"type": "job.state", "state": "running"}
    },
    {
      "seq": 3,
      "timestamp": "2025-01-01T12:00:01+00:00",
      "event": {"stage": "render", "kind": "stage.progress"}
    }
  ]
}
```

Event history is bounded per job. Events use the application event model rather than CLI
or terminal text.

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
