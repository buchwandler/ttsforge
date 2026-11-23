"""TTSForge-owned narration identities and project operations."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..chapter_selection import normalize_chapter_selection
from .errors import (
    InputValidationError,
    OperationConflictError,
    ProjectScopeConflictError,
)
from .models import (
    AudiobookRequest,
    InputOverrides,
    NarrationId,
    NarrationView,
    ProjectPaths,
    ResolvedSetup,
    SetupPreparation,
)

if TYPE_CHECKING:
    from .catalog_service import CatalogApplicationService
    from .service import AudiobookApplicationService


_SHARED_SETTINGS = frozenset(
    {"chapters", "language", "spacy", "speech_profile", "pause_timing"}
)


def _changed_shared_settings(
    audiobook: AudiobookApplicationService,
    request: AudiobookRequest,
    saved: AudiobookRequest,
    overrides: InputOverrides,
) -> tuple[str, ...]:
    changed: list[str] = []
    inspection = None
    for field_name in _SHARED_SETTINGS:
        if not overrides.includes(field_name):
            continue
        if field_name == "chapters":
            if request.chapters is None:
                continue
            if inspection is None:
                inspection = audiobook.inspect_book(request.source)
            try:
                value = normalize_chapter_selection(
                    request.chapters, len(inspection.chapters)
                )
            except ValueError as exc:
                raise InputValidationError(str(exc)) from exc
        elif field_name == "pause_timing":
            value = request.pause_timing or "fixed"
        else:
            value = getattr(request, field_name)
        saved_value = getattr(saved, field_name)
        if field_name == "pause_timing":
            saved_value = saved.pause_timing or "fixed"
        if value != saved_value:
            changed.append(field_name)
    return tuple(sorted(changed))


class NarrationApplicationService:
    """Own narration identity while Readio continues to own rendering workflows."""

    def __init__(
        self,
        audiobook: AudiobookApplicationService,
        catalog: CatalogApplicationService,
    ) -> None:
        self._audiobook = audiobook
        self._catalog = catalog

    def prepare_setup(
        self,
        request: AudiobookRequest,
        overrides: InputOverrides,
        *,
        interactive: bool = True,
    ) -> SetupPreparation:
        if not request.new_variant:
            raise InputValidationError(
                "Narration setup requires an additional-narration request."
            )
        if request.fresh:
            raise InputValidationError("--new-variant cannot be combined with --fresh.")
        if request.rebuild_from in {"convert", "compile"}:
            raise InputValidationError(
                "--new-variant cannot be combined with --rebuild-from "
                "convert or compile."
            )

        paths = ProjectPaths.for_source(request.source, request.project)
        saved = self._audiobook.load_saved_setup(paths)
        if saved is None:
            raise InputValidationError(
                "--new-variant requires an existing TTSForge project. "
                "Run the normal conversion first."
            )
        if saved.source.resolve() != request.source.resolve():
            raise OperationConflictError(
                f"Project {paths.root} is configured for a different source."
            )

        changed = _changed_shared_settings(self._audiobook, request, saved, overrides)
        if changed:
            flags = ", ".join(f"--{name.replace('_', '-')}" for name in changed)
            raise ProjectScopeConflictError(
                f"--new-variant cannot change {flags}: these settings affect shared "
                "source preparation or compile state. Use a separate project with "
                "--project or the normal rebuild workflow."
            )

        shared = {
            "chapters": saved.chapters,
            "language": saved.language,
            "spacy": saved.spacy,
            "speech_profile": saved.speech_profile,
            "pause_timing": saved.pause_timing,
        }
        synthesis_fields = {"engine", "target", "voice", "engine_options", "speed"}
        generic_overrides = InputOverrides(
            (overrides.fields - _SHARED_SETTINGS) | synthesis_fields
        )
        preparation = self._audiobook.prepare_setup(
            replace(request, **shared, new_variant=False),
            generic_overrides,
            interactive=interactive,
        )
        missing = [
            name
            for name in ("engine", "target")
            if getattr(preparation.request, name) is None
        ]
        if missing and not interactive:
            selectors = " and ".join(f"--{name}" for name in missing)
            raise InputValidationError(
                f"--new-variant in non-interactive mode requires explicit {selectors}."
            )
        origins = replace(
            preparation.origins,
            explicit=overrides.fields,
            project=preparation.origins.project - overrides.fields,
            derived=preparation.origins.derived - overrides.fields,
        )
        return replace(
            preparation,
            request=replace(preparation.request, new_variant=True),
            origins=origins,
        )

    def list(
        self, paths: ProjectPaths, *, source: Path | None = None
    ) -> tuple[NarrationView, ...]:
        narrations: list[NarrationView] = []
        primary = self._audiobook.load_saved_setup(paths)
        if primary is not None:
            display_name, _ = _read_display_name(paths)
            narrations.append(
                NarrationView(
                    id="primary",
                    display_name=display_name or "Primary narration",
                    primary=True,
                    output=primary.output,
                    engine=primary.engine,
                    target=primary.target,
                    voice=primary.voice,
                )
            )

        for variant in self._audiobook.list_variants(
            paths, source=source or (primary.source if primary is not None else None)
        ):
            variant_paths = ProjectPaths.for_variant(paths.root, variant.variant_key)
            display_name, metadata_error = _read_display_name(variant_paths)
            narrations.append(
                NarrationView(
                    id=variant.variant_key,
                    display_name=display_name
                    or _default_display_name(
                        variant.engine, variant.target, variant.voice
                    ),
                    primary=False,
                    output=variant.output,
                    engine=variant.engine,
                    target=variant.target,
                    voice=variant.voice,
                    error=variant.error or metadata_error,
                )
            )
        return tuple(narrations)

    def get(self, paths: ProjectPaths, narration_id: str) -> NarrationView:
        try:
            identifier = NarrationId(narration_id).value
        except ValueError as exc:
            raise InputValidationError(str(exc)) from exc
        for narration in self.list(paths):
            if narration.id == identifier:
                return narration
        raise InputValidationError(
            f"Narration {identifier!r} does not exist in {paths.root}."
        )

    def create(
        self,
        paths: ProjectPaths,
        *,
        display_name: str,
        engine: str,
        target: str,
        voice: str | None = None,
        engine_options: dict[str, object] | None = None,
        speed: float | None = None,
        output: Path | None = None,
    ) -> NarrationView:
        display_name = display_name.strip()
        if not display_name:
            raise InputValidationError("Narration display name cannot be empty.")
        if not engine or not target:
            raise InputValidationError(
                "Narration creation requires an engine and target."
            )
        base = self._audiobook.load_saved_setup(paths)
        if base is None:
            raise OperationConflictError(
                f"Create a primary TTSForge setup before adding narrations to "
                f"{paths.root}."
            )

        request = replace(
            base,
            project=paths.root,
            engine=engine,
            target=target,
            voice=voice,
            engine_options=engine_options or {},
            speed=speed,
            output=output or base.output,
            new_variant=True,
        )
        fields = {"engine", "target", "voice", "engine_options", "speed"}
        if output is not None:
            fields.add("output")
        preparation = self.prepare_setup(
            request, InputOverrides(frozenset(fields)), interactive=False
        )
        selected = preparation.request
        self.validate_selection(selected)
        resolved = self.create_from_preparation(
            preparation, selected, display_name=display_name
        )
        from .service import require_runnable_workflow

        require_runnable_workflow(self._audiobook.preflight(resolved).workflow)
        return self.get(paths, _configuration_variant_key(selected))

    def create_from_preparation(
        self,
        preparation: SetupPreparation,
        selected: AudiobookRequest,
        *,
        display_name: str | None = None,
    ) -> ResolvedSetup:
        if not selected.new_variant:
            raise InputValidationError(
                "Narration creation requires a new-narration request."
            )
        base = self._audiobook.load_saved_setup(preparation.paths)
        if base is None:
            raise OperationConflictError(
                f"A new narration requires an existing TTSForge project in "
                f"{preparation.paths.root}."
            )
        selected_name = (
            display_name
            or _default_display_name(selected.engine, selected.target, selected.voice)
        ).strip()
        if not selected_name:
            raise InputValidationError("Narration display name cannot be empty.")

        narration_id = _configuration_variant_key(selected)
        variant_paths = ProjectPaths.for_variant(preparation.paths.root, narration_id)
        existing = self._audiobook.load_saved_setup(variant_paths)
        reserved_outputs = {base.output.resolve()} if base.output is not None else set()
        reserved_outputs.update(
            variant.output.resolve()
            for variant in self._audiobook.list_variants(preparation.paths)
            if variant.variant_key != narration_id and variant.output is not None
        )
        selected = _resolve_variant_output(
            preparation,
            selected,
            base,
            existing,
            selected_name,
            reserved_outputs,
        )
        selected = replace(selected, project=preparation.paths.root, new_variant=False)
        variant_preparation = replace(
            preparation, paths=variant_paths, request=selected
        )
        resolved = self._audiobook.save_setup(variant_preparation, selected)
        _write_display_name(variant_paths, narration_id, selected_name)
        return resolved

    def validate_selection(self, request: AudiobookRequest) -> None:
        if request.engine is None or request.target is None or request.language is None:
            return
        targets = self._catalog.targets(
            engine=request.engine,
            language=request.language,
            offline=request.offline,
            refresh=request.refresh,
        )
        selected = next((item for item in targets if item.id == request.target), None)
        if selected is None:
            raise InputValidationError(
                f"Target {request.target!r} is not available for language "
                f"{request.language!r}."
            )
        if selected.reference_only:
            raise InputValidationError(
                f"Target {request.target!r} requires reference audio, "
                "which TTSForge does not support."
            )
        if request.voice is not None:
            voices = self._catalog.voices(
                engine=request.engine,
                target=request.target,
                language=request.language,
                offline=request.offline,
                refresh=request.refresh,
            )
            if not any(item.id == request.voice for item in voices):
                raise InputValidationError(
                    f"Voice {request.voice!r} is not available for target "
                    f"{request.target!r}."
                )
        if (
            request.new_variant
            and request.voice is None
            and selected.voice_count > 0
            and selected.default_voice is None
        ):
            raise InputValidationError(
                f"Narration creation requires --voice for target {request.target!r}, "
                "which has no default voice."
            )

    def request_for_render(
        self, paths: ProjectPaths, narration_id: str
    ) -> tuple[AudiobookRequest, InputOverrides]:
        narration = self.get(paths, narration_id)
        narration_paths = (
            paths
            if narration.primary
            else ProjectPaths.for_variant(paths.root, narration.id)
        )
        saved = self._audiobook.load_saved_setup(narration_paths)
        if saved is None:
            raise InputValidationError(
                f"Narration {narration.id!r} has no saved setup."
            )
        request = replace(
            saved,
            project=paths.root,
            new_variant=not narration.primary,
        )
        fields = frozenset(
            {"engine", "target", "voice", "engine_options", "speed", "output"}
        )
        return request, InputOverrides(fields)

    def profile_path(self, paths: ProjectPaths, narration_id: str) -> Path:
        request, _ = self.request_for_render(paths, narration_id)
        if request.new_variant:
            return ProjectPaths.for_variant(paths.root, narration_id).profile
        return paths.profile

    def delete(self, paths: ProjectPaths, narration_id: str) -> None:
        narration = self.get(paths, narration_id)
        if narration.primary:
            raise OperationConflictError("The primary narration cannot be deleted.")
        variant_paths = ProjectPaths.for_variant(paths.root, narration.id)
        variants_root = (paths.root / "variants").resolve()
        setup_root = variant_paths.setup_root.resolve()
        if not setup_root.is_relative_to(variants_root):
            raise InputValidationError(
                "Narration storage resolves outside the project variants folder."
            )
        shutil.rmtree(setup_root)


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
    return f"{slug}-{digest}" if slug else f"narration-{digest}"


def _resolve_variant_output(
    preparation: SetupPreparation,
    selected: AudiobookRequest,
    base_request: AudiobookRequest,
    existing: AudiobookRequest | None,
    display_name: str,
    reserved_outputs: set[Path],
) -> AudiobookRequest:
    base_output = base_request.output or base_request.source.with_suffix(".m4b")
    if "output" in preparation.origins.explicit:
        output = selected.output
    else:
        output_directory = base_output.parent
        project_root = preparation.paths.root.resolve()
        if output_directory.resolve().is_relative_to(project_root):
            output_directory = selected.source.parent
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", display_name).strip(" .-")
        safe_name = safe_name or "Narration"
        candidate = output_directory / f"{base_output.stem} [{safe_name}].m4b"
        if existing is not None and existing.output is not None:
            if existing.output.resolve() == candidate.resolve():
                output = existing.output
            else:
                output = _unused_output_path(candidate, reserved_outputs)
        else:
            output = _unused_output_path(candidate, reserved_outputs)
    if output is None:
        raise InputValidationError("Audiobook output path is required.")
    if output.suffix.casefold() != ".m4b":
        raise InputValidationError("Audiobook output must use the .m4b extension.")
    resolved_output = output.resolve()
    if resolved_output == selected.source.resolve():
        raise InputValidationError("Narration output cannot be the source file.")
    if resolved_output.is_relative_to(preparation.paths.root.resolve()):
        raise InputValidationError(
            "Narration output cannot be inside the TTSForge project."
        )
    if resolved_output == base_output.resolve():
        raise InputValidationError(
            "Narration output must differ from the primary audiobook output."
        )
    if (
        existing is not None
        and existing.output is not None
        and resolved_output == existing.output.resolve()
    ):
        return replace(selected, output=output)
    if resolved_output in reserved_outputs:
        raise InputValidationError(
            "Narration output conflicts with another saved narration."
        )
    return replace(selected, output=output)


def _unused_output_path(candidate: Path, reserved_outputs: set[Path]) -> Path:
    if not candidate.exists() and candidate.resolve() not in reserved_outputs:
        return candidate
    suffix = 2
    while True:
        alternate = candidate.with_name(
            f"{candidate.stem} ({suffix}){candidate.suffix}"
        )
        if not alternate.exists() and alternate.resolve() not in reserved_outputs:
            return alternate
        suffix += 1


def _default_display_name(
    engine: str | None, target: str | None, voice: str | None
) -> str:
    parts = [value for value in (engine, voice or target) if value]
    return " ".join(parts) if parts else "Additional narration"


def _read_display_name(paths: ProjectPaths) -> tuple[str | None, str | None]:
    metadata_path = paths.setup_root / "narration.json"
    if not metadata_path.is_file():
        return None, None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"Invalid TTSForge narration metadata: {exc}"
    display_name = metadata.get("display_name") if isinstance(metadata, dict) else None
    if not isinstance(display_name, str) or not display_name.strip():
        return None, "Invalid TTSForge narration metadata: display_name is required."
    return display_name.strip(), None


def _write_display_name(
    paths: ProjectPaths, narration_id: str, display_name: str
) -> None:
    metadata_path = paths.setup_root / "narration.json"
    metadata_path.write_text(
        json.dumps(
            {"id": narration_id, "display_name": display_name},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
