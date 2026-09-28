"""Render the effective audiobook setup before any synthesis starts."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..audiobook import ConversionPreflight
from ..chapter_selection import format_chapter_numbers


def _effective(value: str | None) -> str:
    return value if value is not None else "auto / engine default"


def _lexicon_value(value: tuple[str, ...] | None) -> str:
    if value is None:
        return "auto"
    if not value:
        return "disabled"
    return ", ".join(value)


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
    table.add_row("Language", _effective(resolution.language))
    table.add_row("Engine", _effective(resolution.engine))
    table.add_row("Voice", _effective(resolution.voice))
    table.add_row("Model", _effective(resolution.model))
    table.add_row("Model source", _effective(resolution.model_source))
    table.add_row("Quality", _effective(resolution.quality))
    table.add_row("Speed", f"{resolution.speed:g}x")
    table.add_row("spaCy", _effective(resolution.spacy))
    table.add_row("Short sentences", _effective(resolution.short_sentence))
    table.add_row("Lexicons", _lexicon_value(resolution.lexicons))
    table.add_row("G2P fallback", _effective(resolution.g2p_fallback))
    table.add_row("Lexicon data", _effective(resolution.lexicon_data_policy))
    table.add_row("Voice level", _effective(resolution.voice_level))
    table.add_row("Pause mode", _effective(resolution.pause_mode))
    table.add_row("Synthesis unit", _effective(resolution.unit))
    table.add_row(
        "Experimental", "enabled" if resolution.allow_experimental else "disabled"
    )
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
