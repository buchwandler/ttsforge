"""Utility commands that can be declared without importing the TTS backend."""

from __future__ import annotations

import json
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
from ..utils import load_config, reset_config, save_config
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
    """Render model status when the optional provider API is available."""
    try:
        from pykokoro.onnx_backend import (
            get_config_path,
            get_model_dir,
            get_model_path,
            get_voices_dir,
        )
    except ImportError:
        console.print(
            "\n[bold]ONNX Models:[/bold] [yellow]Status unavailable "
            "(provider not installed)[/yellow]"
        )
        return

    from ..cli.backend_config import resolve_model_source_and_variant

    source, variant = resolve_model_source_and_variant(config)
    quality = str(config.get("model_quality", "fp32"))
    config_path = get_config_path(variant=variant)
    model_path = get_model_path(quality=quality, source=source, variant=variant)
    voices_dir = get_voices_dir(variant=variant)
    voices_path = voices_dir / "voices.bin"
    if all(
        path.exists() and path.stat().st_size > 0
        for path in (config_path, model_path, voices_path)
    ):
        model_dir = get_model_dir(source=source, variant=variant)
        console.print(f"\n[bold]ONNX Models:[/bold] Downloaded ({model_dir})")
        console.print(f"  config.json: {config_path}")
        console.print(f"  model: {model_path}")
        console.print(f"  voices: {voices_path}")
    else:
        console.print("\n[bold]ONNX Models:[/bold] [yellow]Not downloaded[/yellow]")
        console.print("[dim]Run 'ttsforge download' to download models[/dim]")


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
        from ..short_sentence_config import validate_short_sentence_config

        for key, value in set_option:
            if key not in DEFAULT_CONFIG:
                console.print(f"[yellow]Warning:[/yellow] Unknown option '{key}'")
                continue
            try:
                default = DEFAULT_CONFIG[key]
                if isinstance(default, bool):
                    typed: Any = value.lower() in ("true", "1", "yes")
                elif isinstance(default, float):
                    typed = float(value)
                elif isinstance(default, int):
                    typed = int(value)
                elif isinstance(default, list):
                    typed = json.loads(value)
                    if not isinstance(typed, list):
                        raise ValueError
                else:
                    typed = value
                if key == "short_sentence":
                    errors = validate_short_sentence_config(str(typed))
                    if errors:
                        console.print(
                            "[red]Invalid value for short_sentence:[/red] "
                            + "; ".join(errors)
                        )
                        continue
                current[key] = typed
                console.print(f"[green]Set {key} = {typed}[/green]")
            except (TypeError, ValueError, json.JSONDecodeError):
                console.print(f"[red]Invalid value for {key}: {value}[/red]")
        save_config(current)
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
    console.print(f"[bold]Advanced short-sentence config:[/bold] {path}")
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
