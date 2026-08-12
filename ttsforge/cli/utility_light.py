"""Utility commands that can be declared without importing the TTS backend."""

from __future__ import annotations

import json
import warnings
from typing import Any

import typer
from rich.table import Table

from ..constants import (
    DEFAULT_CONFIG,
    DEFAULT_VOICE_FOR_LANG,
    LANGUAGE_DESCRIPTIONS,
    VOICE_PREFIX_TO_LANG,
    VOICES,
)
from ..utils import (
    load_config,
    parse_config_cli_value,
    reset_config,
    save_config,
    validate_config_value,
)
from .helpers import console


def voices(language: str | None) -> None:
    """List available TTS voices without loading provider code."""
    table = Table(title="Available Voices")
    table.add_column("Voice", style="bold")
    table.add_column("Language")
    table.add_column("Gender")
    table.add_column("Default", style="dim")
    for voice in VOICES:
        prefix = voice[:2]
        lang_code = VOICE_PREFIX_TO_LANG.get(prefix, "?")
        if language and lang_code != language:
            continue
        table.add_row(
            voice,
            LANGUAGE_DESCRIPTIONS.get(lang_code, "Unknown"),
            "Female" if prefix[1] == "f" else "Male",
            "Yes" if DEFAULT_VOICE_FOR_LANG.get(lang_code) == voice else "",
        )
    console.print(table)


def _show_model_status(config: dict[str, Any]) -> None:
    """Render source-aware model status using PyKokoro's asset API."""
    try:
        from pykokoro.model_assets import get_model_asset_paths
    except ImportError:
        console.print(
            "\n[bold]ONNX Models:[/bold] [yellow]Status unavailable "
            "(provider not installed)[/yellow]"
        )
        return

    from ..cli.backend_config import resolve_model_source_and_variant

    source, variant = resolve_model_source_and_variant(config)
    quality = str(config.get("model_quality", "fp32"))
    try:
        assets = get_model_asset_paths(
            quality=quality,
            source=source,
            variant=variant,
        )
    except ValueError as exc:
        console.print(
            f"\n[bold]ONNX Models:[/bold] [yellow]Status unavailable[/yellow] ({exc})"
        )
        return

    console.print(f"\n[bold]Source:[/bold] {source}")
    console.print(f"[bold]Variant:[/bold] {variant}")
    console.print(f"[bold]Quality:[/bold] {quality}")
    console.print(
        f"[bold]Configured model set:[/bold] {source} / {variant} / {quality}"
    )
    if assets.complete:
        console.print("[bold]ONNX Models:[/bold] Downloaded")
        if assets.config is None:
            console.print("  config.json: embedded / not required")
        else:
            console.print(f"  config.json: {assets.config}")
        console.print(f"  model: {assets.model}")
        console.print(f"  voices: {assets.voices}")
    else:
        console.print("[bold]ONNX Models:[/bold] [yellow]Incomplete[/yellow]")
        console.print(f"  Missing: {', '.join(assets.missing)}")
        console.print("[dim]Run 'ttsforge download' to download models[/dim]")

        alternate_source = "github" if source == "huggingface" else "huggingface"
        try:
            alternate = get_model_asset_paths(
                quality=quality,
                source=alternate_source,
                variant=variant,
            )
        except ValueError:
            alternate = None
        if alternate is not None and alternate.complete:
            console.print("[yellow]Found a complete alternate model set:[/yellow]")
            console.print(f"  {alternate_source} / {variant} / {quality}")
            console.print(
                f"[dim]Activate it with: ttsforge config "
                f"--set model_source {alternate_source}[/dim]"
            )


