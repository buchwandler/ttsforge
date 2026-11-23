"""TTSForge-owned audiobook metadata overrides and validation."""

from __future__ import annotations

import json
import re
from dataclasses import fields, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import InputValidationError, OperationConflictError
from .models import (
    AudiobookMetadata,
    AudiobookMetadataView,
    AudiobookRequest,
    BookInspectionView,
    MetadataValidationReport,
    ProjectPaths,
    QcFinding,
)

if TYPE_CHECKING:
    from .service import AudiobookApplicationService

_METADATA_FILENAME = "audiobook-metadata.json"
_METADATA_FIELDS = {item.name for item in fields(AudiobookMetadata)}


def metadata_overrides_path(project: Path) -> Path:
    return project / _METADATA_FILENAME


def load_metadata_overrides(project: Path) -> AudiobookMetadata:
    path = metadata_overrides_path(project)
    if not path.exists():
        return AudiobookMetadata()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OperationConflictError(
            f"Invalid audiobook metadata file: {path}."
        ) from exc
    if not isinstance(raw, dict) or set(raw) - _METADATA_FIELDS:
        raise OperationConflictError(f"Invalid audiobook metadata fields in {path}.")
    values: dict[str, object] = {}
    for name, value in raw.items():
        if value is None:
            continue
        if name == "cover" and isinstance(value, str) and value.strip():
            values[name] = Path(value)
        elif isinstance(value, str) and value.strip():
            values[name] = value.strip()
        else:
            raise OperationConflictError(
                f"Invalid value for audiobook metadata field {name!r} in {path}."
            )
    return AudiobookMetadata(**values)


def save_metadata_overrides(project: Path, metadata: AudiobookMetadata) -> None:
    project.mkdir(parents=True, exist_ok=True)
    path = metadata_overrides_path(project)
    values = {
        item.name: str(value) if isinstance(value, Path) else value
        for item in fields(metadata)
        if (value := getattr(metadata, item.name)) is not None
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def apply_project_metadata(
    request: AudiobookRequest, project: Path
) -> AudiobookRequest:
    metadata = request.metadata.overlay(load_metadata_overrides(project))
    if metadata.narrator is None:
        metadata = metadata.overlay(AudiobookMetadata(narrator=request.voice))
    return replace(
        request,
        metadata=metadata,
        title=metadata.title,
        author=metadata.author,
        cover=metadata.cover,
        language=metadata.language or request.language,
    )


def inspected_metadata(inspection: BookInspectionView) -> AudiobookMetadata:
    legacy = AudiobookMetadata(
        title=inspection.title,
        author=inspection.author,
        language=inspection.language,
        cover=inspection.cover,
    )
    return inspection.metadata.overlay(legacy)


class MetadataApplicationService:
    """Manage project metadata without taking ownership of Readio workflow state."""

    def __init__(self, audiobook: AudiobookApplicationService) -> None:
        self._audiobook = audiobook

    def show(self, paths: ProjectPaths) -> AudiobookMetadataView:
        saved = self._audiobook.load_saved_setup(paths)
        if saved is None:
            raise OperationConflictError(
                f"No saved TTSForge setup exists in {paths.root}."
            )
        inspection = self._audiobook.inspect_book(saved.source)
        source_metadata = inspected_metadata(inspection)
        overrides = load_metadata_overrides(paths.root)
        effective = source_metadata.overlay(saved.metadata).overlay(overrides)
        if effective.narrator is None:
            effective = effective.overlay(AudiobookMetadata(narrator=saved.voice))
        return AudiobookMetadataView(
            project=paths.root,
            source=saved.source,
            source_metadata=source_metadata,
            overrides=overrides,
            effective=effective,
        )

    def set(
        self, paths: ProjectPaths, values: dict[str, str | Path]
    ) -> AudiobookMetadataView:
        if not values:
            raise InputValidationError("Provide at least one audiobook metadata field.")
        if self._audiobook.load_saved_setup(paths) is None:
            raise OperationConflictError(
                f"No saved TTSForge setup exists in {paths.root}."
            )
        updates = _metadata_update(values)
        existing = load_metadata_overrides(paths.root)
        save_metadata_overrides(paths.root, existing.overlay(updates))
        return self.show(paths)

    def validate(self, paths: ProjectPaths) -> MetadataValidationReport:
        view = self.show(paths)
        findings = list(validate_metadata(view.effective))
        return MetadataValidationReport(
            project=paths.root,
            valid=not any(finding.severity == "error" for finding in findings),
            findings=tuple(findings),
        )


def validate_metadata(metadata: AudiobookMetadata) -> tuple[QcFinding, ...]:
    findings: list[QcFinding] = []
    for name in ("title", "author"):
        if getattr(metadata, name) is None:
            findings.append(
                QcFinding(
                    id=f"metadata.{name}_missing",
                    severity="warning",
                    section="metadata",
                    message=f"Audiobook {name} is not set.",
                )
            )
    if metadata.cover is None:
        findings.append(
            QcFinding(
                id="metadata.cover_missing",
                severity="warning",
                section="metadata",
                message="Audiobook cover is not set.",
            )
        )
    elif not metadata.cover.is_file():
        findings.append(
            QcFinding(
                id="metadata.cover_unreadable",
                severity="warning",
                section="metadata",
                message="Configured audiobook cover is not a readable file.",
                details={"path": str(metadata.cover)},
            )
        )
    if metadata.year is not None and re.fullmatch(r"\d{4}", metadata.year) is None:
        findings.append(
            QcFinding(
                id="metadata.year_invalid",
                severity="error",
                section="metadata",
                message="Audiobook year must contain four digits.",
                details={"year": metadata.year},
            )
        )
    return tuple(findings)


def _metadata_update(values: dict[str, str | Path]) -> AudiobookMetadata:
    unknown = sorted(set(values) - _METADATA_FIELDS)
    if unknown:
        raise InputValidationError("Unknown audiobook metadata: " + ", ".join(unknown))
    normalized: dict[str, object] = {}
    for name, value in values.items():
        if isinstance(value, Path):
            normalized[name] = value.expanduser().resolve()
        elif isinstance(value, str) and value.strip():
            normalized[name] = value.strip()
        else:
            raise InputValidationError(f"Audiobook metadata {name!r} cannot be empty.")
    metadata = AudiobookMetadata(**normalized)
    if metadata.year is not None and re.fullmatch(r"\d{4}", metadata.year) is None:
        raise InputValidationError("Audiobook year must contain four digits.")
    return metadata
