"""Chapter selection prompts and tables."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..application.models import BookInspectionView
from ..chapter_selection import normalize_chapter_selection


def chapter_table(inspection: BookInspectionView) -> Table:
    table = Table("#", "Chapter", "Characters")
    for chapter in inspection.chapters:
        count = "" if chapter.char_count is None else f"{chapter.char_count:,}"
        table.add_row(str(chapter.number), chapter.title, count)
    return table


def choose_chapters(
    inspection: BookInspectionView,
    console: Console,
    *,
    default: str = "all",
) -> str:
    if not inspection.chapters:
        raise ValueError("No chapters were discovered in the source book.")

    console.print(f"{len(inspection.chapters)} chapters detected")
    console.print(chapter_table(inspection))
    console.print(
        "Select all, a chapter number, ranges, or comma-separated combinations."
    )

    while True:
        raw = typer.prompt(
            "Chapters to include (all, 4, 2-7, 1,3,8-10)", default=default
        ).strip()
        try:
            return normalize_chapter_selection(raw, len(inspection.chapters))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
