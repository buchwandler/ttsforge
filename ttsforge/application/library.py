"""TTSForge audiobook project discovery and summaries."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..chapter_selection import parse_chapter_selection
from .errors import ApplicationError, InputValidationError
from .metadata import MetadataApplicationService
from .models import NarrationView, ProjectPaths
from .narrations import NarrationApplicationService
from .qc import QcApplicationService
from .service import AudiobookApplicationService


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project_id: str
    title: str | None
    author: str | None
    source: Path | None
    project: Path
    chapter_count: int
    selected_chapter_count: int
    narrations: tuple[NarrationView, ...]
    primary_narration_id: str | None
    outputs: tuple[Path, ...]
    qc_state: str | None
    active_job_id: str | None
    last_activity: datetime | None
    error: str | None


class LibraryApplicationService:
    """Discover project directories and inspect them through TTSForge services."""

    def __init__(
        self,
        audiobook: AudiobookApplicationService,
        narrations: NarrationApplicationService,
    ) -> None:
        self._audiobook = audiobook
        self._narrations = narrations
        self._metadata = MetadataApplicationService(audiobook)
        self._qc = QcApplicationService(audiobook, narrations)

    def list(self, root: Path) -> tuple[ProjectSummary, ...]:
        root = root.expanduser()
        if not root.is_dir():
            raise InputValidationError(f"Library root must be a directory: {root}.")
        return tuple(
            self.inspect(project) for project in _project_candidates(root.resolve())
        )

    def get(self, project_id: str) -> ProjectSummary:
        try:
            padding = "=" * (-len(project_id) % 4)
            decoded = base64.b64decode(
                project_id + padding, altchars=b"-_", validate=True
            )
            project = Path(os.fsdecode(decoded))
        except (ValueError, OSError) as exc:
            raise InputValidationError("Invalid library project ID.") from exc
        if not project.is_absolute():
            raise InputValidationError("Invalid library project ID.")
        return self.inspect(project)

    def inspect(self, project: Path) -> ProjectSummary:
        project = project.expanduser().resolve()
        paths = ProjectPaths.for_root(project)
        errors: list[str] = []
        saved = None
        if not project.is_dir():
            errors.append(f"Project directory does not exist: {project}.")
        else:
            try:
                saved = self._audiobook.load_saved_setup(paths)
            except (ApplicationError, OSError, ValueError) as exc:
                errors.append(str(exc))
        if saved is None and not errors:
            errors.append("No primary TTSForge narration setup exists.")

        source = saved.source if saved is not None else None
        inspection = None
        chapter_count = 0
        selected_chapter_count = 0
        title = None
        author = None
        narrations: tuple[NarrationView, ...] = ()
        primary_narration_id = None
        outputs: tuple[Path, ...] = ()
        qc_state = None

        if saved is not None:
            if source is None or not source.is_file() or not os.access(source, os.R_OK):
                errors.append(f"Audiobook source is missing or unreadable: {source}.")
            else:
                try:
                    inspection = self._audiobook.inspect_book(source)
                except (ApplicationError, OSError, ValueError) as exc:
                    errors.append(f"Audiobook source inspection failed: {exc}")
                else:
                    chapter_count = len(inspection.chapters)
                    title = inspection.title
                    author = inspection.author
                    try:
                        selected_chapter_count = len(
                            parse_chapter_selection(
                                saved.chapters or "all", chapter_count
                            )
                        )
                    except ValueError as exc:
                        errors.append(f"Invalid saved chapter selection: {exc}")

            try:
                metadata = self._metadata.show(paths)
            except (ApplicationError, OSError, ValueError) as exc:
                errors.append(f"Audiobook metadata cannot be loaded: {exc}")
            else:
                title = metadata.effective.title
                author = metadata.effective.author

            try:
                narrations = self._narrations.list(paths, source=source)
            except (ApplicationError, OSError, ValueError) as exc:
                errors.append(f"Narrations cannot be listed: {exc}")
            else:
                primary_narration_id = next(
                    (item.id for item in narrations if item.primary), None
                )
                outputs = tuple(
                    item.output for item in narrations if item.output is not None
                )
                errors.extend(
                    f"Narration {item.id}: {item.error}"
                    for item in narrations
                    if item.error
                )

            try:
                report = self._qc.check(paths)
            except (ApplicationError, OSError, ValueError) as exc:
                errors.append(f"Audiobook QC could not be completed: {exc}")
                qc_state = "unknown"
            else:
                severities = {finding.severity for finding in report.findings}
                qc_state = (
                    "issues"
                    if "error" in severities
                    else "unknown"
                    if "unknown" in severities
                    else "passed"
                )

        return ProjectSummary(
            project_id=_project_id(project),
            title=title,
            author=author,
            source=source,
            project=project,
            chapter_count=chapter_count,
            selected_chapter_count=selected_chapter_count,
            narrations=narrations,
            primary_narration_id=primary_narration_id,
            outputs=outputs,
            qc_state=qc_state,
            active_job_id=None,
            last_activity=_last_activity(paths),
            error="; ".join(dict.fromkeys(errors)) or None,
        )


def _project_id(project: Path) -> str:
    encoded = base64.urlsafe_b64encode(os.fsencode(project)).decode("ascii")
    return encoded.rstrip("=")


def _project_candidates(root: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    excluded = {".git", ".ledger", ".venv", ".tox", "__pycache__", "node_modules"}
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        path = Path(directory)
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name not in excluded and not (path / name).is_symlink()
        )
        if not _is_project_candidate(path, filenames, subdirectories):
            continue
        candidates.append(path)
        subdirectories.clear()
    return tuple(sorted(candidates, key=lambda item: str(item).casefold()))


def _is_project_candidate(
    project: Path, filenames: list[str], subdirectories: list[str]
) -> bool:
    if project.name.endswith((".ttsforge", ".ssmdbook", ".readio")):
        return True
    if {
        "render.readio.toml",
        "narrator.renderprofile.toml",
        "audiobook-metadata.json",
        "project.toml",
        "readio.toml",
    }.intersection(filenames):
        return True
    variants = project / "variants"
    if "variants" not in subdirectories:
        return False
    try:
        return next(variants.iterdir(), None) is not None
    except OSError:
        return True


def _last_activity(paths: ProjectPaths) -> datetime | None:
    files = [
        paths.intent,
        paths.profile,
        paths.root / "audiobook-metadata.json",
    ]
    variants = paths.root / "variants"
    try:
        files.extend(
            path
            for directory in variants.iterdir()
            if directory.is_dir() and not directory.is_symlink()
            for path in (
                directory / "render.readio.toml",
                directory / "narrator.renderprofile.toml",
                directory / "narration.json",
            )
        )
    except OSError:
        pass
    timestamps: list[float] = []
    for path in files:
        try:
            timestamps.append(path.stat().st_mtime)
        except OSError:
            continue
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps), timezone.utc)
