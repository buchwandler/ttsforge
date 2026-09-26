"""Audiobook-focused Typer CLI backed by Readio's public application API."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from readio.api import (
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_AUDIOBOOK_FORMATS,
    AudiobookExportResult,
    AudiobookInspection,
    DiscoveryOptions,
    ModelQuery,
    PreviewResult,
    ProjectBuildResult,
    Readio,
    ReadioError,
    SSMDAnalysis,
    VoiceQuery,
)
from rich.console import Console
from rich.table import Table

from ..audiobook import AudiobookConverter, ProjectSetup
from ..options import AudiobookOptions
from ..progress import RichReadioProgress
from ..readio_backend import create_readio

T = TypeVar("T")
_output = Console(stderr=False, highlight=False)


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

config_app = typer.Typer(
    no_args_is_help=True, help="Inspect and update Readio configuration."
)
ssmd_app = typer.Typer(
    no_args_is_help=True, help="Check and author SSMD through Readio."
)


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Convert EPUB books using reusable Readio projects."""
    del version


def _run(action: Callable[[], T], *, debug: bool) -> T:
    try:
        return action()
    except (ReadioError, ValueError, OSError) as exc:
        if debug:
            traceback.print_exc()
        else:
            typer.echo(f"Error: {exc}", err=True)
            code = getattr(exc, "code", None)
            if code:
                typer.echo(f"Code: {code}", err=True)
            details = getattr(exc, "details", None)
            if details:
                typer.echo(
                    json.dumps(details, ensure_ascii=False, default=str),
                    err=True,
                )
            typer.echo("Use --debug for a traceback.", err=True)
        raise typer.Exit(code=1) from exc


def _converter(json_mode: bool) -> AudiobookConverter:
    progress = RichReadioProgress(json_mode=json_mode)
    return AudiobookConverter(on_event=progress)


def _readio() -> Readio:
    return create_readio()


def _validate_output_format(output_format: str) -> None:
    supported = (*SUPPORTED_AUDIO_FORMATS, *SUPPORTED_AUDIOBOOK_FORMATS)
    if output_format.lower() not in supported:
        raise ValueError(
            f"Unsupported audio format {output_format!r}; "
            f"choose from {', '.join(supported)}."
        )


def _options(
    source: Path,
    *,
    project: Path | None,
    chapters: str,
    output: Path | None,
    output_format: str,
    voice: str | None,
    language: str | None,
    engine: str | None,
    speed: float | None,
    bitrate: str | None,
    target_lufs: float | None,
    offline: bool,
    refresh: bool,
    force: bool,
    fresh: bool,
    title: str | None = None,
    author: str | None = None,
    cover: Path | None = None,
) -> AudiobookOptions:
    resolved_output = output or source.with_suffix(f".{output_format}")
    return AudiobookOptions(
        source=source,
        project=project,
        chapters=chapters,
        output=resolved_output,
        format=output_format,
        language=language,
        voice=voice,
        engine=engine,
        speed=speed,
        bitrate=bitrate,
        target_lufs=target_lufs,
        offline=offline,
        refresh=refresh,
        force=force,
        fresh=fresh,
        title=title,
        author=author,
        cover=cover,
    )


def _chapter_table(inspection: AudiobookInspection) -> Table:
    table = Table("#", "Chapter", "Characters")
    for chapter in inspection.chapters:
        title = f"{'  ' * chapter.level}{chapter.title}"
        table.add_row(str(chapter.number), title, f"{chapter.char_count:,}")
    return table


def _choose_chapters(inspection: AudiobookInspection) -> str:
    _output.print(_chapter_table(inspection))
    return typer.prompt("Chapters to include", default="all")


