"""Audiobook-focused CLI over Readio's public workflow gateway."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast

import typer
from rich.console import Console

from ..application.errors import (
    ApplicationError,
    InputValidationError,
    OperationConflictError,
    WorkflowFailureError,
)
from ..application.models import (
    AudiobookRequest,
    BookInspectionView,
    CatalogItemView,
    ConversionResultView,
    InputOverrides,
    PreflightView,
    ProjectPaths,
    SetupPreparation,
    WorkflowPlanView,
)
from ..application.service import AudiobookApplicationService
from .interaction import resolve_interaction_mode
from .presenters import (
    render_catalog,
    render_completion,
    render_preflight,
    render_source_info,
    render_source_list,
    render_workflow,
)
from .progress import LineReadioProgress, LiveReadioProgress, NullReadioProgress

_output = Console(stderr=False, highlight=False, markup=False)

T = TypeVar("T")
_REBUILD_STAGES = (
    "convert",
    "compile",
    "render_plan",
    "render",
    "compose",
    "export",
)


def _version_callback(value: bool) -> None:
    if value:
        from .. import __version__

        typer.echo(f"ttsforge version {__version__}")
        raise typer.Exit()


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="A user-friendly audiobook frontend powered by Readio.",
)


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Convert EPUB books using persistent TTSForge projects."""
    del version


def _service() -> tuple[Any, AudiobookApplicationService]:
    from ..readio_backend import ReadioBackend, create_readio

    backend = ReadioBackend(create_readio())
    return backend, AudiobookApplicationService(backend)


def _is_expected_error(error: Exception) -> bool:
    return isinstance(error, (ApplicationError, ValueError, OSError, ImportError))


def _run(action: Callable[[], T], *, debug: bool) -> T:
    try:
        return action()
    except Exception as error:
        expected: Exception = error
        if not _is_expected_error(error):
            from ..readio_backend import normalize_readio_error

            normalized = normalize_readio_error(error)
            if normalized is None:
                raise
            expected = normalized
        if debug:
            traceback.print_exception(error)
        elif isinstance(expected, WorkflowFailureError):
            typer.echo(f"Error ({expected.category}): {expected}", err=True)
            for label, value in (
                ("Stage", expected.stage),
                ("Package", expected.package),
                ("Selector", expected.selector),
                ("Code", expected.code),
            ):
                if value:
                    typer.echo(f"{label}: {value}", err=True)
            saved_setup = expected.details.get("saved_setup")
            if isinstance(saved_setup, Mapping):
                project = saved_setup.get("project")
                intent = saved_setup.get("intent")
                profile = saved_setup.get("profile")
                if project:
                    typer.echo(
                        f"Saved setup remains available in {project}.",
                        err=True,
                    )
                if intent:
                    typer.echo(f"  Intent: {intent}", err=True)
                if profile:
                    typer.echo(f"  Profile: {profile}", err=True)
                if expected.category == "output collision":
                    typer.echo(
                        "Pass --replace-output only when replacing the "
                        "existing M4B is intentional.",
                        err=True,
                    )
                else:
                    typer.echo(
                        "Resolve the issue, then rerun the same convert command.",
                        err=True,
                    )
            if expected.details:
                typer.echo(
                    json.dumps(expected.details, ensure_ascii=False, default=str),
                    err=True,
                )
            typer.echo("Use --debug for a traceback.", err=True)
        else:
            typer.echo(f"Error: {expected}", err=True)
            code = getattr(expected, "code", None)
            if code:
                typer.echo(f"Code: {code}", err=True)
            details = getattr(expected, "details", None)
            if details:
                typer.echo(
                    json.dumps(details, ensure_ascii=False, default=str),
                    err=True,
                )
            typer.echo("Use --debug for a traceback.", err=True)
        raise typer.Exit(code=1) from error


