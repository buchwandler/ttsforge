"""Shared optional-dependency launcher for the local API."""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, NoReturn


def _is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str,
    state_dir: Path | None = None,
    log_level: Literal[
        "critical", "error", "warning", "info", "debug", "trace"
    ] = "info",
    debug: bool = False,
    allowed_origins: Sequence[str] = (),
) -> None:
    if not _is_loopback_host(host):
        _startup_error(
            ValueError("The local API can bind only to a loopback host."),
            debug=debug,
        )
    try:
        import uvicorn

        from .app import _API_VERSION, create_app
    except ModuleNotFoundError as error:
        if error.name not in {
            "fastapi",
            "multipart",
            "pydantic",
            "starlette",
            "uvicorn",
        }:
            _startup_error(error, debug=debug)
        _dependency_error(error, debug=debug)

    listener: socket.socket | None = None
    try:
        app = create_app(
            token=token,
            state_dir=state_dir,
            allowed_origins=allowed_origins,
            debug=debug,
        )
        listener = socket.create_server((host, port), backlog=2048)
        ready = {
            "type": "server.ready",
            "host": host,
            "port": listener.getsockname()[1],
            "api_version": _API_VERSION,
        }
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=False,
        )

        class ReadinessServer(uvicorn.Server):
            async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                await super().startup(sockets=sockets)
                if self.started:
                    print(json.dumps(ready, separators=(",", ":")), flush=True)

        ReadinessServer(config).run(sockets=[listener])
    except Exception as error:
        _startup_error(error, debug=debug)
    finally:
        if listener is not None:
            listener.close()


def _dependency_error(error: ModuleNotFoundError, *, debug: bool) -> NoReturn:
    print("The local API requires the TTSForge server extra.", file=sys.stderr)
    print('Install with: uv pip install "ttsforge[server]"', file=sys.stderr)
    if debug:
        traceback.print_exception(error)
    raise SystemExit(1) from error


def _startup_error(error: Exception, *, debug: bool) -> NoReturn:
    print(
        f"Unable to start the TTSForge local API: {type(error).__name__}: {error}",
        file=sys.stderr,
    )
    if debug:
        traceback.print_exception(error)
    raise SystemExit(1) from error
