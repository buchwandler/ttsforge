from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from typer.testing import CliRunner

from ttsforge.application.library import ProjectSummary
from ttsforge.cli import app

cli_app = import_module("ttsforge.cli.app")


class FakeLibrary:
    def __init__(self, summary: ProjectSummary) -> None:
        self.summary = summary

    def list(self, root: Path) -> tuple[ProjectSummary, ...]:
        return (self.summary,)

    def inspect(self, project: Path) -> ProjectSummary:
        return self.summary


def test_projects_list_json_and_info_commands(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "Novel.ttsforge"
    summary = ProjectSummary(
        project_id="project-id",
        title="Novel",
        author="Writer",
        source=tmp_path / "Novel.epub",
        project=project,
        chapter_count=4,
        selected_chapter_count=3,
        narrations=(),
        primary_narration_id="primary",
        outputs=(tmp_path / "Novel.m4b",),
        qc_state="unknown",
        active_job_id=None,
        last_activity=None,
        error=None,
    )
    monkeypatch.setattr(cli_app, "_library_service", lambda: FakeLibrary(summary))
    runner = CliRunner()

    listed = runner.invoke(app, ["projects", "list", str(tmp_path), "--json"])
    inspected = runner.invoke(app, ["projects", "info", str(project)])

    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)[0]["project_id"] == "project-id"
    assert inspected.exit_code == 0, inspected.output
    assert "Chapters: 3/4 selected" in inspected.output
    assert "QC: unknown" in inspected.output
