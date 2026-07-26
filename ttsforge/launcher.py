"""Resilient console-script launcher, aligned with Taskledger's entry boundary."""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from importlib import import_module
from typing import cast


def main() -> None:
    try:
        cli_module = import_module("ttsforge.cli")
        cli_main = cli_module.cli_main
        if not callable(cli_main):
            raise TypeError("ttsforge.cli.cli_main is not callable.")
    except Exception as exc:
        sys.stderr.write("ttsforge failed to import its CLI.\n")
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        sys.stderr.write("Run: python -m py_compile ttsforge/cli/__init__.py\n")
        if "--debug" in sys.argv:
            traceback.print_exc()
        raise SystemExit(1) from exc
    cast(Callable[[], None], cli_main)()
