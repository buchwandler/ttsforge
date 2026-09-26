"""Render the effective audiobook setup before any synthesis starts."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..audiobook import ConversionPreflight
from ..chapter_selection import format_chapter_numbers


def render_preflight(preflight: ConversionPreflight, console: Console) -> None:
    table = Table(title="Audiobook Setup", show_header=False)
    table.add_column("Setting", style="bold")
    table.add_column("Value", overflow="fold")

    book = preflight.title or preflight.source.name
    if preflight.author:
        book = f"{book} — {preflight.author}"
    project_state = "new" if preflight.project_created else "existing"
    selected = format_chapter_numbers(chapter.number for chapter in preflight.chapters)
    table.add_row("Book", book)
    table.add_row("Project", f"{preflight.project.root} ({project_state})")
    table.add_row(
        "Chapters",
        f"{selected} ({len(preflight.chapters)} of {preflight.available_chapters})",
    )
    table.add_row("Output", str(preflight.output or "default"))
    table.add_row("Format", preflight.format.upper())

    resolution = preflight.synthesis
    table.add_row("Language", resolution.language)
    table.add_row("Engine", resolution.engine)
    if resolution.voice is not None:
        table.add_row("Voice", resolution.voice)
    if resolution.model is not None:
        table.add_row("Model", resolution.model)
    if resolution.model_source is not None:
        table.add_row("Model source", resolution.model_source)
    if resolution.quality is not None:
        table.add_row("Quality", resolution.quality)
    table.add_row("Speed", f"{resolution.speed:g}x")
    table.add_row("Synthesis unit", resolution.unit)
    if resolution.spacy is not None:
        table.add_row("spaCy", resolution.spacy)
    table.add_row("Pause mode", resolution.pause_mode)
    table.add_row(
        "Loudness target",
        str(preflight.target_lufs) if preflight.target_lufs is not None else "default",
    )
    table.add_row("Bitrate", preflight.bitrate or "default")
    resources = "offline" if preflight.offline else "online"
    resources += " · refresh" if preflight.refresh else " · no refresh"
    table.add_row("Resources", resources)
    console.print(table)


def render_completion(preflight: ConversionPreflight, console: Console) -> None:
    console.print("Audiobook created")
    console.print(f"Output       {preflight.output}")
    console.print(f"Chapters     {len(preflight.chapters)}")
    console.print(f"Format       {preflight.format.upper()}")
    console.print(f"Project      {preflight.project.root}")
