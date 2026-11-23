from __future__ import annotations

from pathlib import Path

from ttsforge.application.models import (
    AudiobookMetadata,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    NarrationView,
    ProjectPaths,
    WorkflowBlockerView,
    WorkflowPlanView,
    WorkflowStepView,
)
from ttsforge.application.qc import QcApplicationService


class _Audiobook:
    def __init__(
        self,
        request: AudiobookRequest,
        inspection: BookInspectionView,
        workflow: WorkflowPlanView,
    ) -> None:
        self.request = request
        self.inspection = inspection
        self.workflow = workflow

    def load_saved_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        return self.request

    def inspect_book(self, source: Path) -> BookInspectionView:
        return self.inspection

    def list_variants(
        self, paths: ProjectPaths, *, source: Path | None = None
    ) -> tuple[object, ...]:
        return ()

    def status(self, paths: ProjectPaths) -> WorkflowPlanView:
        return self.workflow


class _Narrations:
    def __init__(
        self,
        request: AudiobookRequest,
        items: tuple[NarrationView, ...] | None = None,
    ) -> None:
        self.request = request
        self.items = items or (
            NarrationView(
                id="primary",
                display_name="Primary narration",
                primary=True,
                output=request.output,
                engine=request.engine,
                target=request.target,
                voice=request.voice,
            ),
        )

    def list(
        self, paths: ProjectPaths, *, source: Path | None = None
    ) -> tuple[NarrationView, ...]:
        return self.items

    def request_for_render(
        self, paths: ProjectPaths, narration_id: str
    ) -> tuple[AudiobookRequest, object]:
        return self.request, object()


def _service(tmp_path: Path, *, selection: str = "all", output_exists: bool = True):
    source = tmp_path / "book.epub"
    source.touch()
    project = tmp_path / "book.ttsforge"
    project.mkdir()
    output = tmp_path / "book.m4b"
    if output_exists:
        output.write_bytes(b"audio")
    request = AudiobookRequest(
        source=source,
        project=project,
        chapters=selection,
        output=output,
        engine="engine",
        target="target",
        voice="voice",
        metadata=AudiobookMetadata(title="Book", author="Writer", language="en-US"),
    )
    inspection = BookInspectionView(
        source=source,
        kind="book",
        title="Book",
        author="Writer",
        language="en-US",
        chapters=(BookChapterView(1, "Opening", "c1", 100),),
    )
    workflow = WorkflowPlanView(
        source=source,
        workspace=project,
        workspace_mode="project",
        output=output,
        steps=(
            WorkflowStepView(
                stage="export",
                package="audioexport",
                action="reuse",
                selector=None,
                reason="Output is reusable",
                state="complete",
            ),
        ),
    )
    audiobook = _Audiobook(request, inspection, workflow)
    narrations = _Narrations(request)
    return QcApplicationService(audiobook, narrations), ProjectPaths.for_root(project)


def test_qc_reports_safe_pass_with_missing_metadata_warnings(tmp_path: Path) -> None:
    service, paths = _service(tmp_path)

    report = service.check(paths)

    assert report.passed
    assert "metadata.cover_missing" in {item.id for item in report.findings}
    deep = next(
        item for item in report.findings if item.id == "media.deep_qc_unavailable"
    )
    assert deep.severity == "unknown"


def test_qc_reports_invalid_chapter_selection_and_missing_output(
    tmp_path: Path,
) -> None:
    service, paths = _service(tmp_path, selection="2", output_exists=False)

    report = service.check(paths)

    assert not report.passed
    assert {item.id for item in report.findings} >= {
        "chapter.selection_invalid",
        "output.missing",
    }


def test_qc_surfaces_readio_blocker_reason_codes(tmp_path: Path) -> None:
    service, paths = _service(tmp_path)
    audiobook = service._audiobook
    audiobook.workflow = WorkflowPlanView(
        source=audiobook.request.source,
        workspace=paths.root,
        workspace_mode="project",
        output=audiobook.request.output,
        executable=False,
        steps=(
            WorkflowStepView(
                stage="export",
                package="audioexport",
                action="blocked",
                selector=None,
                reason="Missing exporter",
                state="blocked",
                reason_code="audioexport_unavailable",
                blockers=(
                    WorkflowBlockerView(
                        code="audioexport_unavailable",
                        message="Install AudioExport.",
                        owner="readio",
                        recoverable=True,
                        suggested_action="install_audioexport",
                    ),
                ),
            ),
        ),
    )

    report = service.check(paths)

    finding = next(item for item in report.findings if item.id == "workflow.blocked")
    assert not report.passed
    assert finding.details == {
        "narration_id": "primary",
        "blockers": [{"stage": "export", "reason_code": "audioexport_unavailable"}],
    }


def test_qc_reports_incomplete_narration_setup(tmp_path: Path) -> None:
    service, paths = _service(tmp_path)
    service._narrations.items += (
        NarrationView(
            id="broken",
            display_name="Broken",
            primary=False,
            error="Missing profile",
        ),
    )

    report = service.check(paths)

    assert not report.passed
    finding = next(
        item for item in report.findings if item.id == "project.narration_invalid"
    )
    assert finding.details["narration_id"] == "broken"
