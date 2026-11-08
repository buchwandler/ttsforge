from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from readio.api import WorkflowStageError
from typer.testing import CliRunner

from ttsforge.application.models import (
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ConversionResultView,
    ProjectPaths,
    WorkflowPlanView,
)
from ttsforge.application.service import AudiobookApplicationService
from ttsforge.cli import app
from ttsforge.cli.interaction import InteractionMode

cli_app = import_module("ttsforge.cli.app")


class _Backend:
    def __init__(self) -> None:
        self.saved: dict[Path, AudiobookRequest] = {}
        self.calls: list[tuple[object, ...]] = []
        self.render_error: Exception | None = None
        self.render_request: tuple[ProjectPaths, AudiobookRequest] | None = None

    def inspect_source(self, source: Path) -> BookInspectionView:
        self.calls.append(("source", source))
        return BookInspectionView(
            source=source.resolve(),
            kind="book",
            title="Book title",
            author="Writer",
            language="en-US",
            chapters=(BookChapterView(1, "Opening", "c1", 100),),
        )

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        self.calls.append(("load", paths.root))
        return self.saved[paths.root]

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None:
        self.calls.append(("save", paths.root, request))
        paths.intent.touch()
        paths.profile.touch()
        self.saved[paths.root] = request

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object:
        self.calls.append(("request", paths.root, request))
        self.render_request = (paths, request)
        return paths, request

    def inspect(self, request: object) -> WorkflowPlanView:
        self.calls.append(("inspect", request))
        paths, selected = request  # type: ignore[misc]
        return WorkflowPlanView(
            source=selected.source,
            workspace=paths.bundle,
            workspace_mode="bundle",
            output=selected.output,
            steps=(),
        )

    def render(self, request: object, *, on_progress=None) -> ConversionResultView:
        self.calls.append(("render", request))
        if self.render_error is not None:
            raise self.render_error
        paths, selected = request  # type: ignore[misc]
        assert selected.output is not None
        return ConversionResultView(
            output=selected.output,
            workspace=paths.bundle,
            workspace_mode="bundle",
            executed_stages=("render", "compose", "export"),
            reused_stages=("convert", "compile"),
        )

    def list_engines(self) -> tuple[object, ...]:
        self.calls.append(("engines",))
        return ({"id": "engine-a", "name": "Engine A"},)

    def list_targets(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append(("targets", kwargs))
        return ({"id": "target-a", "engine": "engine-a", "language": "en-US"},)

    def list_voices(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append(("voices", kwargs))
        return ({"id": "voice-a", "engine": "engine-a", "language": "en-US"},)


def _invoke(monkeypatch, backend: _Backend, args: list[str]):
    service = AudiobookApplicationService(backend)
    mode = InteractionMode(
        interactive=False,
        json=True,
        live_progress=False,
        confirm=False,
    )
    monkeypatch.setattr(cli_app, "_service", lambda: (backend, service))
    monkeypatch.setattr(cli_app, "resolve_interaction_mode", lambda **kwargs: mode)
    return CliRunner().invoke(app, args)


def test_convert_persists_setup_before_preflight_and_uses_m4b(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--replace-output",
            "--rebuild-from",
            "render",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["result"]["output"] == str(tmp_path / "book.m4b")
    assert payload["request"]["replace_output"] is True
    assert payload["request"]["rebuild_from"] == "render"
    assert [call[0] for call in backend.calls[-4:]] == [
        "save",
        "request",
        "inspect",
        "render",
    ]


def test_output_replacement_and_stage_rebuild_are_separate_controls(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--replace-output",
            "--rebuild-from",
            "render",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert backend.render_request is not None
    request = backend.render_request[1]
    assert request.replace_output is True
    assert request.rebuild_from == "render"


def test_discovery_commands_return_normalized_json(monkeypatch) -> None:
    backend = _Backend()

    targets_result = _invoke(
        monkeypatch,
        backend,
        ["targets", "--engine", "engine-a", "--language", "en-US", "--json"],
    )
    voices_result = _invoke(
        monkeypatch,
        backend,
        ["voices", "--engine", "engine-a", "--target", "target-a", "--json"],
    )

    assert targets_result.exit_code == 0, targets_result.output
    assert json.loads(targets_result.output)[0]["id"] == "target-a"
    assert voices_result.exit_code == 0, voices_result.output
    assert json.loads(voices_result.output)[0]["id"] == "voice-a"


def test_list_and_info_use_source_inspection_without_creating_a_project(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    listed = _invoke(monkeypatch, backend, ["list", str(source), "--json"])
    info = _invoke(monkeypatch, backend, ["info", str(source), "--json"])

    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["chapters"][0]["title"] == "Opening"
    assert info.exit_code == 0, info.output
    payload = json.loads(info.output)
    assert payload["title"] == "Book title"
    assert payload["project"] == str(tmp_path / "book.ttsforge")
    assert payload["saved_setup"] is None
    assert not (tmp_path / "book.ttsforge").exists()


def test_legacy_project_is_rejected_without_mutation(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    legacy = tmp_path / "old.ssmdbook"
    legacy.mkdir()
    marker = legacy / "project.toml"
    marker.write_text("old state", encoding="utf-8")
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--project",
            str(legacy),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "TTSForge/Readio 0.4 project" in result.output
    assert marker.read_text(encoding="utf-8") == "old state"
    assert backend.calls == []


def test_engines_lists_public_discovery_results_as_json(monkeypatch) -> None:
    backend = _Backend()

    result = _invoke(monkeypatch, backend, ["engines", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["id"] == "engine-a"


def test_status_uses_saved_setup_and_readonly_workflow_inspection(
    monkeypatch, tmp_path: Path
) -> None:
    backend = _Backend()
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved[paths.root] = AudiobookRequest(
        source=tmp_path / "book.epub",
        language="en-US",
        engine="engine-a",
        target="target-a",
        output=tmp_path / "book.m4b",
    )

    result = _invoke(
        monkeypatch,
        backend,
        ["status", "--project", str(paths.root), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["source"] == str(tmp_path / "book.epub")
    assert [call[0] for call in backend.calls] == [
        "load",
        "request",
        "inspect",
    ]


def test_unknown_rebuild_stage_is_rejected_before_setup(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        ["convert", str(source), "--rebuild-from", "unknown", "--json"],
    )

    assert result.exit_code == 2
    assert "Choose --rebuild-from" in result.output
    assert backend.calls == []


def test_cli_displays_structured_readio_stage_errors(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()
    backend.render_error = WorkflowStageError(
        "render",
        "The engine runtime is unavailable.",
        package="voicerender",
        selector="chapter-2",
        code="engine_unavailable",
        cause=RuntimeError("missing runtime"),
        details={"retryable": True},
    )

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "Error (render-stage failure)" in result.output
    assert "Stage: render" in result.output
    assert "Package: voicerender" in result.output
    assert "Selector: chapter-2" in result.output
    assert "Code: engine_unavailable" in result.output
