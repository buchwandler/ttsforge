"""Utility commands that can be declared without importing the TTS backend."""

from __future__ import annotations

import json
import warnings
from typing import Any, cast

import typer
from rich.table import Table

from ..constants import (
    DEFAULT_CONFIG,
    LANGUAGE_DESCRIPTIONS,
)
from ..utils import (
    _CONFIG_KEY_PATHS,
    _PATH_TO_CONFIG_KEY,
    effective_config_document,
    load_config,
    load_user_config,
    parse_config_cli_value,
    reset_config,
    save_config,
    validate_config_value,
)
from .helpers import console


def voices(language: str | None) -> None:
    """List available TTS voices from PyKokoro metadata."""
    try:
        from ..pykokoro_adapter import discover_models
    except ImportError:
        console.print(
            "[red]PyKokoro metadata unavailable:[/red] install pykokoro to list voices."
        )
        return

    from ..kokoro_lang import get_pykokoro_language

    # Build primary-language -> TTSForge codes mapping for filtering.
    # e.g. "en" -> ["a", "b"], "de" -> ["d"], "fr" -> ["f"]
    primary_to_tf: dict[str, list[str]] = {}
    for tf_code in LANGUAGE_DESCRIPTIONS:
        bcp47 = get_pykokoro_language(tf_code)
        primary = bcp47.split("-")[0]
        primary_to_tf.setdefault(primary, []).append(tf_code)
    tf_lang_to_label = {
        k: LANGUAGE_DESCRIPTIONS.get(k, k) for k in LANGUAGE_DESCRIPTIONS
    }

    try:
        inventory = discover_models()
    except Exception as exc:  # noqa: BLE001 - metadata loading can raise various errors
        console.print(f"[red]Failed to load voice metadata:[/red] {exc}")
        return

    # Collect all voices with their language metadata and model provenance.
    # A voice appearing in multiple models gets all languages merged.
    voice_data: dict[str, dict[str, object]] = {}
    for model in inventory.models:
        if not model.voices:
            continue
        model_tf_codes: list[str] = []
        for bcp47 in model.languages or []:
            primary = (bcp47 or "").split("-")[0]
            for tf in primary_to_tf.get(primary, []):
                if tf not in model_tf_codes:
                    model_tf_codes.append(tf)
        variant = model.model_id or "default"
        for voice_name in model.voices:
            if voice_name in voice_data:
                existing = voice_data[voice_name]
                for tf in model_tf_codes:
                    if tf not in existing["tf_codes"]:
                        cast(list, existing["tf_codes"]).append(tf)
            else:
                voice_data[voice_name] = {
                    "tf_codes": list(model_tf_codes),
                    "variant": variant,
                }

    if not voice_data:
        console.print("[yellow]No voices found in metadata.[/yellow]")
        return

    # Resolve the automatic default voice for the requested language.
    default_voice: str | None = None
    if language:
        try:
            from ..cli.backend_config import resolve_pykokoro_pipeline_defaults

            resolved = resolve_pykokoro_pipeline_defaults(ttsforge_language=language)
            default_voice = resolved.voice
        except Exception:  # noqa: BLE001, S110 - display-only default, not critical
            pass

    # Filter and sort deterministically.
    items = sorted(
        [
            (name, v["tf_codes"], v["variant"])
            for name, v in voice_data.items()
            if not language or language in v["tf_codes"]
        ]
    )

    table = Table(title="Available Voices")
    table.add_column("Voice", style="bold")
    table.add_column("Language")
    table.add_column("Model")
    table.add_column("Default", style="dim")
    for voice_name, langs, variant in items:
        lang_str = ", ".join(tf_lang_to_label.get(lc, lc) for lc in sorted(langs))
        is_default = "Yes" if voice_name == default_voice else ""
        table.add_row(voice_name, lang_str or "Unknown", variant, is_default)
    console.print(table)


