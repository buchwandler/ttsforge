"""Lightweight SSMD inspection commands that never initialize ONNX."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..ssmd_support import SSMDPolicy, inspect_ssmd_document


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"unable to read SSMD file: {exc}") from exc


def validate(path: Path, strict: bool = False, as_json: bool = False) -> None:
    info = inspect_ssmd_document(_read(path), policy=SSMDPolicy(fail_on_warning=strict))
    payload = {
        "valid": not info.errors and (not strict or not info.warnings),
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "line": issue.line,
                "column": issue.column,
            }
            for issue in info.issues
        ],
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    else:
        if not info.issues:
            typer.echo("SSMD is valid.")
        for issue in info.issues:
            typer.echo(issue.format(path))
    if not payload["valid"]:
        raise typer.Exit(code=1)


def inspect(path: Path, as_json: bool = False) -> None:
    info = inspect_ssmd_document(_read(path), policy=SSMDPolicy())
    payload = {
        "title": info.title,
        "header": info.header,
        "header_keys": sorted(info.header),
        "voice_bindings": info.header.get("voice_bindings", {}).get("kokoro", {})
        if isinstance(info.header.get("voice_bindings"), dict)
        else {},
        "pause_defaults": info.header.get("pause_defaults"),
        "plain_text_characters": len(info.body),
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "line": issue.line,
                "column": issue.column,
            }
            for issue in info.issues
        ],
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str))
        return
    typer.echo(f"Title: {info.title or '(none)'}")
    typer.echo(f"Header keys: {', '.join(payload['header_keys']) or '(none)'}")
    typer.echo(f"Kokoro bindings: {len(payload['voice_bindings'])}")
    typer.echo(f"Plain-text characters: {len(info.body)}")
    for issue in info.issues:
        typer.echo(issue.format(path))


__all__ = ["inspect", "validate"]
