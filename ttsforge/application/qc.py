"""Aggregate safe audiobook checks without duplicating Readio workflow validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..chapter_selection import parse_chapter_selection
from .errors import ApplicationError
from .metadata import MetadataApplicationService, validate_metadata
from .models import (
    AudiobookQcReport,
    BookInspectionView,
    ProjectPaths,
    QcFinding,
    QcSeverity,
)

if TYPE_CHECKING:
    from .narrations import NarrationApplicationService
    from .service import AudiobookApplicationService


class QcApplicationService:
    """Collect source, project, workflow, metadata, and output findings."""

    def __init__(
        self,
        audiobook: AudiobookApplicationService,
        narrations: NarrationApplicationService,
    ) -> None:
        self._audiobook = audiobook
        self._narrations = narrations
        self._metadata = MetadataApplicationService(audiobook)

    def check(
        self, paths: ProjectPaths, narration_id: str | None = None
    ) -> AudiobookQcReport:
        findings: list[QcFinding] = []
        try:
            primary = self._audiobook.load_saved_setup(paths)
        except (ApplicationError, OSError, ValueError) as exc:
            findings.append(
                _finding(
                    "project.primary_invalid",
                    "error",
                    "project",
                    "Primary narration setup cannot be loaded.",
                    error=str(exc),
                )
            )
            return self._report(paths, narration_id, findings)
        if primary is None:
            findings.append(
                _finding(
                    "project.primary_missing",
                    "error",
                    "project",
                    "No primary narration setup is saved.",
                )
            )
            return self._report(paths, narration_id, findings)

        source = primary.source
        if not source.is_file() or not os.access(source, os.R_OK):
            findings.append(
                _finding(
                    "source.unreadable",
                    "error",
                    "source",
                    "Audiobook source is missing or unreadable.",
                    path=str(source),
                )
            )
            return self._report(paths, narration_id, findings)
        try:
            inspection = self._audiobook.inspect_book(source)
        except (ApplicationError, OSError, ValueError) as exc:
            findings.append(
                _finding(
                    "source.inspection_failed",
                    "error",
                    "source",
                    "Audiobook source inspection failed.",
                    error=str(exc),
                )
            )
            return self._report(paths, narration_id, findings)
        findings.extend(_source_findings(inspection))
        try:
            metadata_view = self._metadata.show(paths)
        except (ApplicationError, OSError, ValueError) as exc:
            findings.append(
                _finding(
                    "metadata.invalid",
                    "error",
                    "metadata",
                    "Project audiobook metadata cannot be loaded.",
                    error=str(exc),
                )
            )
        else:
            findings.extend(validate_metadata(metadata_view.effective))

        try:
            all_narrations = self._narrations.list(paths, source=source)
        except (ApplicationError, OSError, ValueError) as exc:
            findings.append(
                _finding(
                    "project.narrations_invalid",
                    "error",
                    "project",
                    "Narration setups cannot be listed.",
                    error=str(exc),
                )
            )
            return self._report(paths, narration_id, findings)
        invalid = [
            item
            for item in all_narrations
            if item.error and (narration_id is None or item.id == narration_id)
        ]
        for item in invalid:
            findings.append(
                _finding(
                    "project.narration_invalid",
                    "error",
                    "project",
                    f"Narration {item.id!r} has an invalid setup.",
                    narration_id=item.id,
                    error=item.error,
                )
            )
        if narration_id is None:
            selected_narrations = tuple(
                item for item in all_narrations if not item.error
            )
        else:
            selected_narrations = tuple(
                item
                for item in all_narrations
                if item.id == narration_id and not item.error
            )
            if not selected_narrations and not any(
                item.id == narration_id for item in invalid
            ):
                findings.append(
                    _finding(
                        "project.narration_not_found",
                        "error",
                        "project",
                        f"Narration {narration_id!r} does not exist or is invalid.",
                        narration_id=narration_id,
                    )
                )

        for item in selected_narrations:
            try:
                request, _ = self._narrations.request_for_render(paths, item.id)
            except (ApplicationError, OSError, ValueError) as exc:
                findings.append(
                    _finding(
                        "project.narration_invalid",
                        "error",
                        "project",
                        f"Narration {item.id!r} cannot be loaded.",
                        narration_id=item.id,
                        error=str(exc),
                    )
                )
                continue
            if request.source.resolve() != source.resolve():
                findings.append(
                    _finding(
                        "project.source_mismatch",
                        "error",
                        "project",
                        f"Narration {item.id!r} refers to a different source.",
                        narration_id=item.id,
                        path=str(request.source),
                    )
                )
            _chapter_findings(request.chapters, inspection, item.id, findings)
            _output_findings(request.output, paths.root, item.id, findings)
            setup_paths = (
                paths if item.primary else ProjectPaths.for_variant(paths.root, item.id)
            )
            try:
                workflow = self._audiobook.status(setup_paths)
            except (ApplicationError, OSError, ValueError) as exc:
                findings.append(
                    _finding(
                        "workflow.inspection_failed",
                        "error",
                        "workflow",
                        f"Narration {item.id!r} workflow cannot be inspected.",
                        narration_id=item.id,
                        error=str(exc),
                    )
                )
                continue
            if not workflow.executable:
                blockers = [
                    {"stage": step.stage, "reason_code": step.reason_code}
                    for step in workflow.steps
                    if step.action == "blocked"
                ]
                findings.append(
                    _finding(
                        "workflow.blocked",
                        "error",
                        "workflow",
                        f"Narration {item.id!r} workflow is blocked.",
                        narration_id=item.id,
                        blockers=blockers,
                    )
                )
            rebuild = [
                step.stage
                for step in workflow.steps
                if step.force or step.action in {"run", "rebuild"}
            ]
            if rebuild:
                findings.append(
                    _finding(
                        "workflow.rebuild_required",
                        "warning",
                        "workflow",
                        f"Narration {item.id!r} workflow has stages to execute.",
                        narration_id=item.id,
                        stages=rebuild,
                    )
                )
            for step in workflow.steps:
                for blocker in step.blockers:
                    if workflow.executable:
                        findings.append(
                            _finding(
                                "workflow.blocker_reported",
                                "warning",
                                "workflow",
                                blocker.message,
                                narration_id=item.id,
                                stage=step.stage,
                                reason_code=blocker.code,
                            )
                        )

        findings.append(
            _finding(
                "media.deep_qc_unavailable",
                "unknown",
                "output",
                (
                    "Embedded M4B metadata, chapter markers, and audio quality are "
                    "not inspected without an authoritative Readio result."
                ),
            )
        )
        return self._report(paths, narration_id, findings)

    @staticmethod
    def _report(
        paths: ProjectPaths, narration_id: str | None, findings: list[QcFinding]
    ) -> AudiobookQcReport:
        return AudiobookQcReport(
            project=paths.root,
            narration_id=narration_id,
            passed=not any(finding.severity == "error" for finding in findings),
            findings=tuple(findings),
        )


def _source_findings(inspection: BookInspectionView) -> tuple[QcFinding, ...]:
    findings: list[QcFinding] = []
    if inspection.kind != "book":
        findings.append(
            _finding(
                "source.not_book",
                "error",
                "source",
                "Source kind is not a book.",
                kind=inspection.kind,
            )
        )
    for name, value in (
        ("title", inspection.title),
        ("author", inspection.author),
        ("language", inspection.language),
    ):
        if value is None:
            findings.append(
                _finding(
                    f"source.{name}_missing",
                    "warning",
                    "source",
                    f"Source {name} metadata is not available.",
                )
            )
    if not inspection.chapters:
        findings.append(
            _finding(
                "source.chapters_missing",
                "error",
                "source",
                "No chapters were discovered in the source book.",
            )
        )
    return tuple(findings)


def _chapter_findings(
    selection: str | None,
    inspection: BookInspectionView,
    narration_id: str,
    findings: list[QcFinding],
) -> None:
    try:
        indices = parse_chapter_selection(selection or "all", len(inspection.chapters))
    except ValueError as exc:
        findings.append(
            _finding(
                "chapter.selection_invalid",
                "error",
                "source",
                f"Narration {narration_id!r} has an invalid chapter selection.",
                narration_id=narration_id,
                selection=selection,
                error=str(exc),
            )
        )
        return
    for index in indices:
        chapter = inspection.chapters[index]
        if chapter.char_count == 0:
            findings.append(
                _finding(
                    "chapter.empty",
                    "error",
                    "source",
                    f"Selected chapter {chapter.number} has no source text.",
                    narration_id=narration_id,
                    chapter=chapter.number,
                )
            )


def _output_findings(
    output: Path | None,
    project: Path,
    narration_id: str,
    findings: list[QcFinding],
) -> None:
    if output is None:
        findings.append(
            _finding(
                "output.path_missing",
                "error",
                "output",
                f"Narration {narration_id!r} has no output path configured.",
                narration_id=narration_id,
            )
        )
        return
    if output.suffix.casefold() != ".m4b":
        findings.append(
            _finding(
                "output.extension_invalid",
                "error",
                "output",
                f"Narration {narration_id!r} output must use the .m4b extension.",
                narration_id=narration_id,
                path=str(output),
            )
        )
    if output.resolve().is_relative_to(project.resolve()):
        findings.append(
            _finding(
                "output.inside_project",
                "error",
                "output",
                f"Narration {narration_id!r} output is inside the project workspace.",
                narration_id=narration_id,
                path=str(output),
            )
        )
    if not output.is_file():
        findings.append(
            _finding(
                "output.missing",
                "error",
                "output",
                f"Narration {narration_id!r} output file does not exist.",
                narration_id=narration_id,
                path=str(output),
            )
        )
    elif output.stat().st_size == 0:
        findings.append(
            _finding(
                "output.empty",
                "error",
                "output",
                f"Narration {narration_id!r} output file is empty.",
                narration_id=narration_id,
                path=str(output),
            )
        )


def _finding(
    identifier: str,
    severity: QcSeverity,
    section: str,
    message: str,
    **details: object,
) -> QcFinding:
    return QcFinding(
        id=identifier,
        severity=severity,
        section=section,
        message=message,
        details=details,
    )
