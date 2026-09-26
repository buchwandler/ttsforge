"""Chapter selection prompts and tables."""

from __future__ import annotations

import typer
from readio.api import AudiobookInspection
from rich.console import Console
from rich.table import Table

from ..chapter_selection import format_chapter_numbers, parse_chapter_selection


def chapter_table(inspection: AudiobookInspection) -> Table:
    table = Table("#", "Chapter", "Characters")
    for chapter in inspection.chapters:
        title = f"{'  ' * chapter.level}{chapter.title}"
        table.add_row(str(chapter.number), title, f"{chapter.char_count:,}")
    return table


def choose_chapters(
    inspection: AudiobookInspection,
    console: Console,
    *,
    book_label: str | None = None,
) -> str:
    if book_label:
        console.print(book_label)
    console.print(f"{len(inspection.chapters)} chapters detected")
    console.print(chapter_table(inspection))

    while True:
        raw = typer.prompt("Chapters to include", default="all")
        try:
            selected = parse_chapter_selection(raw, len(inspection.chapters))
            if not selected:
                raise ValueError("Chapter selection must include at least one chapter.")
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            continue
        return format_chapter_numbers(index + 1 for index in selected)
