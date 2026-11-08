"""Human-readable presenters for application-owned audiobook views."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..application.models import (
    AudiobookRequest,
    BookInspectionView,
    CatalogItemView,
    ConversionResultView,
    PreflightView,
    WorkflowPlanView,
)


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


def render_preflight(preflight: PreflightView, console: Console) -> None:
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
    console.print(table)
    console.print("Workflow")
    render_workflow(preflight.workflow, console)


def render_completion(result: ConversionResultView, console: Console) -> None:
    console.print("Audiobook created")
    console.print(f"Output: {result.output}")
    if result.workspace is not None:
        console.print(f"Workspace: {result.workspace} ({result.workspace_mode})")
    if result.executed_stages:
        console.print(f"Executed: {', '.join(result.executed_stages)}")
    if result.reused_stages:
        console.print(f"Reused: {', '.join(result.reused_stages)}")
    for warning in result.warnings:
        console.print(f"Warning: {warning}")


def render_catalog(
    title: str,
    items: Sequence[CatalogItemView],
    console: Console,
) -> None:
    console.print(f"{title} ({len(items)})")
    if not items:
        console.print("No matching items.")
        return
    table = Table("ID", "Label", "Engine", "Language")
    for item in items:
        table.add_row(item.id, item.label, _show(item.engine), _show(item.language))
    console.print(table)
    for item in items:
        if item.details:
            details = ", ".join(
                f"{key}: {value}" for key, value in item.details.items()
            )
            console.print(f"{item.id}: {details}")
