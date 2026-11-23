"""Audiobook-focused CLI over Readio's public workflow gateway."""

from __future__ import annotations

import json
import signal
import traceback
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast

import typer
from rich.console import Console
from rich.table import Table

from ..application.catalog_service import CatalogApplicationService
from ..application.chapters import ChapterApplicationService
from ..application.conversion import ConversionCoordinator
from ..application.errors import (
    ApplicationError,
    InputValidationError,
    OperationConflictError,
    WorkflowFailureError,
)
from ..application.library import LibraryApplicationService
from ..application.metadata import MetadataApplicationService
from ..application.models import (
    AudiobookQcReport,
    AudiobookRequest,
    BookInspectionView,
    ChapterStatusView,
    ConversionResultView,
    InputOverrides,
    PreflightView,
    ProjectPaths,
    ProjectVariantView,
    SetupPreparation,
    SpacyModelView,
    WorkflowPlanView,
)
from ..application.narrations import NarrationApplicationService
from ..application.preview import PreviewApplicationService, PreviewRequest
from ..application.qc import QcApplicationService
from ..application.service import AudiobookApplicationService
from ..application.speech_profiles import discover_speech_replacement_profiles
from .catalog import (
    CatalogChoiceView,
    TargetChoiceView,
    VoiceChoiceView,
    engine_choice_view,
    target_choice_view,
    voice_choice_view,
)
from .chapters import choose_chapters
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


_SPACY_CHOICES = ("off", "auto", "sm", "md", "lg", "trf")
_PAUSE_TIMING_CHOICES = ("fixed", "natural", "engaging")
_SPACY_LABELS = {
    "off": "disabled",
    "auto": "installed models only",
    "sm": "small",
    "md": "medium",
    "lg": "large",
    "trf": "transformer",
}


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
narration_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(narration_app, name="narration")
chapters_app = typer.Typer(add_completion=False, no_args_is_help=True)
metadata_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(chapters_app, name="chapters")
app.add_typer(metadata_app, name="metadata")
projects_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(projects_app, name="projects")


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


def _run(action: Callable[[], T], *, debug: bool, failure_code: int = 1) -> T:
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
        raise typer.Exit(code=failure_code) from error