def _json_dump(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command()
def convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("-o", "--output")] = None,
    output_format: Annotated[
        str,
        typer.Option("-f", "--format", help="Output format; defaults to m4b."),
    ] = "m4b",
    project: Annotated[Path | None, typer.Option("--project")] = None,
    chapters: Annotated[
        str | None,
        typer.Option("--chapters", help="Chapter numbers/ranges, or all."),
    ] = None,
    interactive_chapters: Annotated[
        bool,
        typer.Option("--interactive-chapters", help="Prompt to select chapters."),
    ] = False,
    voice: Annotated[str | None, typer.Option("--voice")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    speed: Annotated[float | None, typer.Option("--speed", min=0.5, max=2.0)] = None,
    bitrate: Annotated[str | None, typer.Option("--bitrate")] = None,
    target_lufs: Annotated[float | None, typer.Option("--target-lufs")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace owned output."),
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Create a separate project; preserve existing work.",
        ),
    ] = False,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    cover: Annotated[
        Path | None,
        typer.Option("--cover", exists=True, dir_okay=False),
    ] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Inspect a book and create or reuse its persistent Readio project."""

    def action() -> tuple[
        AudiobookInspection,
        ProjectSetup,
        AudiobookExportResult | ProjectBuildResult,
    ]:
        _validate_output_format(output_format)
        converter = _converter(json_mode)
        inspection = converter.inspect(source)
        selected_chapters = chapters
        if interactive_chapters and selected_chapters is None:
            selected_chapters = _choose_chapters(inspection)
        options = _options(
            source,
            project=project,
            chapters=selected_chapters or "all",
            output=output,
            output_format=output_format.lower(),
            voice=voice,
            language=language,
            engine=engine,
            speed=speed,
            bitrate=bitrate,
            target_lufs=target_lufs,
            offline=offline,
            refresh=refresh,
            force=force,
            fresh=fresh,
            title=title,
            author=author,
            cover=cover,
        )
        setup = converter.create_or_open_project(options, inspection=inspection)
        result = converter.build_and_export(setup.project, options)
        return inspection, setup, result

    inspection, setup, result = _run(action, debug=debug)
    if json_mode:
        _json_dump(
            {
                "source": str(source),
                "project": str(setup.project.root),
                "created": setup.created,
                "selected_chapters": list(setup.selected_chapters),
                "output": str(result.output_path) if result.output_path else None,
                "format": (
                    result.format
                    if isinstance(result, AudiobookExportResult)
                    else output_format.lower()
                ),
                "result": asdict(result),
            }
        )
        return
    _output.print(f"Book: {source}")
    _output.print(f"Project: {setup.project.root}")
    if result.output_path:
        _output.print(f"Output: {result.output_path}")
    if setup.created:
        _output.print(
            "Created Readio project with chapters: "
            + ", ".join(map(str, setup.selected_chapters))
        )
    else:
        _output.print(
            "Reusing existing Readio project; its chapter selection is persistent."
        )
    _output.print(f"Available chapters: {len(inspection.chapters)}")


@app.command("list")
def list_chapters(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List EPUB chapters using Readio's audiobook inspection API."""
    inspection = _run(lambda: _converter(json_mode).inspect(source), debug=debug)
    if json_mode:
        _json_dump(asdict(inspection))
    else:
        _output.print(_chapter_table(inspection))


