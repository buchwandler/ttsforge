# Local API server

TTSForge supports the CLI and the local HTTP API used by TTSForge Studio. The server is
a supported Studio interface, not a browser application: it does not include a browser
UI, Tauri shell, or frontend assets. Normal CLI use does not start a server or require
HTTP dependencies.

## Install and start

Install the `server` extra to add FastAPI, Pydantic, Uvicorn, and multipart upload
support:

```bash
python -m pip install "ttsforge[server]"
```

Provide a private bearer token through the `TTSFORGE_TOKEN` environment variable, or
pass it with `--token`:

```bash
export TTSFORGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
ttsforge serve --port 8765 --state-dir ~/.local/state/ttsforge
```

The server binds to `127.0.0.1` by default. `--host` accepts loopback addresses such as
`127.0.0.1`, `::1`, and `localhost`. Non-loopback addresses, including `0.0.0.0`, are
rejected. The default port is `8765`; pass `--port 0` to let the operating system choose
an available port.

At startup the process writes one JSON readiness record to stdout after the API has
started. The record contains `type` (`server.ready`), `host`, the actual `port`, and
`api_version`. Normal Uvicorn diagnostics are written to stderr. This makes port-zero
startup usable by a supervising desktop application without parsing log messages.

The same launcher is available through the module entry point:

```bash
python -m ttsforge.server \
  --host 127.0.0.1 \
  --port 8765 \
  --token "$TTSFORGE_TOKEN" \
  --state-dir ~/.local/state/ttsforge
```

Both commands accept `--host`, `--port`, `--token`, `--state-dir`, repeatable
`--allow-origin`, `--log-level`, and `--debug`. `TTSFORGE_TOKEN` can supply the token
when `--token` is omitted. Log levels are `critical`, `error`, `warning`, `info`,
`debug`, and `trace`.

If the server dependencies are missing, the launcher prints:

```text
The local API requires the TTSForge server extra.
Install with: uv pip install "ttsforge[server]"
```

The server logs an unexpected-error traceback only when `--debug` is enabled. The client
receives the same generic error response in either mode.

## Local security boundary

All `/api/v1` endpoints except `/api/v1/health` require `Authorization: Bearer <token>`.
The token is compared in constant time and is not written to normal logs.

The API accepts same-origin requests, the built-in Tauri origins `tauri://localhost`,
`https://tauri.localhost`, and `http://tauri.localhost`, and any additional origins
explicitly passed with `--allow-origin`. Repeat that option for multiple origins.
Wildcard origins are rejected, and credentialed CORS is disabled.

The API can inspect and import local files, so keep it on loopback and treat its bearer
token as a local capability. Do not expose it through a network interface or proxy it to
an untrusted browser.

The v1 OpenAPI 3.1 schema is checked in at
[`docs/api/openapi-v1.json`](api/openapi-v1.json). Swagger UI and ReDoc are disabled,
but `GET /openapi.json` publicly serves the runtime schema as contract metadata.
Protected API operations declare HTTP bearer authentication in both schemas.

## State and worker lifecycle

The default state directory is `~/.local/state/ttsforge`. Uploaded sources are stored
under `imports/<source_id>/<sanitized-filename>` with server-managed ownership metadata.
Uploads are limited to 2 GiB. Startup cleanup removes only unclaimed imports older than
the 30-day default retention period. Preflight and job submission claim imported
sources; claimed sources are not removed by startup cleanup and can be explicitly
deleted through the API.

Imports, managed projects, and outputs use separate directories. An imported source gets
`projects/<source_id>` and `outputs/<source_id>/<source-basename>.m4b` as default
project and output paths. Explicit client paths are preserved. A direct local source
path is not copied or owned by the server.

Conversion jobs are held in memory and run in isolated Python child processes. One job
is active at a time by default. Job status and bounded progress history are not
persisted, so restarting the server clears them. Cancelling a job terminates its worker
process tree; server shutdown also stops active workers.

Terminal job records are capped at 100. The oldest terminal jobs are pruned first;
queued, preparing, and running jobs are never pruned. `GET /api/v1/jobs` supports state,
limit, and an exclusive `before` job-ID cursor. Event pages report `first`, `next`, and
`truncated` so a Studio client can detect when bounded event history has dropped older
events.

See the [Studio API reference](studio-api.md) for endpoints and request formats.