def _show_model_status(config: dict[str, Any]) -> None:
    """Render source-aware model status using PyKokoro's asset API."""
    try:
        from ..pykokoro_adapter import get_model_asset_paths
    except ImportError:
        console.print(
            "\n[bold]ONNX Models:[/bold] [yellow]Status unavailable "
            "(provider not installed)[/yellow]"
        )
        return

    from ..cli.backend_config import resolve_model_source_variant_quality

    source, variant, quality = resolve_model_source_variant_quality(config)
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
        from ..cli.backend_config import resolve_onnx_provider
        from ..pykokoro_adapter import (
            get_available_execution_providers,
            resolve_execution_provider,
        )

        configured = resolve_onnx_provider(config, provider_override=None)
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
    except (ImportError, OSError, RuntimeError):
        console.print(
            "[bold]ONNX Runtime Providers:[/bold] [yellow]Status unavailable[/yellow]"
        )


def doctor_command() -> None:
    """Report installed runtime, provider, asset, and path diagnostics."""
    from importlib.metadata import PackageNotFoundError, version

    from ..utils import get_ffmpeg_path, get_user_cache_path, get_user_config_path

    console.print("[bold]TTSForge doctor[/bold]")
    for distribution in ("ttsforge", "pykokoro", "kokorog2p", "ssmd"):
        try:
            value = version(distribution)
        except PackageNotFoundError:
            value = "not installed"
        console.print(f"  {distribution}: {value}")
    config = load_config()
    _show_provider_status(config)
    _show_model_status(config)
    try:
        console.print(f"[bold]ffmpeg:[/bold] {get_ffmpeg_path()}")
    except (OSError, RuntimeError) as exc:
        console.print(f"[bold]ffmpeg:[/bold] unavailable ({exc})")
    console.print(f"[bold]Config:[/bold] {get_user_config_path()}")
    console.print(f"[bold]Cache:[/bold] {get_user_cache_path()}")


def config(
    show: bool,
    reset: bool,
    set_option: tuple[tuple[str, str], ...],
) -> None:
    """Manage ttsforge configuration."""
    if reset:
        reset_config()
        console.print("[green]Configuration reset.[/green]")
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


def _config_key(path: str) -> str:
    parts = tuple(part for part in path.split(".") if part)
    if len(parts) == 1 and parts[0] in DEFAULT_CONFIG:
        return parts[0]
    try:
        return _PATH_TO_CONFIG_KEY[parts]
    except KeyError as exc:
        raise ValueError(f"Unknown configuration path: {path}") from exc


def config_show_command(
    effective: bool = False,
    user: bool = False,
    as_json: bool = False,
) -> None:
    """Show persisted overrides or effective schema-2 configuration."""
    if effective and user:
        raise typer.BadParameter("--effective and --user cannot be combined")
    document = effective_config_document() if not user else load_user_config()
    if as_json:
        console.print_json(json.dumps(document, ensure_ascii=False))
        return
    console.print_json(json.dumps(document, ensure_ascii=False, indent=2))


def config_get_command(path: str) -> None:
    """Get one effective configuration value using a dotted path."""
    key = _config_key(path)
    value = load_config()[key]
    typer.echo(json.dumps(value, ensure_ascii=False))


def config_set_command(path: str, value: str) -> None:
    """Set one user configuration override using a dotted path."""
    key = _config_key(path)
    current = load_config()
    typed = parse_config_cli_value(key, value, DEFAULT_CONFIG[key])
    validate_config_value(key, typed)
    current[key] = typed
    if not save_config(current):
        raise typer.Exit(code=1)
    typer.echo(f"Set {path} = {typed}")


def config_unset_command(path: str) -> None:
    """Remove one persisted configuration override."""
    key = _config_key(path)
    document = load_user_config()
    parts = _CONFIG_KEY_PATHS[key]
    target: Any = document
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            return
        target = target[part]
    if isinstance(target, dict):
        target.pop(parts[-1], None)
    for index in range(len(parts) - 1, 0, -1):
        parent: Any = document
        for part in parts[: index - 1]:
            if not isinstance(parent, dict):
                break
            parent = parent.get(part)
        if (
            isinstance(parent, dict)
            and isinstance(parent.get(parts[index - 1]), dict)
            and not parent[parts[index - 1]]
        ):
            parent.pop(parts[index - 1], None)
    if not save_config(document):
        raise typer.Exit(code=1)
    typer.echo(f"Unset {path}")


def config_path_command() -> None:
    """Print the user configuration path."""
    from ..utils import get_user_config_path

    typer.echo(get_user_config_path())


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
