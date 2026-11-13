"""Audiobook-focused CLI over Readio's public workflow gateway."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast

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
    ConversionResultView,
    InputOverrides,
    PreflightView,
    ProjectPaths,
    ProjectVariantView,
    SetupPreparation,
    SpacyModelView,
    WorkflowPlanView,
)
from ..application.service import (
    AudiobookApplicationService,
    require_runnable_workflow,
)
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
from .speech_profiles import discover_speech_replacement_profiles

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
    selected_target = next(
        (choice for choice in target_views if choice.id == target), None
    )

    def discover_voices() -> tuple[VoiceChoiceView, ...]:
        return tuple(
            choice
            for item in backend.list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=request.offline,
                refresh=request.refresh,
            )
            if (
                choice := voice_choice_view(
                    item,
                    default_voice=(
                        selected_target.default_voice
                        if selected_target is not None
                        else None
                    ),
                )
            )
            is not None
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


def _validate_reference_target(
    backend: Any,
    request: AudiobookRequest,
    *,
    require_voice: bool = False,
) -> None:
    if request.engine is None or request.target is None:
        return
    choices = tuple(
        target_choice_view(item)
        for item in backend.list_targets(
            engine=request.engine,
            language=request.language,
            offline=request.offline,
            refresh=request.refresh,
        )
    )
    _reject_reference_only_target(request.target, choices)
    selected = next((choice for choice in choices if choice.id == request.target), None)
    if (
        require_voice
        and request.voice is None
        and selected is not None
        and selected.voice_count > 0
        and selected.default_voice is None
    ):
        raise InputValidationError(
            f"--new-variant requires --voice for target {request.target!r}, "
            "which has no default voice."
        )


def _prepare_spacy_model(
    backend: Any,
    request: AudiobookRequest,
    *,
    json_mode: bool,
    interactive: bool,
    confirm: bool,
    assume_yes: bool,
) -> SpacyModelView | None:
    if request.spacy not in {"sm", "md", "lg", "trf"}:
        return None
    if request.language is None:
        raise InputValidationError("Language is required to resolve a spaCy model.")

    model = cast(
        SpacyModelView, backend.inspect_spacy_model(request.language, request.spacy)
    )
    if not json_mode:
        _output.print("spaCy")
        _output.print(f"  Model  {model.model}")
        status = "installed"
        if model.model_version:
            status += f" {model.model_version}"
        if not model.installed:
            status = "not installed"
        _output.print(f"  Status {status}")
    if model.installed:
        return model
    if request.offline:
        return cast(
            SpacyModelView,
            backend.ensure_spacy_model(request.language, request.spacy, offline=True),
        )
    if confirm and not typer.confirm(f"Download {model.model}?", default=True):
        raise InputValidationError(
            f"spaCy model {model.model!r} is required to continue."
        )
    if not interactive and not assume_yes:
        raise InputValidationError(
            f"spaCy model {model.model!r} is missing. "
            "Run interactively or pass --yes to download it."
        )

    if not json_mode:
        _output.print(f"Installing {model.model}...")
    installed = cast(
        SpacyModelView, backend.ensure_spacy_model(request.language, request.spacy)
    )
    if not json_mode:
        version = f" {installed.model_version}" if installed.model_version else ""
        _output.print(f"Installed {installed.model}{version}")
    return installed


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
                "Create a separate setup and output in the existing project, reusing "
                "source conversion and semantic compile state."
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
        preparation = service.prepare_setup(
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
            _validate_reference_target(
                backend, selected, require_voice=selected.new_variant
            )
        resolved = service.save_setup(preparation, selected)
        preparation = resolved.preparation
        spacy_model = _prepare_spacy_model(
            backend,
            resolved.request,
            json_mode=interaction.json,
            interactive=interaction.interactive,
            confirm=interaction.confirm,
            assume_yes=yes,
        )
        preflight = service.preflight(resolved)
        if not interaction.json:
            render_preflight(preflight, _output, spacy_model=spacy_model)
        require_runnable_workflow(preflight.workflow)
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
            result = service.render(resolved, on_progress=progress)
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
            }
        )
    else:
        render_completion(
            result,
            _output,
            elapsed_seconds=elapsed_seconds,
            configuration_variant=preparation.paths.variant_key,
        )


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

    def discover() -> tuple[tuple[object, ...], str | None]:
        backend = _service()[0]
        values = tuple(
            backend.list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        )
        default_voice = None
        if engine is not None and target is not None:
            targets = tuple(
                target_choice_view(item)
                for item in backend.list_targets(
                    engine=engine,
                    language=language,
                    offline=offline,
                    refresh=refresh,
                )
            )
            selected = next((item for item in targets if item.id == target), None)
            if selected is not None:
                default_voice = selected.default_voice
        return values, default_voice

    values, default_voice = _run(discover, debug=debug)
    _catalog_command(
        "Voices",
        values,
        view=lambda item: voice_choice_view(item, default_voice=default_voice),
        json_mode=json_mode,
    )


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