@app.command()
def info(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show EPUB metadata and chapter count from Readio inspection."""
    inspection = _run(lambda: _converter(json_mode).inspect(source), debug=debug)
    if json_mode:
        _json_dump(asdict(inspection))
        return
    _output.print(f"Source: {inspection.source}")
    for key, value in inspection.metadata.items():
        _output.print(f"{key.replace('_', ' ').title()}: {value}")
    _output.print(f"Chapters: {len(inspection.chapters)}")
    _output.print(f"Candidate output: {source.with_suffix('.m4b')}")


@app.command()
def status(
    project: Annotated[Path | None, typer.Argument()] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show authoritative Readio project state and next actions."""
    project_path = project or Path.cwd()
    result = _run(lambda: _converter(json_mode).status(project_path), debug=debug)
    if json_mode:
        _json_dump(asdict(result))
        return
    _output.print(f"Project: {result.project.root}")
    table = Table("Stage", "State", "Reason")
    for stage in result.stages:
        table.add_row(stage.stage, stage.state, stage.reason or "")
    _output.print(table)
    for action in result.next_actions:
        _output.print(f"Next: {action.stage} — {action.reason}")


@app.command()
def preview(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    project: Annotated[Path | None, typer.Option("--project")] = None,
    chapters: Annotated[str, typer.Option("--chapters")] = "all",
    selection: Annotated[str, typer.Option("--selection")] = "first:3",
    voice: Annotated[str | None, typer.Option("--voice")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    speed: Annotated[float | None, typer.Option("--speed", min=0.5, max=2.0)] = None,
    target_lufs: Annotated[float | None, typer.Option("--target-lufs")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Render a preview through the same Readio project pipeline as conversion."""

    def action() -> tuple[ProjectSetup, PreviewResult]:
        converter = _converter(json_mode)
        inspection = converter.inspect(source)
        options = _options(
            source,
            project=project,
            chapters=chapters,
            output=None,
            output_format="m4b",
            voice=voice,
            language=language,
            engine=engine,
            speed=speed,
            bitrate=None,
            target_lufs=target_lufs,
            offline=False,
            refresh=False,
            force=False,
            fresh=False,
        )
        setup = converter.create_or_open_project(options, inspection=inspection)
        result = converter.preview(setup.project, options, selection=selection)
        return setup, result

    setup, result = _run(action, debug=debug)
    if json_mode:
        _json_dump({"project": str(setup.project.root), "result": asdict(result)})
    else:
        _output.print(f"Preview project: {setup.project.root}")
        _output.print(
            f"Preview rendered {result.items} items ({result.frames} frames at "
            f"{result.sample_rate} Hz)."
        )
        if result.output_path:
            _output.print(f"Output: {result.output_path}")


@app.command()
def plan(
    project: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Create/update speech plans in a Readio project."""
    result = _run(lambda: _converter(json_mode).plan(project), debug=debug)
    if json_mode:
        _json_dump(asdict(result))
    else:
        _output.print(
            f"Planned {len(result.scopes)} project scopes in {result.project.root}"
        )


def _catalog_payload(listing) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "items": [asdict(item) for item in listing.items],
        "discovery": asdict(listing.discovery),
    }


@app.command()
def voices(
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    gender: Annotated[str | None, typer.Option("--gender")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List voices from Readio's discovery catalog."""
    result = _run(
        lambda: _readio().catalog.voices_listing(
            VoiceQuery(language=language, model=model, engine=engine, gender=gender),
            discovery=DiscoveryOptions(offline=offline, refresh=refresh),
        ),
        debug=debug,
    )
    if json_mode:
        _json_dump(_catalog_payload(result))
        return
    table = Table("Selector", "Language", "Model", "Engine", "Status", "Runtime")
    for voice in result.items:
        table.add_row(
            voice.selector or voice.qualified_id,
            voice.locale,
            voice.model,
            voice.engine,
            voice.status,
            "yes" if voice.runtime_available else "no",
        )
    _output.print(table)


@app.command()
def models(
    engine: Annotated[str | None, typer.Option("--engine")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List models and synthesis targets from Readio's discovery catalog."""
    result = _run(
        lambda: _readio().catalog.models_listing(
            ModelQuery(engine=engine, language=language, status=status),
            discovery=DiscoveryOptions(offline=offline, refresh=refresh),
        ),
        debug=debug,
    )
    if json_mode:
        _json_dump(_catalog_payload(result))
        return
    table = Table("Model/target", "Engine", "Status", "Runtime", "Default voice")
    for model_info in result.items:
        table.add_row(
            model_info.id,
            model_info.backend,
            model_info.status,
            "yes" if model_info.runtime_available else "no",
            model_info.default_voice or "",
        )
    _output.print(table)


@app.command()
def engines(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show synthesis engines known to Readio."""
    result = _run(lambda: _readio().catalog.engines(), debug=debug)
    if json_mode:
        _json_dump([asdict(item) for item in result])
        return
    table = Table("Engine", "Version", "Installed", "Runnable", "Missing dependency")
    for engine in result:
        table.add_row(
            engine.id,
            engine.version or "—",
            "yes" if engine.installed else "no",
            "yes" if engine.runnable else "no",
            engine.missing_dependency or "",
        )
    _output.print(table)


@app.command()
def formats(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List Readio generic audio formats and audiobook export formats."""
    result = _run(lambda: _readio().catalog.audio_formats(), debug=debug)
    rows = [asdict(item) for item in result]
    rows.extend(
        {
            "id": format_id,
            "suffix": f".{format_id}",
            "available": None,
            "reason": (
                "Audiobook-specific export; availability is checked at export time."
            ),
        }
        for format_id in SUPPORTED_AUDIOBOOK_FORMATS
        if format_id not in {item.id for item in result}
    )
    if json_mode:
        _json_dump(rows)
        return
    table = Table("Format", "Suffix", "Available", "Details")
    for row in rows:
        available = row["available"]
        table.add_row(
            str(row["id"]),
            str(row["suffix"]),
            "API" if available is None else "yes" if available else "no",
            str(row["reason"] or ""),
        )
    _output.print(table)


@app.command()
def doctor(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Report Readio runtime, dependency, engine, path, and format diagnostics."""
    report = _run(lambda: _readio().diagnostics.run(), debug=debug)
    if json_mode:
        _json_dump(asdict(report))
        return
    _output.print(f"Readio {report.readio_version} · Python {report.python_version}")
    _output.print(
        f"Config: {report.config_path} "
        f"({'found' if report.config_exists else 'missing'})"
    )
    engine_table = Table("Engine", "Status", "Version", "Missing dependency")
    for engine in report.engines:
        engine_table.add_row(
            engine.id,
            engine.status,
            engine.version or "—",
            engine.missing_dependency or "",
        )
    _output.print(engine_table)
    missing = [item.id for item in report.dependencies if not item.available]
    if missing:
        _output.print("Missing optional dependencies: " + ", ".join(missing))
    unavailable = [item for item in report.audio_formats if not item.available]
    if unavailable:
        _output.print(
            "Unavailable audio formats: "
            + ", ".join(f"{item.id} ({item.reason})" for item in unavailable)
        )
    for path in report.paths:
        state = "present" if path.exists else "not created"
        _output.print(f"{path.name}: {path.path} ({state})")


@config_app.command("path")
def config_path(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show the active Readio configuration path."""
    path = _run(lambda: _readio().configuration.path(), debug=debug)
    _json_dump({"path": str(path)}) if json_mode else _output.print(str(path))


@config_app.command("show")
def config_show(
    path: Annotated[Path | None, typer.Option("--path")] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Show persisted Readio configuration (not a TTSForge shadow config)."""

    def action():
        api = _readio()
        active_path = api.configuration.path() if path is None else path
        return active_path, api.configuration.load(path)

    active_path, config = _run(action, debug=debug)
    if not json_mode:
        _output.print(f"Readio configuration: {active_path}")
    _json_dump({"path": str(active_path), "config": asdict(config)})


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument()],
    value: Annotated[str, typer.Argument()],
    path: Annotated[Path | None, typer.Option("--path")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Set a persistent Readio key, e.g. reader.voice or languages.en.voice."""

    def action():
        api = _readio()
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        api.configuration.set_value(key, parsed, path=path)
        active_path = api.configuration.path() if path is None else path
        return active_path

    active_path = _run(action, debug=debug)
    _output.print(f"Updated Readio setting {key!r} in {active_path}.")


@config_app.command("init")
def config_init(
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Initialize Readio's persistent configuration and standard directories."""
    result = _run(
        lambda: _readio().configuration.initialize(overwrite=overwrite),
        debug=debug,
    )
    if json_mode:
        _json_dump(asdict(result))
    else:
        _output.print(f"Initialized Readio configuration: {result.path}")
        for directory in result.created_directories:
            _output.print(f"Created: {directory}")


@config_app.command("languages")
def config_languages(
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """List configured Readio language profiles."""
    profiles = _run(lambda: _readio().configuration.language_profiles(), debug=debug)
    payload = {language: asdict(settings) for language, settings in profiles.items()}
    _json_dump(payload) if json_mode else _output.print_json(data=payload)


@config_app.command("language")
def config_language(
    language: Annotated[str, typer.Argument()],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Resolve the exact or base-language Readio profile for a locale."""
    result = _run(
        lambda: _readio().configuration.resolve_language_profile(language),
        debug=debug,
    )
    _json_dump(asdict(result)) if json_mode else _output.print_json(data=asdict(result))


def _show_ssmd_analysis(analysis: SSMDAnalysis) -> None:
    _output.print(f"Provider: {analysis.provider}")
    if analysis.voice_references:
        references = Table("Voice reference", "Uses", "Lines", "Resolved")
        unresolved = set(analysis.unresolved_references)
        for item in analysis.voice_references:
            references.add_row(
                item.reference,
                str(item.count),
                ", ".join(map(str, item.lines)),
                "no" if item.reference in unresolved else "yes",
            )
        _output.print(references)
    for diagnostic in analysis.diagnostics:
        _output.print(
            f"{diagnostic.severity}: {diagnostic.message}"
            + (f" (line {diagnostic.line})" if diagnostic.line else "")
        )


def _show_ssmd_check(result, *, json_mode: bool) -> None:  # type: ignore[no-untyped-def]
    if json_mode:
        _json_dump(asdict(result))
    else:
        _output.print(f"SSMD check: {'valid' if result.ok else 'issues found'}")
        _show_ssmd_analysis(result.analysis)
        if result.roundtrip is not None:
            _output.print(f"Roundtrip: {result.roundtrip.get('ok', 'completed')}")
    if not result.ok:
        raise typer.Exit(code=1)


@ssmd_app.command("check")
def ssmd_check(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    roundtrip: Annotated[bool, typer.Option("--roundtrip")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Check SSMD through Readio and optionally perform a roundtrip check."""
    result = _run(
        lambda: _readio().ssmd.check(source, roundtrip=roundtrip),
        debug=debug,
    )
    _show_ssmd_check(result, json_mode=json_mode)


@ssmd_app.command("validate")
def ssmd_validate(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    roundtrip: Annotated[bool, typer.Option("--roundtrip")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Require resolvable SSMD voices and report Readio diagnostics."""
    result = _run(
        lambda: _readio().ssmd.validate(source, roundtrip=roundtrip),
        debug=debug,
    )
    _show_ssmd_check(result, json_mode=json_mode)


@ssmd_app.command("analyze")
def ssmd_analyze(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Analyze SSMD voice references through Readio."""
    result = _run(lambda: _readio().ssmd.analyze(source), debug=debug)
    if json_mode:
        _json_dump(asdict(result))
    else:
        _show_ssmd_analysis(result)
        _output.print(f"Analysis: {'valid' if result.ok else 'issues found'}")
    if not result.ok:
        raise typer.Exit(code=1)


@ssmd_app.command("roundtrip")
def ssmd_roundtrip(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Run Readio's SSMD authoring roundtrip check."""
    result = _run(lambda: _readio().ssmd.roundtrip_check(source), debug=debug)
    _show_ssmd_check(result, json_mode=json_mode)


@ssmd_app.command("materialize")
def ssmd_materialize(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    bindings: Annotated[
        str,
        typer.Option("--bindings", help="JSON object of reference:voice pairs."),
    ],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    in_place: Annotated[bool, typer.Option("--in-place")] = False,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Materialize explicit SSMD voice bindings via Readio's authoring API."""

    def action():
        try:
            parsed = json.loads(bindings)
        except json.JSONDecodeError as error:
            raise ValueError("--bindings must be a JSON object") from error
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parsed.items()
        ):
            raise ValueError("--bindings must map string references to string voices")
        return _readio().ssmd.materialize_bindings(
            source, parsed, provider=provider, output=output, in_place=in_place
        )

    result = _run(action, debug=debug)
    if json_mode:
        _json_dump(asdict(result))
    else:
        _output.print(
            f"Materialized {result.binding_count} binding(s) to {result.output_path}."
        )


app.add_typer(config_app, name="config")
app.add_typer(ssmd_app, name="ssmd")


def cli_main() -> None:
    """Run the installed TTSForge command."""
    app(prog_name="ttsforge")


__all__ = ["app", "cli_main"]
