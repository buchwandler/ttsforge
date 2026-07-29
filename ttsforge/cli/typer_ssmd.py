"""Typer registration for lightweight SSMD commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

ssmd_app = typer.Typer(
    add_completion=False,
    help="Inspect and validate SSMD 0.8 documents without initializing ONNX.",
)


@ssmd_app.command("validate")
def validate_command(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    strict: Annotated[
        bool, typer.Option("--strict", help="Treat warnings as failures.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    from .commands_ssmd import validate

    validate(path, strict=strict, as_json=as_json)


@ssmd_app.command("inspect")
def inspect_command(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    from .commands_ssmd import inspect

    inspect(path, as_json=as_json)


def register(app: typer.Typer) -> None:
    app.add_typer(ssmd_app, name="ssmd")