def _json_dump(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _write_preview_file(path: Path, payload: bytes) -> Path:
    output = path.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open("xb") as stream:
            created = True
            stream.write(payload)
    except FileExistsError as error:
        raise OperationConflictError(
            f"Preview output already exists: {output}."
        ) from error
    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise
    return output


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


def _narration_service() -> tuple[
    AudiobookApplicationService, NarrationApplicationService
]:
    backend, audiobook = _service()
    catalog = CatalogApplicationService(backend)
    return audiobook, NarrationApplicationService(audiobook, catalog)


def _library_service() -> LibraryApplicationService:
    backend, audiobook = _service()
    narrations = NarrationApplicationService(
        audiobook, CatalogApplicationService(backend)
    )
    return LibraryApplicationService(audiobook, narrations)


@projects_app.command("list")
def projects_list(
    root: Annotated[Path, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Discover TTSForge projects below a library directory."""
    projects = _run(lambda: _library_service().list(root), debug=debug)
    if json_mode:
        _json_dump([asdict(item) for item in projects])
        return
    if not projects:
        _output.print(f"No TTSForge projects found under {root}.")
        return
    for item in projects:
        _output.print(f"{item.title or item.project.name}: {item.project}")
        _output.print(
            f"  Chapters: {item.selected_chapter_count}/{item.chapter_count}; "
            f"narrations: {len(item.narrations)}; QC: {item.qc_state or 'unknown'}"
        )
        if item.error:
            _output.print(f"  Error: {item.error}")


@projects_app.command("info")
def projects_info(
    project: Annotated[Path, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect one TTSForge project directory."""
    summary = _run(lambda: _library_service().inspect(project), debug=debug)
    if json_mode:
        _json_dump(asdict(summary))
        return
    _output.print(f"Project: {summary.project}")
    _output.print(f"Title: {summary.title or 'not set'}")
    _output.print(f"Author: {summary.author or 'not set'}")
    _output.print(f"Source: {summary.source or 'not set'}")
    _output.print(
        f"Chapters: {summary.selected_chapter_count}/{summary.chapter_count} selected"
    )
    _output.print(f"QC: {summary.qc_state or 'unknown'}")
    for narration in summary.narrations:
        primary = " (primary)" if narration.primary else ""
        _output.print(f"Narration: {narration.display_name}{primary} [{narration.id}]")
    for output in summary.outputs:
        _output.print(f"Output: {output}")
    if summary.error:
        _output.print(f"Error: {summary.error}")


def _prepare_narration_render(
    project: Path, narration_id: str
) -> tuple[ConversionCoordinator, object]:
    backend, audiobook = _service()
    catalog = CatalogApplicationService(backend)
    narrations = NarrationApplicationService(audiobook, catalog)
    request, overrides = narrations.request_for_render(
        ProjectPaths.for_root(project), narration_id
    )
    coordinator = ConversionCoordinator(audiobook, catalog)
    return coordinator, coordinator.prepare(request, overrides)


@narration_app.command("list")
def narration_list(
    project: Annotated[Path, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List the primary and additional narrations in a TTSForge project."""
    _, narrations = _narration_service()
    values = _run(lambda: narrations.list(ProjectPaths.for_root(project)), debug=debug)
    if json_mode:
        _json_dump(values)
    elif not values:
        _output.print("No narrations configured.")
    else:
        for item in values:
            primary = " (primary)" if item.primary else ""
            _output.print(f"{item.display_name}{primary} [{item.id}]")
            if item.error:
                _output.print(f"  Error: {item.error}")


@narration_app.command("info")
def narration_info(
    project: Annotated[Path, typer.Argument()],
    narration_id: Annotated[str, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show the saved configuration summary for one narration."""
    _, narrations = _narration_service()
    item = _run(
        lambda: narrations.get(ProjectPaths.for_root(project), narration_id),
        debug=debug,
    )
    if json_mode:
        _json_dump(item)
    else:
        _output.print(f"{item.display_name} [{item.id}]")
        _output.print(f"Primary: {'yes' if item.primary else 'no'}")
        _output.print(f"Output: {item.output or 'not configured'}")
        _output.print(f"Engine: {item.engine or 'not configured'}")
        _output.print(f"Target: {item.target or 'not configured'}")
        _output.print(f"Voice: {item.voice or 'default'}")
        if item.error:
            _output.print(f"Error: {item.error}")


@narration_app.command("create")
def narration_create(
    project: Annotated[Path, typer.Argument()],
    display_name: Annotated[str, typer.Option("--name")],
    engine: Annotated[str, typer.Option("--engine")],
    target: Annotated[str, typer.Option("--target")],
    voice: Annotated[str | None, typer.Option("--voice")] = None,
    engine_option: Annotated[list[str] | None, typer.Option("--engine-option")] = None,
    speed: Annotated[float | None, typer.Option("--speed")] = None,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Create and persist an additional narration without rendering it."""
    _, narrations = _narration_service()
    item = _run(
        lambda: narrations.create(
            ProjectPaths.for_root(project),
            display_name=display_name,
            engine=engine,
            target=target,
            voice=voice,
            engine_options=_parse_engine_options(engine_option),
            speed=speed,
            output=output,
        ),
        debug=debug,
    )
    if json_mode:
        _json_dump(item)
    else:
        _output.print(f"Created narration {item.display_name} [{item.id}].")
        _output.print(f"Output: {item.output}")


@narration_app.command("preflight")
def narration_preflight(
    project: Annotated[Path, typer.Argument()],
    narration_id: Annotated[str, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect the Readio workflow for a saved narration."""
    _, prepared = _run(
        lambda: _prepare_narration_render(project, narration_id), debug=debug
    )
    if json_mode:
        _json_dump(prepared.preflight)
    else:
        render_preflight(prepared.preflight, _output, spacy_model=prepared.spacy_model)


@narration_app.command("render")
def narration_render(
    project: Annotated[Path, typer.Argument()],
    narration_id: Annotated[str, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Render a saved narration using its existing project artifacts."""
    coordinator, prepared = _run(
        lambda: _prepare_narration_render(project, narration_id), debug=debug
    )
    result = _run(lambda: coordinator.execute(prepared), debug=debug)
    if json_mode:
        _json_dump({"narration_id": narration_id, "result": result})
    else:
        _output.print(f"Rendered {result.output}")


@narration_app.command("delete")
def narration_delete(
    project: Annotated[Path, typer.Argument()],
    narration_id: Annotated[str, typer.Argument()],
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Delete an additional narration setup without deleting rendered audio."""
    _, narrations = _narration_service()
    _run(
        lambda: narrations.delete(ProjectPaths.for_root(project), narration_id),
        debug=debug,
    )
    _output.print(f"Deleted narration {narration_id}. Rendered audio was kept.")


def _choose_catalog_value(
    label: str,
    items: tuple[CatalogChoiceView, ...],
    *,
    optional: bool = False,
) -> str | None:
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


def _reject_reference_only_target(
    target: str,
    choices: tuple[TargetChoiceView, ...],
) -> None:
    if any(choice.id == target and choice.reference_only for choice in choices):
        raise InputValidationError(
            f"Target {target!r} requires reference audio, "
            "which TTSForge does not support."
        )


def _prompt_choice(label: str, choices: tuple[str, ...], default: str) -> str:
    value = cast(str, typer.prompt(label, default=default))
    if value.isdecimal():
        row = int(value)
        if 1 <= row <= len(choices):
            return choices[row - 1]
    if value in choices:
        return value
    available = ", ".join(choices)
    raise InputValidationError(f"Choose {label.lower()} from: {available}.")


def _choose_spacy_tier(default: str | None, models: tuple[SpacyModelView, ...]) -> str:
    installed_tiers = {item.tier for item in models if item.installed}
    _output.print("spaCy model")
    for index, tier in enumerate(_SPACY_CHOICES, 1):
        marker = (
            " [installed]"
            if tier in installed_tiers and tier in {"sm", "md", "lg", "trf"}
            else ""
        )
        _output.print(f"  {index}. {tier:<4} {_SPACY_LABELS[tier]}{marker}")
    return _prompt_choice("spaCy model", _SPACY_CHOICES, default or "sm")


def _choose_pause_timing(default: str | None) -> str:
    return _prompt_choice(
        "Pause timing (fixed/natural/engaging)",
        _PAUSE_TIMING_CHOICES,
        default or "engaging",
    )


def _prompt_speech_profile(
    default: Path | None,
    *,
    directory: Path,
) -> Path | None:
    detected = discover_speech_replacement_profiles(directory)
    entries: list[tuple[str, Path | None]] = [("none", None)]

    if default is not None and default not in detected:
        entries.append((f"{default}  [current]", default))

    for path in detected:
        marker = "  [current]" if default == path else "  [detected]"
        entries.append((f"{path.name}{marker}", path))

    custom_index = len(entries) + 1
    _output.print("Speech replacement profile")
    for index, (label, _) in enumerate(entries, 1):
        _output.print(f"  {index}. {label}")
    _output.print(f"  {custom_index}. enter custom path...")

    default_index = 1
    if default is not None:
        for index, (_, candidate) in enumerate(entries, 1):
            if candidate == default:
                default_index = index
                break

    selection = cast(
        str,
        typer.prompt("Speech replacement profile", default=str(default_index)),
    )
    if selection.isdecimal():
        selected = int(selection)
        if 1 <= selected <= len(entries):
            return entries[selected - 1][1]
        if selected == custom_index:
            custom = cast(
                str,
                typer.prompt("Speech replacement profile path", default=""),
            )
            return Path(custom).expanduser() if custom else None
        raise InputValidationError(
            f"Choose speech replacement profile from 1 to {custom_index}."
        )

    if selection.casefold() == "none":
        return None
    return Path(selection).expanduser() if selection else None


def _confirm_language(language: str | None, preparation: SetupPreparation) -> str:
    if preparation.origins.should_confirm_derived("language"):
        if language is None:
            return cast(str, typer.prompt("Language"))
        return cast(str, typer.prompt("Language", default=language))
    if language is None:
        return cast(str, typer.prompt("Language"))
    return language


def _complete_interactive_setup(
    backend: Any,
    preparation: SetupPreparation,
) -> AudiobookRequest:
    request = preparation.request
    chapters = request.chapters
    language = request.language
    engine = request.engine
    target = request.target
    voice = request.voice
    engine_options = request.engine_options
    speed = request.speed
    spacy = request.spacy
    speech_profile = request.speech_profile
    pause_timing = request.pause_timing

    if preparation.origins.should_confirm_derived("chapters"):
        chapters = choose_chapters(
            preparation.inspection,
            _output,
            default=chapters or "all",
        )
    language = _confirm_language(language, preparation)
    if preparation.origins.needs_input("spacy"):
        models = backend.list_spacy_models(language)
        spacy = _choose_spacy_tier(spacy, models)

    language_changed = language != request.language
    explicit = preparation.origins.explicit
    if language_changed:
        if "engine" not in explicit:
            engine = None
        if "target" not in explicit:
            target = None
        if "voice" not in explicit:
            voice = None
        if "engine_options" not in explicit:
            engine_options = {}
        if "speed" not in explicit:
            speed = None

    if engine is None:
        engine = _choose_catalog_value(
            f"Engines for {language}",
            tuple(engine_choice_view(item) for item in backend.list_engines()),
        )
    if engine is None:
        raise InputValidationError("An engine must be selected.")

    target_views = tuple(
        target_choice_view(item)
        for item in backend.list_targets(
            engine=engine,
            language=language,
            offline=request.offline,
            refresh=request.refresh,
        )
    )
    if target is not None:
        _reject_reference_only_target(target, target_views)
        if (
            language_changed
            and "target" in explicit
            and not any(choice.id == target for choice in target_views)
        ):
            raise InputValidationError(
                f"Target {target!r} is not available for language {language!r}."
            )
    else:
        selectable_targets = tuple(
            choice for choice in target_views if not choice.reference_only
        )
        if not selectable_targets and target_views:
            raise InputValidationError(
                "No supported audiobook targets are available. "
                "Reference-audio enrollment is not supported by TTSForge."
            )
        target = _choose_catalog_value(
            f"{engine.capitalize()} targets for {language}",
            selectable_targets,
        )
    if target is None:
        raise InputValidationError("A render target must be selected.")

    def discover_voices() -> tuple[VoiceChoiceView, ...]:
        return tuple(
            voice_choice_view(voice)
            for voice in backend.list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=request.offline,
                refresh=request.refresh,
            )
        )

    if language_changed and voice is not None and "voice" in explicit:
        available_voices = discover_voices()
        if not any(choice.id == voice for choice in available_voices):
            raise InputValidationError(
                f"Voice {voice!r} is not available for language {language!r}."
            )
    if voice is None and (
        preparation.origins.needs_input("voice")
        or (language_changed and "voice" not in explicit)
    ):
        voice = _choose_catalog_value(
            f"Voices for {language} / {target}",
            discover_voices(),
            optional=True,
        )
    if preparation.origins.needs_input("speech_profile"):
        speech_profile = _prompt_speech_profile(
            speech_profile,
            directory=request.source.parent,
        )
    if preparation.origins.needs_input("pause_timing"):
        pause_timing = _choose_pause_timing(pause_timing)

    return replace(
        request,
        chapters=chapters,
        language=language,
        engine=engine,
        target=target,
        voice=voice,
        engine_options=engine_options,
        speed=speed,
        spacy=spacy,
        speech_profile=speech_profile,
        pause_timing=pause_timing,
    )


def _confirm_spacy_model(
    model: SpacyModelView,
    *,
    json_mode: bool,
    interactive: bool,
    confirm: bool,
    offline: bool,
    assume_yes: bool,
) -> bool:
    if not json_mode:
        _output.print("spaCy")
        _output.print(f"  Model  {model.model}")
        status = "installed"
        if model.model_version:
            status += f" {model.model_version}"
        if not model.installed:
            status = "not installed"
        _output.print(f"  Status {status}")
    if model.installed or offline:
        return True
    if confirm and not typer.confirm(f"Download {model.model}?", default=True):
        return False
    if not interactive and not assume_yes:
        raise InputValidationError(
            f"spaCy model {model.model!r} is missing. "
            "Run interactively or pass --yes to download it."
        )
    if not json_mode:
        _output.print(f"Installing {model.model}...")
    return True


def _inspection_payload(inspection: BookInspectionView) -> dict[str, object]:
    return {
        "source": str(inspection.source),
        "kind": inspection.kind,
        "title": inspection.title,
        "author": inspection.author,
        "language": inspection.language,
        "chapters": [asdict(chapter) for chapter in inspection.chapters],
        "cover": str(inspection.cover) if inspection.cover is not None else None,
        "metadata": asdict(inspection.metadata),
    }


def _workflow_payload(plan: WorkflowPlanView) -> dict[str, object]:
    return asdict(plan)


@app.command()
def preview(
    project: Annotated[Path, typer.Argument()],
    text: Annotated[str, typer.Option("--text")],
    output: Annotated[Path, typer.Option("--output")],
    narration_id: Annotated[str | None, typer.Option("--narration")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Synthesize explicit text with a saved narration and write a WAV preview."""
    backend, audiobook = _service()
    catalog = CatalogApplicationService(backend)
    narrations = NarrationApplicationService(audiobook, catalog)
    previews = PreviewApplicationService(narrations, backend)
    request = PreviewRequest(
        project=project,
        narration_id=narration_id,
        text=text,
    )
    cancellation = previews.new_cancellation_token()

    def generate() -> tuple[object, Path]:
        previous_handler = signal.getsignal(signal.SIGINT)

        def cancel(_signum: int, _frame: object) -> None:
            cancellation.cancel()

        signal.signal(signal.SIGINT, cancel)
        try:
            result = previews.preview(request, cancellation=cancellation)
            output_path = _write_preview_file(output, result.audio.wav)
            return result, output_path
        finally:
            signal.signal(signal.SIGINT, previous_handler)

    result, output_path = _run(generate, debug=debug)
    if json_mode:
        _json_dump(
            {
                "narration_id": result.narration_id,
                "excerpt": result.excerpt,
                "audio": {
                    "sample_rate": result.audio.sample_rate,
                    "channels": result.audio.channels,
                    "frames": result.audio.frames,
                    "duration_seconds": result.audio.duration_seconds,
                    "warnings": result.audio.warnings,
                },
                "output": output_path,
            }
        )
    else:
        _output.print(
            f"Wrote preview WAV {output_path} "
            f"({result.audio.duration_seconds:.1f}s, {result.audio.sample_rate} Hz)."
        )


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
    spacy: Annotated[
        Literal["off", "auto", "sm", "md", "lg", "trf"] | None,
        typer.Option("--spacy", help="spaCy model tier."),
    ] = None,
    speech_profile: Annotated[
        Path | None,
        typer.Option("--speech-profile"),
    ] = None,
    pause_timing: Annotated[
        Literal["fixed", "natural", "engaging"] | None,
        typer.Option("--pause-timing"),
    ] = None,
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
    new_variant: Annotated[
        bool,
        typer.Option(
            "--new-variant",
            help=(
                "Deprecated compatibility adapter. Prefer `ttsforge narration create` "
                "and `ttsforge narration render`."
            ),
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes")] = False,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Disable prompts; new variants require explicit engine and target.",
        ),
    ] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect, configure, and render an EPUB audiobook as M4B."""
    if new_variant and not json_mode:
        typer.echo(
            "Warning: --new-variant is deprecated. Use `ttsforge narration create` "
            "and `ttsforge narration render`.",
            err=True,
        )
    if new_variant and fresh:
        raise typer.BadParameter("--new-variant cannot be combined with --fresh.")
    if new_variant and rebuild_from in {"convert", "compile"}:
        raise typer.BadParameter(
            "--new-variant cannot be combined with --rebuild-from convert or compile."
        )
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
        spacy=spacy,
        speech_profile=speech_profile,
        pause_timing=pause_timing,
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
        new_variant=new_variant,
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
        spacy=spacy,
        speech_profile=speech_profile,
        pause_timing=pause_timing,
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
        SpacyModelView | None,
        float | None,
    ]:
        backend, service = _service()
        catalog = CatalogApplicationService(backend)
        coordinator = ConversionCoordinator(service, catalog)
        setup_service = (
            NarrationApplicationService(service, catalog)
            if request.new_variant
            else service
        )
        preparation = setup_service.prepare_setup(
            request,
            overrides,
            interactive=interaction.interactive,
        )
        if preparation.inspection.kind != "book":
            raise InputValidationError(
                "Convert requires a book source such as an EPUB."
            )
        if interaction.interactive:
            selected = _complete_interactive_setup(backend, preparation)
        else:
            selected = preparation.request

        spacy_was_missing = False

        def confirm_spacy(model: SpacyModelView) -> bool:
            nonlocal spacy_was_missing
            spacy_was_missing = not model.installed
            return _confirm_spacy_model(
                model,
                json_mode=interaction.json,
                interactive=interaction.interactive,
                confirm=interaction.confirm,
                offline=selected.offline,
                assume_yes=yes,
            )

        def present_preflight(
            preflight: PreflightView, spacy_model: SpacyModelView | None
        ) -> None:
            if not interaction.json:
                render_preflight(preflight, _output, spacy_model=spacy_model)

        prepared = coordinator.prepare(
            selected,
            overrides,
            preparation=preparation,
            on_spacy_model=confirm_spacy,
            on_preflight=present_preflight,
        )
        preparation = prepared.preparation
        resolved = prepared.resolved
        spacy_model = prepared.spacy_model
        if spacy_was_missing and spacy_model is not None and not interaction.json:
            version = (
                f" {spacy_model.model_version}" if spacy_model.model_version else ""
            )
            _output.print(f"Installed {spacy_model.model}{version}")
        preflight = prepared.preflight
        if interaction.confirm and not typer.confirm(
            "Create this audiobook?", default=True
        ):
            _output.print("Cancelled. The saved setup is ready to retry.")
            return preparation, preflight, None, spacy_model, None
        progress = (
            NullReadioProgress()
            if interaction.json
            else LiveReadioProgress(
                chapters=preparation.inspection.chapters,
                selected_chapters=resolved.request.chapters,
            )
            if interaction.live_progress
            else LineReadioProgress(
                chapters=preparation.inspection.chapters,
                selected_chapters=resolved.request.chapters,
            )
        )
        try:
            result = coordinator.execute(prepared, on_progress=progress)
        except Exception:
            progress.close(success=False)
            raise
        else:
            progress.close(success=True)
        return preparation, preflight, result, spacy_model, progress.elapsed_seconds

    preparation, preflight, result, spacy_model, elapsed_seconds = _run(
        action, debug=debug
    )
    if result is None:
        return
    if json_mode:
        _json_dump(
            {
                "source": str(source),
                "project": str(preparation.paths.root),
                "configuration_variant": preparation.paths.variant_key,
                "reused_setup": preparation.reused,
                "spacy_model": None if spacy_model is None else asdict(spacy_model),
                "request": asdict(preflight.setup.request),
                "workflow": _workflow_payload(preflight.workflow),
                "result": asdict(result),
                "warnings": (
                    ["--new-variant is deprecated; use the narration commands."]
                    if new_variant
                    else []
                ),
            }
        )
    else:
        render_completion(
            result,
            _output,
            elapsed_seconds=elapsed_seconds,
            configuration_variant=preparation.paths.variant_key,
        )


@metadata_app.command("show")
def metadata_show(
    project: Annotated[Path, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show effective source metadata and saved TTSForge overrides."""
    metadata_service = MetadataApplicationService(_service()[1])
    view = _run(
        lambda: metadata_service.show(ProjectPaths.for_root(project.expanduser())),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump(asdict(view))
        return
    _output.print(f"Project: {view.project}")
    for name, value in asdict(view.effective).items():
        _output.print(f"{name.replace('_', ' ').title()}: {value or 'not set'}")


@metadata_app.command("set")
def metadata_set(
    project: Annotated[Path, typer.Argument()],
    title: Annotated[str | None, typer.Option("--title")] = None,
    subtitle: Annotated[str | None, typer.Option("--subtitle")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    narrator: Annotated[str | None, typer.Option("--narrator")] = None,
    series: Annotated[str | None, typer.Option("--series")] = None,
    series_number: Annotated[str | None, typer.Option("--series-number")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    publisher: Annotated[str | None, typer.Option("--publisher")] = None,
    year: Annotated[str | None, typer.Option("--year")] = None,
    cover: Annotated[Path | None, typer.Option("--cover")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Persist project-wide audiobook metadata overrides."""
    updates = {
        name: value
        for name, value in (
            ("title", title),
            ("subtitle", subtitle),
            ("author", author),
            ("narrator", narrator),
            ("series", series),
            ("series_number", series_number),
            ("language", language),
            ("publisher", publisher),
            ("year", year),
            ("cover", cover),
        )
        if value is not None
    }
    metadata_service = MetadataApplicationService(_service()[1])
    view = _run(
        lambda: metadata_service.set(
            ProjectPaths.for_root(project.expanduser()), updates
        ),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump(asdict(view))
    else:
        _output.print(f"Updated audiobook metadata in {view.project}.")


@metadata_app.command("validate")
def metadata_validate(
    project: Annotated[Path, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Validate effective audiobook metadata."""
    metadata_service = MetadataApplicationService(_service()[1])
    report = _run(
        lambda: metadata_service.validate(ProjectPaths.for_root(project.expanduser())),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump(asdict(report))
    else:
        _output.print(
            "Audiobook metadata is valid."
            if report.valid
            else "Audiobook metadata has errors."
        )
        for finding in report.findings:
            _output.print(f"{finding.severity}: {finding.message}")
    if not report.valid:
        raise typer.Exit(code=1)


def _chapter_table(chapters: tuple[ChapterStatusView, ...]) -> Table:
    table = Table("#", "Chapter", "Characters", "Selected", "Workflow")
    for chapter in chapters:
        char_count = "" if chapter.char_count is None else f"{chapter.char_count:,}"
        table.add_row(
            str(chapter.number),
            chapter.title,
            char_count,
            "yes" if chapter.selected else "no",
            chapter.workflow_state or "",
        )
    return table


@chapters_app.command("list")
def chapters_list(
    source_or_project: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List chapters from a source book or saved project."""
    chapter_service = ChapterApplicationService(_service()[1])
    chapters = _run(
        lambda: chapter_service.list(source_or_project.expanduser()),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump([asdict(chapter) for chapter in chapters])
    else:
        _output.print(_chapter_table(chapters))


@chapters_app.command("status")
def chapters_status(
    project: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show selected chapters and matching Readio workflow states."""
    chapter_service = ChapterApplicationService(_service()[1])
    chapters = _run(
        lambda: chapter_service.status(ProjectPaths.for_root(project.expanduser())),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump([asdict(chapter) for chapter in chapters])
    else:
        _output.print(_chapter_table(chapters))


@chapters_app.command("select")
def chapters_select(
    project: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    selection: Annotated[str, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Validate a project's existing chapter selection without changing its scope."""
    chapter_service = ChapterApplicationService(_service()[1])
    selected = _run(
        lambda: chapter_service.select(
            ProjectPaths.for_root(project.expanduser()), selection
        ),
        debug=debug,
        failure_code=2,
    )
    if json_mode:
        _json_dump(asdict(selected))
    else:
        _output.print(
            f"Project {selected.project} already selects chapters {selected.selection}."
        )


@app.command("check")
def check_audiobook(
    project: Annotated[Path, typer.Argument()],
    narration: Annotated[str | None, typer.Option("--narration")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Run product-level audiobook quality checks."""

    def check() -> AudiobookQcReport:
        backend, audiobook = _service()
        narrations = NarrationApplicationService(
            audiobook, CatalogApplicationService(backend)
        )
        return QcApplicationService(audiobook, narrations).check(
            ProjectPaths.for_root(project.expanduser()), narration
        )

    report = _run(check, debug=debug, failure_code=2)
    if json_mode:
        _json_dump(asdict(report))
    else:
        _output.print(
            f"Audiobook QC {'passed' if report.passed else 'failed'} "
            f"for {report.project}."
        )
        for finding in report.findings:
            _output.print(f"{finding.severity}: {finding.id}: {finding.message}")
    if any(
        finding.id in {"project.primary_missing", "project.primary_invalid"}
        for finding in report.findings
    ):
        raise typer.Exit(code=2)
    if not report.passed:
        raise typer.Exit(code=1)


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
        tuple[ProjectVariantView, ...],
    ]:
        _, service = _service()
        inspection = service.inspect_book(source)
        paths = ProjectPaths.for_source(source, project)
        saved = service.load_saved_setup(paths)
        if saved is not None and saved.source.resolve() != source.resolve():
            raise OperationConflictError(
                f"Project {paths.root} is configured for a different source."
            )
        variants = service.list_variants(paths, source=source)
        return inspection, paths, saved, variants

    inspection, paths, saved, variants = _run(action, debug=debug)
    if json_mode:
        payload = _inspection_payload(inspection)
        payload["project"] = str(paths.root)
        payload["saved_setup"] = None if saved is None else asdict(saved)
        payload["variants"] = [asdict(variant) for variant in variants]
        _json_dump(payload)
    else:
        render_source_info(inspection, paths.root, saved, _output, variants=variants)


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
    view: Callable[[object], CatalogChoiceView | None],
    json_mode: bool,
) -> None:
    items = tuple(choice for value in values if (choice := view(value)) is not None)
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
    _catalog_command("Engines", values, view=engine_choice_view, json_mode=json_mode)


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
    _catalog_command("Targets", values, view=target_choice_view, json_mode=json_mode)


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

    def discover() -> tuple[object, ...]:
        backend = _service()[0]
        return tuple(
            backend.list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        )

    values = _run(discover, debug=debug)
    _catalog_command(
        "Voices",
        values,
        view=voice_choice_view,
        json_mode=json_mode,
    )


@app.command()
def serve(
    *,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 8765,
    token: Annotated[str, typer.Option("--token", envvar="TTSFORGE_TOKEN")],
    state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
    allow_origin: Annotated[
        list[str] | None,
        typer.Option("--allow-origin", help="Explicitly allow a browser origin."),
    ] = None,
    log_level: Annotated[
        Literal["critical", "error", "warning", "info", "debug", "trace"],
        typer.Option("--log-level"),
    ] = "info",
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Run the optional TTSForge Studio local API."""
    from ..server.launcher import run_server

    run_server(
        host=host,
        port=port,
        token=token,
        state_dir=state_dir,
        allowed_origins=allow_origin or (),
        log_level=log_level,
        debug=debug,
    )


__all__ = [
    "app",
    "cli_main",
    "convert",
    "engines",
    "info",
    "list_chapters",
    "status",
    "serve",
    "targets",
    "voices",
]


def cli_main() -> None:
    """Run the installed TTSForge command."""
    app(prog_name="ttsforge")
