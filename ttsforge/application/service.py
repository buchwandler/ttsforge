"""UI-independent audiobook setup, persistence, preflight, and render orchestration."""

from __future__ import annotations

import hashlib
import json
import re
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
    ProjectVariantView,
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


_NEW_VARIANT_SHARED_FIELDS = (
    "chapters",
    "language",
    "spacy",
    "speech_profile",
    "pause_timing",
)


def _validate_new_variant_inputs(
    request: AudiobookRequest,
    saved: AudiobookRequest,
    overrides: InputOverrides,
) -> None:
    changed = tuple(
        field_name
        for field_name in _NEW_VARIANT_SHARED_FIELDS
        if overrides.includes(field_name)
        and (
            (request.pause_timing or "fixed") != (saved.pause_timing or "fixed")
            if field_name == "pause_timing"
            else getattr(request, field_name) != getattr(saved, field_name)
        )
    )
    if changed:
        flags = ", ".join(f"--{name.replace('_', '-')}" for name in changed)
        raise ProjectScopeConflictError(
            f"--new-variant cannot change {flags}: these settings affect shared "
            "source preparation or compile state. Use a separate project with "
            "--project or the normal rebuild workflow."
        )


def _validate_new_variant_flags(request: AudiobookRequest) -> None:
    if not request.new_variant:
        return
    if request.fresh:
        raise InputValidationError("--new-variant cannot be combined with --fresh.")
    if request.rebuild_from in {"convert", "compile"}:
        raise InputValidationError(
            "--new-variant cannot be combined with --rebuild-from convert or compile."
        )


def _merge_setup_request(
    request: AudiobookRequest,
    saved: AudiobookRequest | None,
    overrides: InputOverrides,
    derived: AudiobookRequest,
    *,
    interactive: bool,
) -> AudiobookRequest:
    merge_overrides = overrides
    if request.new_variant and saved is not None:
        merge_overrides = InputOverrides(
            overrides.fields
            | frozenset({"engine", "target", "voice", "engine_options", "speed"})
        )
    merged = (
        derived
        if saved is None
        else merge_saved_setup(derived, saved, merge_overrides, interactive=interactive)
    )
    if request.new_variant and saved is not None:
        merged = replace(
            merged,
            engine=request.engine if overrides.includes("engine") else None,
            target=request.target if overrides.includes("target") else None,
            voice=request.voice if overrides.includes("voice") else None,
            engine_options=(
                request.engine_options if overrides.includes("engine_options") else {}
            ),
            speed=request.speed if overrides.includes("speed") else None,
        )
    return merged


def _validate_new_variant_selectors(
    request: AudiobookRequest,
    merged: AudiobookRequest,
    *,
    interactive: bool,
) -> None:
    if not request.new_variant or interactive:
        return
    missing = [name for name in ("engine", "target") if getattr(merged, name) is None]
    if missing:
        selectors = " and ".join(f"--{name}" for name in missing)
        raise InputValidationError(
            f"--new-variant in non-interactive mode requires explicit {selectors}."
        )


def blocked_workflow_steps(plan: WorkflowPlanView) -> tuple[WorkflowStepView, ...]:
    """Return Readio workflow stages explicitly marked as blocked."""
    return tuple(step for step in plan.steps if step.action == "blocked")


def require_runnable_workflow(plan: WorkflowPlanView) -> None:
    """Raise an application error when Readio's workflow plan is blocked."""
    blocked = blocked_workflow_steps(plan)
    if blocked:
        raise BlockedWorkflowError(blocked)


def _configuration_variant_key(request: AudiobookRequest) -> str:
    identity = {
        "engine": request.engine,
        "target": request.target,
        "voice": request.voice,
        "engine_options": dict(request.engine_options),
        "speed": request.speed,
    }
    serialized = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:8]
    label = "-".join(
        (request.engine or "", request.target or "", request.voice or "default")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:55].rstrip("-")
    return f"{slug}-{digest}" if slug else f"variant-{digest}"


