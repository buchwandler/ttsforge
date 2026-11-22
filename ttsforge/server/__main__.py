"""Run the TTSForge Studio API with ``python -m ttsforge.server``."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the TTSForge local API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, choices=range(0, 65536), default=8765)
    parser.add_argument("--token", default=os.environ.get("TTSFORGE_TOKEN"))
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        help="Explicitly allow a browser origin. May be repeated.",
    )
    parser.add_argument(
        "--log-level",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        default="info",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("--token is required (or set TTSFORGE_TOKEN).")

    from .launcher import run_server

    run_server(
        host=args.host,
        port=args.port,
        token=args.token,
        state_dir=args.state_dir,
        allowed_origins=args.allow_origin,
        log_level=args.log_level,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
