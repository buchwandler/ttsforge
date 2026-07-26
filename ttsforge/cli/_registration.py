"""Register lazily executed command implementations with Typer."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from typer.core import TyperCommand

from ._command_specs import COMMAND_SPECS


class ShortSentenceConfigTyperCommand(TyperCommand):
    """Append the runtime-resolved advanced config path to command help."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        super().format_help(ctx, formatter)
        from ttsforge.short_sentence_config import (
            get_advanced_short_sentence_config_path,
        )

        formatter.write_paragraph()
        formatter.write_text(
            "Advanced short-sentence config path: "
            f"{get_advanced_short_sentence_config_path()}"
        )


def _literal_type(values: list[str]) -> Any:
    return Literal.__getitem__(tuple(values))


def _parameter_type(spec: dict[str, Any], default: Any) -> Any:
    type_name = spec.get("python_type")
    base: Any
    if spec.get("choices") and spec.get("case_sensitive", True):
        base = _literal_type(list(spec["choices"]))
    elif type_name == "Path":
        base = str if "str" in str(spec.get("annotation", "")) else Path
    elif type_name == "int":
        base = int
    elif type_name == "float":
        base = float
    elif type_name == "bool":
        base = bool
    elif (
        spec.get("is_flag")
        or "flag_value" in spec
        or "/" in " ".join(spec.get("decls", []))
    ):
        base = bool
    else:
        base = str
    if spec.get("multiple"):
        base = list[base]
    if default is None:
        base = base | None
    return base


def _default_for(spec: dict[str, Any]) -> Any:
    if "default" in spec:
        return spec["default"]
    if spec.get("multiple"):
        return None
    if spec.get("is_flag"):
        return False
    if spec["kind"] == "argument" and spec.get("required", True):
        return inspect.Parameter.empty
    return None


def _path_kwargs(spec: dict[str, Any]) -> dict[str, Any]:
    path = spec.get("path")
    if not isinstance(path, dict):
        return {}
    return {
        "exists": path.get("exists", False),
        "file_okay": path.get("file_okay", True),
        "dir_okay": path.get("dir_okay", True),
        "readable": path.get("readable", True),
        "writable": path.get("writable", False),
        "resolve_path": path.get("resolve_path", False),
    }


def _argument_metadata(spec: dict[str, Any]) -> Any:
    metavar = spec.get("metavar")
    if spec["name"] == "action":
        metavar = "[show|init|reset]"
    return typer.Argument(
        help=spec.get("help"),
        metavar=metavar,
        min=spec.get("min"),
        max=spec.get("max"),
        **_path_kwargs(spec),
    )


def _option_metadata(spec: dict[str, Any]) -> Any:
    declarations = [
        value
        for value in spec.get("decls", [])
        if isinstance(value, str) and value.startswith("-")
    ]
    return typer.Option(
        *declarations,
        help=spec.get("help"),
        metavar=spec.get("metavar"),
        min=spec.get("min"),
        max=spec.get("max"),
        **_path_kwargs(spec),
    )


def _signature_for(spec: dict[str, Any]) -> inspect.Signature:
    parameters: list[inspect.Parameter] = []
    has_context = any(item["kind"] == "context" for item in spec["parameters"])
    if spec["function"] == "config" and not has_context:
        parameters.append(
            inspect.Parameter(
                "ctx",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=typer.Context,
            )
        )
    for item in spec["parameters"]:
        if item["kind"] == "context":
            parameters.append(
                inspect.Parameter(
                    item["name"],
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=typer.Context,
                )
            )
            continue
        default = _default_for(item)
        metadata = (
            _argument_metadata(item)
            if item["kind"] == "argument"
            else _option_metadata(item)
        )
        annotation = Annotated[_parameter_type(item, default), metadata]
        parameters.append(
            inspect.Parameter(
                item["name"],
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=annotation,
            )
        )
    return inspect.Signature(parameters, return_annotation=None)


def _make_callback(spec: dict[str, Any]) -> Any:
    parameter_specs = {item["name"]: item for item in spec["parameters"]}
    context_names = {
        item["name"] for item in spec["parameters"] if item["kind"] == "context"
    }

    def callback(**values: Any) -> Any:
        context = values.pop("ctx", None)
        if context is None:
            for name in context_names:
                context = values.pop(name, None)
                if context is not None:
                    break

        for name, item in parameter_specs.items():
            if item["kind"] == "context" or name not in values:
                continue
            value = values[name]
            if item.get("multiple"):
                values[name] = tuple(value or ())
            if item.get("flag_value") is False:
                values[name] = False if value else None
            choices = item.get("choices")
            if choices and not item.get("case_sensitive", True) and value is not None:
                normalized = str(value).lower()
                valid = {str(choice).lower() for choice in choices}
                if normalized not in valid:
                    raise typer.BadParameter(
                        f"{value!r} is not one of {', '.join(map(str, choices))}."
                    )
                values[name] = normalized

        if spec["function"] == "config":
            keys = list(values.pop("set_option", ()) or ())
            extras = list(context.args if context is not None else ())
            if len(keys) != len(extras):
                raise typer.BadParameter(
                    "--set requires exactly two values: KEY VALUE."
                )
            values["set_option"] = tuple(zip(keys, extras, strict=True))

        if spec["function"] == "short_sentence_advanced_config":
            return _run_short_sentence_config(context, values.get("action"))
        if spec["function"] == "config":
            return _run_config(values["show"], values["reset"], values["set_option"])
        if spec["function"] == "voices":
            return _run_voices(values.get("language"))

        module = importlib.import_module(spec["module"])
        implementation = getattr(module, spec["function"])
        if context_names:
            context_name = next(iter(context_names))
            values[context_name] = context
        return implementation(**values)

    callback.__name__ = f"{spec['function']}_command"
    callback.__doc__ = spec.get("help") or None
    callback.__signature__ = _signature_for(spec)
    return callback


