"""Human-readable presenters for application-owned audiobook views."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..application.models import (
    AudiobookRequest,
    BookInspectionView,
    ConversionResultView,
    PreflightView,
    SpacyModelView,
    WorkflowPlanView,
)
from .catalog import (
    CatalogChoiceView,
    EngineChoiceView,
    TargetChoiceView,
    VoiceChoiceView,
)
from .progress import format_elapsed


def _show(value: object | None) -> str:
    return "not set" if value is None else str(value)


def chapter_table(inspection: BookInspectionView) -> Table:
    table = Table("#", "Title", "Characters")
    for chapter in inspection.chapters:
        count = "" if chapter.char_count is None else f"{chapter.char_count:,}"
        table.add_row(str(chapter.number), chapter.title, count)
    return table


def render_source_list(inspection: BookInspectionView, console: Console) -> None:
    console.print(chapter_table(inspection))


def render_source_info(
    inspection: BookInspectionView,
    project: Path,
    saved: AudiobookRequest | None,
    console: Console,
) -> None:
    table = Table("Field", "Value", show_header=False)
    for label, value in (
        ("Title", inspection.title),
        ("Author", inspection.author),
        ("Language", inspection.language),
        ("Chapter count", len(inspection.chapters)),
        ("Source", inspection.source),
        ("Default project", project),
        ("Existing setup", "yes" if saved is not None else "no"),
    ):
        table.add_row(label, _show(value))
    if saved is not None:
        for label, value in (
            ("Saved chapters", saved.chapters),
            ("Saved output", saved.output),
            ("Saved engine", saved.engine),
            ("Saved target", saved.target),
            ("Saved voice", saved.voice),
        ):
            table.add_row(label, _show(value))
    console.print(table)


def render_workflow(plan: WorkflowPlanView, console: Console) -> None:
    table = Table("Stage", "Action", "State", "Reason")
    for step in plan.steps:
        table.add_row(step.stage, step.action, step.state, step.reason)
    console.print(table)
    for warning in plan.warnings:
        console.print(f"Warning: {warning}")


def render_preflight(
    preflight: PreflightView,
    console: Console,
    *,
    spacy_model: SpacyModelView | None = None,
) -> None:
    setup = preflight.setup
    request = setup.request
    inspection = setup.preparation.inspection
    table = Table("Setting", "Value", show_header=False)
    table.add_row("Book", request.title or inspection.source.name)
    table.add_row("Author", _show(request.author))
    table.add_row("Project", str(setup.preparation.paths.root))
    table.add_row("Chapters", _show(request.chapters))
    table.add_row("Output", _show(request.output))
    table.add_row("Format", "M4B")
    table.add_row("Language", _show(request.language))
    table.add_row("Engine", _show(request.engine))
    table.add_row("Target", _show(request.target))
    table.add_row("Voice", _show(request.voice))
    if request.spacy == "off":
        spacy_summary = "off"
    elif request.spacy == "auto":
        spacy_summary = "auto (installed models only)"
    elif spacy_model is not None:
        version = f" {spacy_model.model_version}" if spacy_model.model_version else ""
        spacy_summary = f"{request.spacy}: {spacy_model.model}{version}"
    else:
        spacy_summary = request.spacy or "existing Readio behavior"
    table.add_row("spaCy", spacy_summary)
    table.add_row(
        "Speech profile",
        _show(request.speech_profile) if request.speech_profile else "none",
    )
    table.add_row("Pause timing", request.pause_timing or "fixed")
    console.print(table)
    console.print("Workflow")
    render_workflow(preflight.workflow, console)


def render_completion(
    result: ConversionResultView,
    console: Console,
    *,
    elapsed_seconds: float | None = None,
) -> None:
    console.print("Audiobook created")
    console.print(f"Output: {result.output}")
    if elapsed_seconds is not None:
        console.print(f"Elapsed: {format_elapsed(elapsed_seconds)}")
    if result.workspace is not None:
        console.print(f"Workspace: {result.workspace} ({result.workspace_mode})")
    if result.executed_stages:
        console.print(f"Executed: {', '.join(result.executed_stages)}")
    if result.reused_stages:
        console.print(f"Reused: {', '.join(result.reused_stages)}")
    for warning in result.warnings:
        console.print(f"Warning: {warning}")


def _engine_catalog_row(item: EngineChoiceView) -> tuple[str, list[str], list[str]]:
    line = item.id
    if item.version:
        line += f"  {item.version}"
    tags = []
    if not item.runnable:
        tags.append("not runnable")
    elif not item.installed:
        tags.append("not installed")
    details = [" · ".join(item.features)] if item.features else []
    if item.reason:
        details.append(f"missing dependency: {item.reason}")
    return line, tags, details


def _target_catalog_row(item: TargetChoiceView) -> tuple[str, list[str], list[str]]:
    tags = []
    if item.reference_only:
        tags.append("reference audio required, unsupported")
    elif not item.runtime_available:
        tags.append("runtime unavailable")
    elif item.status and item.status != "ready":
        tags.append(item.status)
    details = []
    if item.languages:
        details.append("/".join(item.languages))
    if item.voice_count:
        details.append(f"{item.voice_count} voices")
    if item.qualities:
        details.append(", ".join(item.qualities))
    if item.sample_rate:
        details.append(f"{item.sample_rate // 1000} kHz")
    if item.default_voice:
        details.append(f"default voice: {item.default_voice}")
    if item.voice_mode:
        details.append(f"voice mode: {item.voice_mode}")
    if item.features:
        details.append(" · ".join(item.features))
    return item.id, tags, details


def _voice_catalog_row(item: VoiceChoiceView) -> tuple[str, list[str], list[str]]:
    tags = ["default"] if item.default else []
    if not item.runtime_available:
        tags.append("runtime unavailable")
    identity = [item.gender if item.gender != "unknown" else "unknown gender"]
    if item.locale and item.locale.casefold() != "unknown":
        identity.append(item.locale)
    if item.language_label:
        identity.append(item.language_label)
    elif item.language and item.language.casefold() != "unknown":
        identity.append(item.language)
    return item.id, tags, [" · ".join(identity)]


def _catalog_row(
    item: CatalogChoiceView,
) -> tuple[str, list[str], list[str]]:
    if isinstance(item, EngineChoiceView):
        return _engine_catalog_row(item)
    if isinstance(item, TargetChoiceView):
        return _target_catalog_row(item)
    return _voice_catalog_row(item)


def render_catalog(
    title: str,
    items: Sequence[CatalogChoiceView],
    console: Console,
) -> None:
    console.print(f"{title} ({len(items)})")
    if not items:
        console.print("No matching items.")
        return

    for index, item in enumerate(items, 1):
        primary, tags, details = _catalog_row(item)
        styled = Text(f"  {index}. {primary}")
        if tags:
            styled.append("  " + "  ".join(f"[{tag}]" for tag in tags), style="dim")
        console.print(styled)
        for detail in details:
            console.print(Text(f"     {detail}"))
