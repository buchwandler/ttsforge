"""CLI contract tests for Readio-backed audiobook workflows."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from readio.api import (
    AudiobookChapter,
    AudiobookExportResult,
    AudiobookInspection,
    PreviewResult,
    ProjectRef,
    ProjectStatus,
)
from typer.testing import CliRunner

from ttsforge.audiobook import ProjectSetup

cli_module = import_module("ttsforge.cli.app")


runner = CliRunner()


def _inspection(source: Path) -> AudiobookInspection:
    return AudiobookInspection(
        source=source,
        metadata={"title": "A title", "authors": ["An author"]},
        chapters=(
            AudiobookChapter(
                number=1,
                source_id="chapter-1",
                title="Chapter One",
                href="chapter-1.xhtml",
                parent_id=None,
                level=0,
                char_count=12,
                markdown="# Chapter One",
            ),
        ),
    )


class _FakeConverter:
    def __init__(self, source: Path, project: ProjectRef) -> None:
        self.inspection = _inspection(source)
        self.project = project
        self.options = None

    def inspect(self, source: Path) -> AudiobookInspection:
        return self.inspection

    def create_or_open_project(self, options, *, inspection):  # type: ignore[no-untyped-def]
        self.options = options
        return ProjectSetup(project=self.project, created=True, selected_chapters=(1,))

    def build_and_export(self, project, options):  # type: ignore[no-untyped-def]
        return AudiobookExportResult(
            project=self.project,
            output_path=self.project.root.with_suffix(".m4b"),
            format="m4b",
            output_sha256="digest",
            export_id="export-1",
            chapter_count=1,
        )

    def status(self, project: Path) -> ProjectStatus:
        return ProjectStatus(self.project, stages=(), issues=(), next_actions=())

    def preview(self, project, options, *, selection):  # type: ignore[no-untyped-def]
        return PreviewResult(
            project=self.project,
            profile_id="profile",
            plan_ids=(),
            reused=0,
            rendered=1,
            activated=False,
            sample_rate=24000,
            frames=24000,
            items=1,
        )


def test_help_exposes_only_the_audiobook_frontend_commands() -> None:
    result = runner.invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "convert" in result.output
    assert "list" in result.output
    assert "status" in result.output
    assert "phonemes" not in result.output
    assert "download" not in result.output

    assert "engines" in result.output
    assert "formats" in result.output
    assert "doctor" in result.output
    assert "config" in result.output
    assert "ssmd" in result.output


def test_list_and_info_use_the_public_inspection_result(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(cli_module, "_converter", lambda json_mode: converter)

    listed = runner.invoke(cli_module.app, ["list", str(source)])
    described = runner.invoke(cli_module.app, ["info", str(source), "--json"])

    assert listed.exit_code == 0, listed.output
    assert "Chapter One" in listed.output
    assert described.exit_code == 0, described.output
    assert json.loads(described.output)["metadata"]["title"] == "A title"


def test_convert_initializes_readio_project_and_keeps_json_stdout_clean(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(cli_module, "_converter", lambda json_mode: converter)

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["project"] == str(project.root)
    assert payload["created"] is True
    assert payload["selected_chapters"] == [1]
    assert payload["format"] == "m4b"
    assert payload["output"] == str(project.root.with_suffix(".m4b"))
    assert payload["result"]["chapter_count"] == 1
    assert converter.options.chapters == "1"
    assert result.stderr == ""


def test_status_and_preview_are_project_service_workflows(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(cli_module, "_converter", lambda json_mode: converter)

    status = runner.invoke(cli_module.app, ["status", str(project.root), "--json"])
    preview = runner.invoke(cli_module.app, ["preview", str(source), "--json"])

    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["project"]["root"] == str(project.root)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["result"]["items"] == 1