def _resolve_variant_setup(
    preparation: SetupPreparation,
    selected: AudiobookRequest,
    base_request: AudiobookRequest,
) -> tuple[ProjectPaths, AudiobookRequest]:
    variant_key = _configuration_variant_key(selected)
    paths = ProjectPaths.for_variant(preparation.paths.root, variant_key)
    base_output = base_request.output or base_request.source.with_suffix(".m4b")
    if "output" in preparation.origins.explicit:
        output = selected.output
    else:
        output_directory = base_output.parent
        project_root = preparation.paths.root.resolve()
        if output_directory.resolve().is_relative_to(project_root):
            output_directory = selected.source.parent
        output = output_directory / f"{base_output.stem} [{variant_key}].m4b"
    if output is None:
        raise InputValidationError("Audiobook output path is required.")
    if output.suffix.casefold() != ".m4b":
        raise InputValidationError("Audiobook output must use the .m4b extension.")
    resolved_output = output.resolve()
    if resolved_output == selected.source.resolve():
        raise InputValidationError("New-variant output cannot be the source file.")
    if resolved_output.is_relative_to(preparation.paths.root.resolve()):
        raise InputValidationError(
            "New-variant output cannot be inside the TTSForge project."
        )
    if resolved_output == base_output.resolve():
        raise InputValidationError(
            "New-variant output must differ from the base audiobook output."
        )
    return paths, replace(selected, output=output)


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
        _validate_new_variant_flags(request)
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
        elif request.new_variant:
            raise InputValidationError(
                "--new-variant requires an existing TTSForge project. "
                "Run the normal conversion first."
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
        if request.new_variant and saved is not None:
            _validate_new_variant_inputs(request, saved, overrides)
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
        merged = _merge_setup_request(
            request, saved, overrides, derived, interactive=interactive
        )
        if saved is None:
            merged = replace(
                merged,
                spacy=merged.spacy or "sm",
                pause_timing=merged.pause_timing or "engaging",
            )
        elif merged.pause_timing is None:
            merged = replace(merged, pause_timing="fixed")
        _validate_new_variant_selectors(request, merged, interactive=interactive)
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

        paths = preparation.paths
        resolved_preparation = preparation
        if selected.new_variant:
            base_request = self._backend.load_setup(paths)
            paths, selected = _resolve_variant_setup(
                preparation, selected, base_request
            )
            resolved_preparation = replace(preparation, paths=paths, request=selected)
        paths.setup_root.mkdir(parents=True, exist_ok=True)
        self._backend.save_setup(paths, selected)
        render_request = self._backend.request_from_intent(paths, selected)
        return ResolvedSetup(resolved_preparation, selected, render_request)

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

    def list_variants(
        self, paths: ProjectPaths, *, source: Path | None = None
    ) -> tuple[ProjectVariantView, ...]:
        variants_root = paths.root / "variants"
        if not variants_root.is_dir():
            return ()
        variants: list[ProjectVariantView] = []
        for directory in sorted(variants_root.iterdir(), key=lambda item: item.name):
            if not directory.is_dir():
                continue
            variant_paths = ProjectPaths.for_variant(paths.root, directory.name)
            if (
                not variant_paths.intent.is_file()
                or not variant_paths.profile.is_file()
            ):
                variants.append(
                    ProjectVariantView(
                        variant_key=directory.name,
                        error=(
                            "Incomplete setup: both render.readio.toml and "
                            "narrator.renderprofile.toml are required."
                        ),
                    )
                )
                continue
            try:
                saved = self._backend.load_setup(variant_paths)
            except Exception as exc:
                variants.append(
                    ProjectVariantView(
                        variant_key=directory.name,
                        error=f"Invalid setup: {exc}",
                    )
                )
                continue
            error = None
            if source is not None and saved.source.resolve() != source.resolve():
                error = "Saved setup refers to a different source."
            variants.append(
                ProjectVariantView(
                    variant_key=directory.name,
                    output=saved.output,
                    engine=saved.engine,
                    target=saved.target,
                    voice=saved.voice,
                    error=error,
                )
            )
        return tuple(variants)

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
            new_variant=request.new_variant,
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