def _json_dump(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _record(item: object) -> dict[str, object]:
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if isinstance(item, Mapping):
        return dict(item)
    names = (
        "id",
        "selector",
        "qualified_id",
        "target_id",
        "name",
        "display_name",
        "label",
        "engine",
        "language",
        "locale",
        "description",
    )
    return {name: getattr(item, name) for name in names if hasattr(item, name)}


def _catalog_views(items: tuple[object, ...]) -> tuple[CatalogItemView, ...]:
    views: list[CatalogItemView] = []
    for item in items:
        data = _record(item)
        identifier = next(
            (
                data[key]
                for key in ("id", "selector", "qualified_id", "target_id", "name")
                if data.get(key) is not None
            ),
            str(item),
        )
        label = next(
            (
                data[key]
                for key in ("label", "display_name", "name", "id")
                if data.get(key) is not None
            ),
            identifier,
        )
        known = {
            "id",
            "selector",
            "qualified_id",
            "target_id",
            "name",
            "display_name",
            "label",
            "engine",
            "language",
            "locale",
        }
        views.append(
            CatalogItemView(
                id=str(identifier),
                label=str(label),
                engine=_optional_string(data.get("engine")),
                language=_optional_string(data.get("language", data.get("locale"))),
                details={key: value for key, value in data.items() if key not in known},
            )
        )
    return tuple(views)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_engine_options(values: list[str] | None) -> dict[str, object]:
    options: dict[str, object] = {}
    for value in values or ():
        key, separator, raw_value = value.partition("=")
        if not separator or not key.strip():
            raise InputValidationError(
                f"Invalid engine option {value!r}; use KEY=VALUE."
            )
        key = key.strip()
        if key in options:
            raise InputValidationError(
                f"Engine option {key!r} was provided more than once."
            )
        try:
            options[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            options[key] = raw_value
    return options


def _overrides(**values: object) -> InputOverrides:
    return InputOverrides(
        frozenset(
            name
            for name, value in values.items()
            if value is not None and value is not False
        )
    )


def _choose_catalog_value(
    label: str,
    items: tuple[CatalogItemView, ...],
    *,
    optional: bool = False,
) -> str | None:
    if items:
        render_catalog(label, items, _output)
    identifiers = tuple(item.id for item in items)
    if not identifiers:
        prompt = f"{label} ID (blank for engine default)" if optional else f"{label} ID"
        value = (
            cast(str, typer.prompt(prompt, default=""))
            if optional
            else cast(str, typer.prompt(prompt))
        )
        return (value or None) if optional else value

    default = "" if optional else (identifiers[0] if len(identifiers) == 1 else "")
    value = cast(
        str,
        typer.prompt(
            f"{label} ID (number or identifier)",
            default=default,
        ),
    )
    if not value and optional:
        return None
    if value.isdecimal():
        row = int(value)
        if 1 <= row <= len(identifiers):
            return identifiers[row - 1]
    if value in identifiers:
        return value
    raise typer.BadParameter(f"Unknown {label.lower()} selection: {value!r}.")


def _complete_interactive_setup(
    backend: Any,
    preparation: SetupPreparation,
) -> AudiobookRequest:
    request = preparation.request
    language = request.language
    engine = request.engine
    target = request.target
    voice = request.voice

    if language is None:
        language = cast(str, typer.prompt("Language"))
    if engine is None:
        engine = _choose_catalog_value(
            "Engines", _catalog_views(tuple(backend.list_engines()))
        )
    if engine is None:
        raise InputValidationError("An engine must be selected.")
    if target is None:
        target = _choose_catalog_value(
            "Targets",
            _catalog_views(
                tuple(
                    backend.list_targets(
                        engine=engine,
                        language=language,
                        offline=request.offline,
                        refresh=request.refresh,
                    )
                )
            ),
        )
    if target is None:
        raise InputValidationError("A render target must be selected.")
    if voice is None and preparation.origins.needs_input("voice"):
        voice = _choose_catalog_value(
            "Voices",
            _catalog_views(
                tuple(
                    backend.list_voices(
                        engine=engine,
                        target=target,
                        language=language,
                        offline=request.offline,
                        refresh=request.refresh,
                    )
                )
            ),
            optional=True,
        )
    return replace(
        request,
        language=language,
        engine=engine,
        target=target,
        voice=voice,
    )


def _inspection_payload(inspection: BookInspectionView) -> dict[str, object]:
    return {
        "source": str(inspection.source),
        "kind": inspection.kind,
        "title": inspection.title,
        "author": inspection.author,
        "language": inspection.language,
        "chapters": [asdict(chapter) for chapter in inspection.chapters],
    }


def _workflow_payload(plan: WorkflowPlanView) -> dict[str, object]:
    return asdict(plan)


@app.command()
def convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    project: Annotated[Path | None, typer.Option("--project")] = None,
    chapters: Annotated[str | None, typer.Option("--chapters")] = None,
    output: Annotated[Path | None, typer.Option("-o", "--output")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    target: Annotated[str | None, typer.Option("--target")] = None,
    voice: Annotated[str | None, typer.Option("--voice")] = None,
    engine_option: Annotated[
        list[str] | None,
        typer.Option(
            "--engine-option",
            help="Engine-specific KEY=VALUE option; repeatable.",
        ),
    ] = None,
    speed: Annotated[float | None, typer.Option("--speed", min=0.5, max=2.0)] = None,
    bitrate: Annotated[str | None, typer.Option("--bitrate")] = None,
    target_lufs: Annotated[float | None, typer.Option("--target-lufs")] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    cover: Annotated[
        Path | None,
        typer.Option("--cover", exists=True, dir_okay=False, readable=True),
    ] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    rebuild_from: Annotated[
        str | None,
        typer.Option(
            "--rebuild-from",
            help=(
                "Explicitly rebuild from convert, compile, render_plan, render, "
                "compose, or export."
            ),
        ),
    ] = None,
    replace_output: Annotated[
        bool,
        typer.Option(
            "--replace-output", help="Allow replacing an existing M4B output."
        ),
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option("--fresh", help="Use a separate new TTSForge project directory."),
    ] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    non_interactive: Annotated[bool, typer.Option("--non-interactive")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect, configure, and render an EPUB audiobook as M4B."""
    if rebuild_from is not None and rebuild_from not in _REBUILD_STAGES:
        choices = ", ".join(_REBUILD_STAGES)
        raise typer.BadParameter(f"Choose --rebuild-from from: {choices}.")
    interaction = resolve_interaction_mode(
        json_mode=json_mode,
        assume_yes=yes,
        force_non_interactive=non_interactive,
    )
    options = _parse_engine_options(engine_option)
    request = AudiobookRequest(
        source=source,
        project=project,
        chapters=chapters,
        output=output,
        language=language,
        engine=engine,
        target=target,
        voice=voice,
        engine_options=options,
        speed=speed,
        bitrate=bitrate,
        target_lufs=target_lufs,
        title=title,
        author=author,
        cover=cover,
        offline=offline,
        refresh=refresh,
        rebuild_from=rebuild_from,
        replace_output=replace_output,
        fresh=fresh,
    )
    overrides = _overrides(
        chapters=chapters,
        output=output,
        language=language,
        engine=engine,
        target=target,
        voice=voice,
        engine_options=options if engine_option else None,
        speed=speed,
        bitrate=bitrate,
        target_lufs=target_lufs,
        title=title,
        author=author,
        cover=cover,
    )

    def action() -> tuple[
        SetupPreparation,
        PreflightView,
        ConversionResultView | None,
    ]:
        backend, service = _service()
        preparation = service.prepare_setup(
            request,
            overrides,
            interactive=interaction.interactive,
        )
        if preparation.inspection.kind != "book":
            raise InputValidationError(
                "Convert requires a book source such as an EPUB."
            )
        selected = (
            _complete_interactive_setup(backend, preparation)
            if interaction.interactive
            else preparation.request
        )
        resolved = service.save_setup(preparation, selected)
        preflight = service.preflight(resolved)
        if not interaction.json:
            render_preflight(preflight, _output)
        if interaction.confirm and not typer.confirm(
            "Create this audiobook?", default=True
        ):
            _output.print("Cancelled. The saved setup is ready to retry.")
            return preparation, preflight, None
        progress = (
            NullReadioProgress()
            if interaction.json
            else LiveReadioProgress()
            if interaction.live_progress
            else LineReadioProgress()
        )
        try:
            result = service.render(resolved, on_progress=progress)
        finally:
            progress.close()
        return preparation, preflight, result

    preparation, preflight, result = _run(action, debug=debug)
    if result is None:
        return
    if json_mode:
        _json_dump(
            {
                "source": str(source),
                "project": str(preparation.paths.root),
                "reused_setup": preparation.reused,
                "request": asdict(preflight.setup.request),
                "workflow": _workflow_payload(preflight.workflow),
                "result": asdict(result),
            }
        )
    else:
        render_completion(result, _output)


@app.command("list")
def list_chapters(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List the chapters discovered in a source book."""
    inspection = _run(lambda: _service()[1].inspect_book(source), debug=debug)
    if json_mode:
        _json_dump(_inspection_payload(inspection))
    else:
        render_source_list(inspection, _output)


@app.command()
def info(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    project: Annotated[Path | None, typer.Option("--project")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show source metadata and any saved audiobook setup."""

    def action() -> tuple[
        BookInspectionView,
        ProjectPaths,
        AudiobookRequest | None,
    ]:
        _, service = _service()
        inspection = service.inspect_book(source)
        paths = ProjectPaths.for_source(source, project)
        saved = service.load_saved_setup(paths)
        if saved is not None and saved.source.resolve() != source.resolve():
            raise OperationConflictError(
                f"Project {paths.root} is configured for a different source."
            )
        return inspection, paths, saved

    inspection, paths, saved = _run(action, debug=debug)
    if json_mode:
        payload = _inspection_payload(inspection)
        payload["project"] = str(paths.root)
        payload["saved_setup"] = None if saved is None else asdict(saved)
        _json_dump(payload)
    else:
        render_source_info(inspection, paths.root, saved, _output)


@app.command()
def status(
    source: Annotated[Path | None, typer.Argument()] = None,
    project: Annotated[Path | None, typer.Option("--project")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect the saved workflow for a source or project directory."""
    if source is None:
        paths = ProjectPaths.for_root(project or Path.cwd())
    else:
        paths = ProjectPaths.for_source(source, project)

    def action() -> WorkflowPlanView:
        service = _service()[1]
        if source is not None:
            saved = service.load_saved_setup(paths)
            if saved is not None and saved.source.resolve() != source.resolve():
                raise OperationConflictError(
                    f"Project {paths.root} is configured for a different source."
                )
        return service.status(paths)

    plan = _run(action, debug=debug)
    if json_mode:
        _json_dump(_workflow_payload(plan))
    else:
        _output.print(f"Project: {paths.root}")
        _output.print(
            f"Workspace: {plan.workspace or 'not available'} ({plan.workspace_mode})"
        )
        render_workflow(plan, _output)


def _catalog_command(
    label: str,
    values: tuple[object, ...],
    *,
    json_mode: bool,
) -> None:
    items = _catalog_views(values)
    if json_mode:
        _json_dump([asdict(item) for item in items])
    else:
        render_catalog(label, items, _output)


@app.command()
def engines(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List engines exposed by Readio's public discovery API."""
    values = _run(lambda: tuple(_service()[0].list_engines()), debug=debug)
    _catalog_command("Engines", values, json_mode=json_mode)


@app.command()
def targets(
    engine: Annotated[str, typer.Option("--engine")],
    language: Annotated[str | None, typer.Option("--language")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List runnable targets for an engine."""
    values = _run(
        lambda: tuple(
            _service()[0].list_targets(
                engine=engine,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        ),
        debug=debug,
    )
    _catalog_command("Targets", values, json_mode=json_mode)


@app.command()
def voices(
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    target: Annotated[str | None, typer.Option("--target")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List voices available for an engine target."""
    values = _run(
        lambda: tuple(
            _service()[0].list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        ),
        debug=debug,
    )
    _catalog_command("Voices", values, json_mode=json_mode)


__all__ = [
    "app",
    "cli_main",
    "convert",
    "engines",
    "info",
    "list_chapters",
    "status",
    "targets",
    "voices",
]


def cli_main() -> None:
    """Run the installed TTSForge command."""
    app(prog_name="ttsforge")
