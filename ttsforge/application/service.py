"""UI-independent audiobook setup, persistence, preflight, and render orchestration."""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from ..chapter_selection import normalize_chapter_selection
from .errors import (
    BlockedWorkflowError,
    InputValidationError,
    LegacyWorkspaceError,
    OperationConflictError,
    ProjectScopeConflictError,
)
from .events import ApplicationEvent
from .models import (
    AudiobookRequest,
    BookInspectionView,
    ConversionResultView,
    InputOverrides,
    PreflightView,
    ProjectPaths,
    ResolvedSetup,
    SetupOrigins,
    SetupPreparation,
    WorkflowPlanView,
    WorkflowStepView,
)
from .setup import merge_saved_setup


class ApplicationBackend(Protocol):
    def inspect_source(self, source: Path) -> BookInspectionView: ...

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest: ...

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None: ...

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object: ...

    def inspect(self, request: object) -> WorkflowPlanView: ...

    def render(
        self,
        request: object,
        *,
        on_progress: Callable[[ApplicationEvent], None] | None = None,
    ) -> ConversionResultView: ...


_REBUILD_ORDER = ("convert", "compile", "render_plan", "render", "compose", "export")


def _rebuild_for_setup_change(
    request: AudiobookRequest, saved: AudiobookRequest
) -> AudiobookRequest:
    required = None
    if (
        request.language != saved.language
        or request.spacy != saved.spacy
        or request.speech_profile != saved.speech_profile
    ):
        required = "convert"
    elif (request.pause_timing or "fixed") != (saved.pause_timing or "fixed"):
        required = "render_plan"
    if required is None:
        return request

    current = request.rebuild_from
    if current is None or _REBUILD_ORDER.index(required) < _REBUILD_ORDER.index(
        current
    ):
        return replace(request, rebuild_from=required)
    return request


def blocked_workflow_steps(plan: WorkflowPlanView) -> tuple[WorkflowStepView, ...]:
    """Return Readio workflow stages explicitly marked as blocked."""
    return tuple(step for step in plan.steps if step.action == "blocked")


def require_runnable_workflow(plan: WorkflowPlanView) -> None:
    """Raise an application error when Readio's workflow plan is blocked."""
    blocked = blocked_workflow_steps(plan)
    if blocked:
        raise BlockedWorkflowError(blocked)


