"""CLI contract tests for Readio-backed audiobook workflows."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from readio.api import (
    AudiobookChapter,
    AudiobookExportResult,
    AudiobookInspection,
    AudiobookProjectChapter,
    PreviewResult,
    ProjectRef,
    ProjectStatus,
    SynthesisResolution,
)
from typer.testing import CliRunner

from ttsforge.audiobook import ConversionPreflight, ProjectSetup
from ttsforge.chapter_selection import parse_chapter_selection
from ttsforge.ui.interaction import InteractionMode

cli_module = import_module("ttsforge.cli.app")


runner = CliRunner()


def _set_mode(
    monkeypatch,
    *,
    interactive: bool,
    json_mode: bool = False,
    confirm: bool | None = None,
) -> None:
    mode = InteractionMode(
        interactive=interactive,
        json=json_mode,
        live_progress=interactive,
        confirm=interactive if confirm is None else confirm,
    )
    monkeypatch.setattr(cli_module, "resolve_interaction_mode", lambda **kwargs: mode)


def _inspection(source: Path) -> AudiobookInspection:
    return AudiobookInspection(
        source=source,
        metadata={"title": "A title", "authors": ["An author"]},
        chapters=tuple(
            AudiobookChapter(
                number=number,
                source_id=f"chapter-{number}",
                title=f"Chapter {number}",
                href=f"chapter-{number}.xhtml",
                parent_id=None,
                level=0,
                char_count=12 * number,
                markdown=f"# Chapter {number}",
            )
            for number in range(1, 4)
        ),
    )


class _FakeConverter:
    def __init__(self, source: Path, project: ProjectRef) -> None:
        self.inspection = _inspection(source)
        self.project = project
        self.options = None
        self.existing_project: ProjectRef | None = None
        self.existing_chapters = (2, 3)
        self.setup: ProjectSetup | None = None
        self.calls: list[str] = []
        self.build_synthesis = None
        self.preflight_synthesis = None

    def inspect(self, source: Path) -> AudiobookInspection:
        self.calls.append("inspect")
        return self.inspection

    def find_project(self, options):  # type: ignore[no-untyped-def]
        self.calls.append("find_project")
        return self.existing_project

    def create_or_open_project(
        self, options, *, inspection, existing_project=None, project_checked=False
    ):  # type: ignore[no-untyped-def]
        self.calls.append("create_or_open_project")
        self.options = options
        if existing_project is None:
            numbers = tuple(
                index + 1
                for index in parse_chapter_selection(
                    options.chapters, len(self.inspection.chapters)
                )
            )
            created = True
        else:
            numbers = self.existing_chapters
            created = False
        self.setup = ProjectSetup(
            project=self.project,
            created=created,
            chapters=tuple(
                AudiobookProjectChapter(
                    number=number,
                    scope_id=f"chapter-{number:04d}",
                    title=f"Chapter {number}",
                    level=0,
                )
                for number in numbers
            ),
        )
        return self.setup

    def preflight(self, setup, inspection, options, *, synthesis):  # type: ignore[no-untyped-def]
        self.calls.append("preflight")
        self.preflight_synthesis = synthesis
        resolution = SynthesisResolution(
            engine=options.engine or "pykokoro",
            language=options.language or "en-us",
            voice=options.voice or "af_heart",
            model=options.model or "kokoro-v1",
            model_source=options.model_source or "github",
            quality=options.quality or "fp32",
            speed=options.speed or 1.0,
            unit="paragraph",
            pause_mode="sentence",
            voice_level=None,
        )
        return ConversionPreflight(
            source=options.source,
            title="A title",
            author="An author",
            project=self.project,
            project_created=setup.created,
            available_chapters=len(inspection.chapters),
            chapters=setup.chapters,
            output=options.output,
            format=options.format,
            synthesis_request=synthesis,
            synthesis=resolution,
            bitrate=options.bitrate,
            target_lufs=options.target_lufs,
            offline=options.offline,
            refresh=options.refresh,
        )

    def build_and_export(self, project, options, *, synthesis=None):  # type: ignore[no-untyped-def]
        self.calls.append("build_and_export")
        self.build_synthesis = synthesis
        return AudiobookExportResult(
            project=self.project,
            output_path=self.project.root.with_suffix(".m4b"),
            format="m4b",
            output_sha256="digest",
            export_id="export-1",
            chapter_count=len(self.setup.chapters) if self.setup else 0,
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
    convert_help = runner.invoke(cli_module.app, ["convert", "--help"]).output
    assert "--yes" in convert_help
    assert "--non-interactive" in convert_help
    assert "--model" in convert_help
    assert "--model-source" in convert_help
    assert "--quality" in convert_help


def test_list_and_info_use_the_public_inspection_result(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    listed = runner.invoke(cli_module.app, ["list", str(source)])
    described = runner.invoke(cli_module.app, ["info", str(source), "--json"])

    assert listed.exit_code == 0, listed.output
    assert "Chapter 1" in listed.output
    assert described.exit_code == 0, described.output
    assert json.loads(described.output)["metadata"]["title"] == "A title"


def test_convert_initializes_readio_project_and_keeps_json_stdout_clean(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=False, json_mode=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--chapters",
            "1",
            "--model",
            "kokoro-v1",
            "--model-source",
            "github",
            "--quality",
            "fp32",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["project"] == str(project.root)
    assert payload["created"] is True
    assert payload["selected_chapters"] == [1]
    assert payload["format"] == "m4b"
    assert payload["output"] == str(project.root.with_suffix(".m4b"))
    assert payload["result"]["chapter_count"] == 1
    assert payload["synthesis"]["model"] == "kokoro-v1"
    assert payload["synthesis"]["model_source"] == "github"
    assert payload["synthesis"]["quality"] == "fp32"
    assert converter.options.chapters == "1"
    assert converter.build_synthesis is converter.preflight_synthesis
    assert converter.calls == [
        "inspect",
        "find_project",
        "create_or_open_project",
        "preflight",
        "build_and_export",
    ]
    assert result.stderr == ""


def test_interactive_new_project_prompts_retries_and_preflights_before_build(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app, ["convert", str(source)], input="typo\n2-3\ny\n"
    )

    assert result.exit_code == 0, result.output
    assert "3 chapters detected" in result.output
    assert "Invalid chapter number: typo" in result.output
    assert result.output.count("Chapters to include") == 2
    assert "Create this audiobook?" in result.output
    assert "2-3" in result.output
    assert "Model" in result.output
    assert "kokoro-v1" in result.output
    assert converter.options.chapters == "2-3"
    assert converter.calls.index("preflight") < converter.calls.index(
        "build_and_export"
    )
    assert converter.build_synthesis is converter.preflight_synthesis


def test_interactive_explicit_chapters_skip_chapter_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" not in result.output
    assert "Create this audiobook?" in result.output
    assert converter.options.chapters == "1"


def test_yes_keeps_chapter_prompt_but_skips_final_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True, confirm=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app, ["convert", str(source), "--yes"], input="2\n"
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" in result.output
    assert "Create this audiobook?" not in result.output
    assert converter.options.chapters == "2"


def test_non_interactive_uses_all_without_prompting(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app, ["convert", str(source), "--non-interactive"]
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" not in result.output
    assert "Create this audiobook?" not in result.output
    assert converter.options.chapters == "all"
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (1, 2, 3)


def test_existing_project_shows_persisted_scope_without_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.existing_project = project
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(cli_module.app, ["convert", str(source)], input="y\n")

    assert result.exit_code == 0, result.output
    assert "2-3" in result.output
    assert "Chapters to include" not in result.output
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (2, 3)


def test_existing_project_rejects_conflicting_chapters(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.existing_project = project
    _set_mode(monkeypatch, interactive=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1"],
    )

    assert result.exit_code == 1
    assert "Existing project uses chapters 2-3" in result.output
    assert "--fresh" in result.output
    assert "preflight" not in converter.calls
    assert "build_and_export" not in converter.calls


def test_declining_confirmation_does_not_start_build(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1"],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert "Cancelled" in result.output
    assert "build_and_export" not in converter.calls


def test_status_and_preview_are_project_service_workflows(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    status = runner.invoke(cli_module.app, ["status", str(project.root), "--json"])
    preview = runner.invoke(cli_module.app, ["preview", str(source), "--json"])

    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["project"]["root"] == str(project.root)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["result"]["items"] == 1