def _run_voices(language: str | None) -> None:
    from rich.table import Table

    from ttsforge.cli.helpers import console
    from ttsforge.constants import (
        DEFAULT_VOICE_FOR_LANG,
        LANGUAGE_DESCRIPTIONS,
        VOICE_PREFIX_TO_LANG,
        VOICES,
    )

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


def _run_config(
    show: bool, reset: bool, set_option: tuple[tuple[str, str], ...]
) -> None:
    from rich.table import Table

    from ttsforge.cli.helpers import console
    from ttsforge.constants import DEFAULT_CONFIG
    from ttsforge.short_sentence_config import validate_short_sentence_config
    from ttsforge.utils import load_config, reset_config, save_config

    if reset:
        reset_config()
        console.print("[green]Configuration reset to defaults.[/green]")
        return
    if set_option:
        current = load_config()
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
            except ValueError:
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

    try:
        utility = importlib.import_module("ttsforge.cli.commands_utility")
        quality = current.get("model_quality", utility.DEFAULT_MODEL_QUALITY)
        source, variant = utility._resolve_model_source_and_variant(current)
        config_path = utility.get_config_path(variant=variant)
        model_path = utility.get_model_path(
            quality=quality,
            source=source,
            variant=variant,
        )
        voices_path = utility._get_cache_voices_path(source, variant)
        if all(
            utility._exists_nonempty(path)
            for path in (config_path, model_path, voices_path)
        ):
            model_dir = utility.get_model_dir(source=source, variant=variant)
            console.print(f"\n[bold]ONNX Models:[/bold] Downloaded ({model_dir})")
            console.print(f"  config.json: {config_path}")
            console.print(f"  model: {model_path}")
            console.print(f"  voices: {voices_path}")
            return
    except Exception:
        pass
    console.print("\n[bold]ONNX Models:[/bold] [yellow]Not downloaded[/yellow]")
    console.print("[dim]Run 'ttsforge download' to download models[/dim]")


def _run_short_sentence_config(
    context: typer.Context | None, action: str | None
) -> None:
    """Lightweight implementation kept outside the ONNX utility module."""
    from ttsforge.cli.helpers import console
    from ttsforge.short_sentence_config import (
        get_advanced_short_sentence_config_path,
        load_short_sentence_json_config,
        write_advanced_short_sentence_config,
    )
    from ttsforge.utils import load_config, save_config

    if action is None:
        if context is not None:
            typer.echo(context.get_help())
        return

    path = get_advanced_short_sentence_config_path()
    console.print(f"[bold]Advanced short-sentence config:[/bold] {path}")
    action = action.lower()
    if action == "show":
        if not path.exists():
            console.print("[yellow]Config file does not exist yet.[/yellow]")
            return
        try:
            data = load_short_sentence_json_config(path)
        except Exception as exc:
            console.print(f"[red]Error loading config:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print_json(json.dumps(data, ensure_ascii=False))
        return

    written_path = write_advanced_short_sentence_config(path)
    current_config = load_config()
    current_config["short_sentence"] = f"config={written_path}"
    if save_config(current_config):
        if action == "reset":
            console.print(
                "[green]Reset advanced short-sentence config to defaults.[/green]"
            )
        else:
            console.print("[green]Wrote advanced short-sentence config.[/green]")
        console.print("[green]Updated ttsforge config to use it.[/green]")
        return
    console.print("[red]Failed to update ttsforge config.[/red]")
    raise typer.Exit(code=1)


def register_commands(app: typer.Typer, phonemes_app: typer.Typer) -> None:
    """Register all command adapters without importing implementation modules."""
    for spec in COMMAND_SPECS:
        target = phonemes_app if spec.get("parent") == "phonemes" else app
        callback = _make_callback(spec)
        command_kwargs: dict[str, Any] = {
            "name": spec["name"],
            "help": spec.get("help") or None,
        }
        if spec["function"] == "config":
            command_kwargs["context_settings"] = {
                "allow_extra_args": True,
                "ignore_unknown_options": False,
            }
        if spec["function"] == "short_sentence_advanced_config":
            command_kwargs["cls"] = ShortSentenceConfigTyperCommand
        target.command(**command_kwargs)(callback)