def _show_provider_status(config: dict[str, Any]) -> None:
    """Render provider availability without making it a model-status gate."""
    try:
        from pykokoro.onnx_session import (
            get_available_execution_providers,
            resolve_execution_provider,
        )

        from ..cli.backend_config import resolve_onnx_provider

        configured = resolve_onnx_provider(
            config, provider_override=None, use_gpu_override=None
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            available = get_available_execution_providers()
            resolved = resolve_execution_provider(configured)
        console.print("[bold]ONNX Runtime Providers:[/bold]")
        console.print(f"  Available: {', '.join(available) or 'none'}")
        console.print(f"  Configured: {configured}")
        console.print(f"  Resolved: {resolved}")
        if caught:
            console.print(f"  [yellow]Runtime warning: {caught[0].message}[/yellow]")
    except Exception:
        console.print(
            "[bold]ONNX Runtime Providers:[/bold] [yellow]Status unavailable[/yellow]"
        )


def config(
    show: bool,
    reset: bool,
    set_option: tuple[tuple[str, str], ...],
) -> None:
    """Manage ttsforge configuration."""
    if reset:
        reset_config()
        console.print("[green]Configuration reset to defaults.[/green]")
        return

    if set_option:
        current = load_config()
        pending: dict[str, Any] = {}
        errors: list[str] = []
        from ..short_sentence_config import validate_short_sentence_config

        for key, value in set_option:
            if key not in DEFAULT_CONFIG:
                errors.append(f"Unknown option '{key}'")
                continue
            try:
                default = DEFAULT_CONFIG[key]
                typed = parse_config_cli_value(key, value, default)
                validate_config_value(key, typed)
                if key == "short_sentence":
                    short_sentence_errors = validate_short_sentence_config(str(typed))
                    if short_sentence_errors:
                        raise ValueError("; ".join(short_sentence_errors))
                pending[key] = typed
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                detail = str(exc)
                suffix = f" ({detail})" if detail else ""
                errors.append(f"Invalid value for {key}: {value}{suffix}")

        if errors:
            for error in errors:
                console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=2)

        current.update(pending)
        if not save_config(current):
            console.print("[red]Failed to save configuration.[/red]")
            raise typer.Exit(code=1)
        for key, typed in pending.items():
            console.print(f"[green]Set {key} = {typed}[/green]")
        return

    current = load_config()
    table = Table(title="Current Configuration")
    table.add_column("Option", style="bold")
    table.add_column("Value")
    table.add_column("Default", style="dim")
    for key, default in DEFAULT_CONFIG.items():
        value = current.get(key, default)
        table.add_row(key, str(value), "" if value == default else str(default))
    console.print(table)
    _show_model_status(current)
    _show_provider_status(current)


def short_sentence_advanced_config(
    ctx: typer.Context,
    action: str | None,
) -> None:
    """Create, link, or show the advanced short-sentence JSON configuration."""
    if action is None:
        help_lines = ctx.get_help().splitlines()
        if help_lines and help_lines[0].startswith("Usage:"):
            command_usage = help_lines[0].split(" [OPTIONS]", 1)[0]
            help_lines[0] = f"{command_usage} [OPTIONS] [show|init|reset]"
        typer.echo("\n".join(help_lines))
        return

    from ..short_sentence_config import (
        get_advanced_short_sentence_config_path,
        load_short_sentence_json_config,
        write_advanced_short_sentence_config,
    )

    path = get_advanced_short_sentence_config_path()
    # Keep the path as one contiguous token so it remains copyable and
    # callers can reliably identify the config file in captured output.
    console.print(
        f"[bold]Advanced short-sentence config:[/bold] {path}",
        overflow="ignore",
        no_wrap=True,
        crop=False,
    )
    if action == "show":
        if not path.exists():
            console.print("[yellow]Config file does not exist yet.[/yellow]")
            return
        try:
            data = load_short_sentence_json_config(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            console.print(f"[red]Error loading config:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print_json(json.dumps(data, ensure_ascii=False))
        return

    written_path = write_advanced_short_sentence_config(path)
    current = load_config()
    current["short_sentence"] = f"config={written_path}"
    if save_config(current):
        message = (
            "Reset advanced short-sentence config to defaults."
            if action == "reset"
            else "Wrote advanced short-sentence config."
        )
        console.print(f"[green]{message}[/green]")
        console.print("[green]Updated ttsforge config to use it.[/green]")
        return
    console.print("[red]Failed to update ttsforge config.[/red]")
    raise typer.Exit(code=1)