class AudiobookApplicationService:
    """Coordinate saved audiobook setup and delegate workflow decisions to Readio."""

    def __init__(self, backend: ApplicationBackend) -> None:
        self._backend = backend

    def inspect_book(self, source: Path) -> BookInspectionView:
        return self._backend.inspect_source(source)

    def prepare_setup(
        self,
        request: AudiobookRequest,
        overrides: InputOverrides,
        *,
        interactive: bool = True,
    ) -> SetupPreparation:
        paths = ProjectPaths.for_source(request.source, request.project)
        if request.source.name.endswith((".ssmdbook", ".readio")):
            raise LegacyWorkspaceError(
                self._legacy_workspace_message(request.source, source=None)
            )
        if request.fresh:
            root = paths.root
            if self._is_legacy_workspace(root):
                root = ProjectPaths.for_source(request.source).root
            paths = ProjectPaths.for_root(self._fresh_root(root))
        else:
            self._reject_legacy_workspace(paths.root, request.source)
        inspection = self.inspect_book(request.source)
        if not inspection.chapters:
            raise InputValidationError(
                "No chapters were discovered in the source book."
            )
        if request.chapters is not None:
            try:
                request = replace(
                    request,
                    chapters=normalize_chapter_selection(
                        request.chapters, len(inspection.chapters)
                    ),
                )
            except ValueError as exc:
                raise InputValidationError(str(exc)) from exc

        has_intent = paths.intent.is_file()
        has_profile = paths.profile.is_file()
        if has_intent != has_profile:
            raise OperationConflictError(
                "Incomplete TTSForge setup in "
                f"{paths.root}: intent and profile must both exist."
            )
        saved: AudiobookRequest | None = None
        if has_intent:
            saved = self._backend.load_setup(paths)
            if saved.source.resolve() != request.source.resolve():
                raise OperationConflictError(
                    f"Project {paths.root} is configured for a different source."
                )
        elif paths.root.exists():
            if not paths.root.is_dir():
                raise OperationConflictError(
                    f"Project path is not a directory: {paths.root}."
                )
            if any(paths.root.iterdir()):
                raise OperationConflictError(
                    f"Project directory is not empty: {paths.root}."
                )
        if (
            saved is not None
            and overrides.includes("chapters")
            and request.chapters is not None
            and request.chapters != saved.chapters
        ):
            raise ProjectScopeConflictError(
                f"Project {paths.root} is configured for chapters "
                f"'{saved.chapters}'. A different chapter selection "
                f"('{request.chapters}') requires a separate project. "
                "Use --fresh or pass a different --project path."
            )
        derived = self._with_source_defaults(request, paths, inspection)
        merged = (
            derived
            if saved is None
            else merge_saved_setup(
                derived,
                saved,
                overrides,
                interactive=interactive,
            )
        )
        if saved is None:
            merged = replace(
                merged,
                spacy=merged.spacy or "sm",
                pause_timing=merged.pause_timing or "engaging",
            )
        elif merged.pause_timing is None:
            merged = replace(merged, pause_timing="fixed")
        if saved is not None:
            merged = _rebuild_for_setup_change(merged, saved)
        origins = self._setup_origins(merged, overrides, saved, inspection)
        return SetupPreparation(
            paths=paths,
            inspection=inspection,
            request=merged,
            origins=origins,
            reused=saved is not None,
        )

    def save_setup(
        self,
        preparation: SetupPreparation,
        request: AudiobookRequest | None = None,
    ) -> ResolvedSetup:
        selected = request or preparation.request
        missing = [
            name
            for name in ("language", "engine", "target")
            if getattr(selected, name) is None
        ]
        if missing:
            raise InputValidationError(
                f"Audiobook setup is missing required values: {', '.join(missing)}."
            )
        if selected.output is None:
            raise InputValidationError("Audiobook output path is required.")
        if selected.output.suffix.casefold() != ".m4b":
            raise InputValidationError("Audiobook output must use the .m4b extension.")

        preparation.paths.root.mkdir(parents=True, exist_ok=True)
        self._backend.save_setup(preparation.paths, selected)
        render_request = self._backend.request_from_intent(preparation.paths, selected)
        return ResolvedSetup(preparation, selected, render_request)

    def preflight(self, resolved: ResolvedSetup) -> PreflightView:
        return PreflightView(
            setup=resolved,
            workflow=self._backend.inspect(resolved.render_request),
        )

    def render(
        self,
        resolved: ResolvedSetup,
        *,
        on_progress: Callable[[ApplicationEvent], None] | None = None,
    ) -> ConversionResultView:
        return self._backend.render(resolved.render_request, on_progress=on_progress)

    def load_saved_setup(self, paths: ProjectPaths) -> AudiobookRequest | None:
        self._reject_legacy_workspace(paths.root, source=None)
        has_intent = paths.intent.is_file()
        has_profile = paths.profile.is_file()
        if has_intent != has_profile:
            raise OperationConflictError(
                "Incomplete TTSForge setup in "
                f"{paths.root}: intent and profile must both exist."
            )
        return self._backend.load_setup(paths) if has_intent else None

    def status(self, paths: ProjectPaths) -> WorkflowPlanView:
        saved = self.load_saved_setup(paths)
        if saved is None:
            raise OperationConflictError(
                f"No saved TTSForge setup exists in {paths.root}."
            )
        request = self._backend.request_from_intent(paths, saved)
        return self._backend.inspect(request)

    @staticmethod
    def _is_legacy_workspace(path: Path) -> bool:
        if path.name.endswith((".ssmdbook", ".readio")):
            return True
        if not path.is_dir():
            return False
        if (path / "project.toml").is_file():
            return True
        return (path / "readio.toml").is_file() and not (
            path / "render.readio.toml"
        ).is_file()

    def _reject_legacy_workspace(self, path: Path, source: Path | None) -> None:
        if self._is_legacy_workspace(path):
            raise LegacyWorkspaceError(self._legacy_workspace_message(path, source))

    @staticmethod
    def _legacy_workspace_message(project: Path, source: Path | None) -> str:
        if source is not None and not source.name.endswith((".ssmdbook", ".readio")):
            source_arg = shlex.quote(str(source))
            suggested_project = ProjectPaths.for_source(source).root
        else:
            source_arg = "<original.epub>"
            suggested_project = Path(f"{project.stem}.ttsforge")
        return (
            "This is a TTSForge/Readio 0.4 project and cannot be resumed by "
            "TTSForge 0.5.\n\n"
            "Create a new project from the original EPUB:\n"
            f"  ttsforge convert {source_arg} --project "
            f"{shlex.quote(str(suggested_project))}\n\n"
            "The old project is left unchanged."
        )

    @staticmethod
    def _with_source_defaults(
        request: AudiobookRequest,
        paths: ProjectPaths,
        inspection: BookInspectionView,
    ) -> AudiobookRequest:
        return AudiobookRequest(
            source=request.source,
            project=paths.root,
            chapters=request.chapters or "all",
            output=request.output or request.source.with_suffix(".m4b"),
            language=request.language or inspection.language,
            engine=request.engine,
            target=request.target,
            voice=request.voice,
            engine_options=request.engine_options,
            speed=request.speed,
            bitrate=request.bitrate,
            spacy=request.spacy,
            speech_profile=request.speech_profile,
            pause_timing=request.pause_timing,
            target_lufs=request.target_lufs,
            title=request.title if request.title is not None else inspection.title,
            author=request.author if request.author is not None else inspection.author,
            cover=request.cover if request.cover is not None else inspection.cover,
            offline=request.offline,
            refresh=request.refresh,
            rebuild_from=request.rebuild_from,
            replace_output=request.replace_output,
            fresh=request.fresh,
        )

    @staticmethod
    @staticmethod
    @staticmethod
    def _setup_origins(
        request: AudiobookRequest,
        overrides: InputOverrides,
        saved: AudiobookRequest | None,
        inspection: BookInspectionView,
    ) -> SetupOrigins:
        fields = (
            "chapters",
            "output",
            "language",
            "engine",
            "target",
            "voice",
            "engine_options",
            "speed",
            "bitrate",
            "spacy",
            "speech_profile",
            "pause_timing",
            "target_lufs",
            "title",
            "author",
            "cover",
        )
        project_fields = frozenset(
            name
            for name in fields
            if saved is not None
            and not overrides.includes(name)
            and getattr(request, name) == getattr(saved, name)
            and (
                bool(getattr(saved, name))
                if name == "engine_options"
                else getattr(saved, name) is not None
            )
        )
        if (
            saved is not None
            and saved.voice is None
            and saved.engine is not None
            and saved.target is not None
            and not overrides.includes("voice")
            and request.engine == saved.engine
            and request.target == saved.target
        ):
            project_fields = project_fields | frozenset({"voice"})
        if saved is not None:
            project_fields = project_fields | frozenset(
                name
                for name in ("spacy", "speech_profile", "pause_timing")
                if not overrides.includes(name) and getattr(saved, name) is None
            )
        derived = {"chapters", "output"} - overrides.fields - project_fields
        source_values = {
            "language": inspection.language,
            "title": inspection.title,
            "author": inspection.author,
            "cover": inspection.cover,
        }
        derived.update(
            name
            for name, value in source_values.items()
            if value is not None
            and getattr(request, name) == value
            and name not in overrides.fields
            and name not in project_fields
        )
        return SetupOrigins(
            explicit=overrides.fields,
            project=project_fields,
            derived=frozenset(derived),
        )

    @staticmethod
    def _fresh_root(root: Path) -> Path:
        if not root.exists():
            return root
        candidate = root.with_name(f"{root.stem}.fresh{root.suffix}")
        index = 2
        while candidate.exists():
            candidate = root.with_name(f"{root.stem}.fresh-{index}{root.suffix}")
            index += 1
        return candidate
