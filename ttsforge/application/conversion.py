"""Shared non-interactive conversion preparation and execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .catalog_service import CatalogApplicationService
from .errors import InputValidationError
from .events import ApplicationEvent
from .models import (
    AudiobookRequest,
    ConversionResultView,
    InputOverrides,
    PreflightView,
    ResolvedSetup,
    SetupPreparation,
    SpacyModelView,
)
from .service import AudiobookApplicationService, require_runnable_workflow


@dataclass(frozen=True, slots=True)
class PreparedConversion:
    preparation: SetupPreparation
    resolved: ResolvedSetup
    spacy_model: SpacyModelView | None
    preflight: PreflightView


class ConversionCoordinator:
    """Finalize a selected request once for every TTSForge frontend."""

    def __init__(
        self,
        audiobook: AudiobookApplicationService,
        catalog: CatalogApplicationService,
    ) -> None:
        self._audiobook = audiobook
        self._catalog = catalog

    def prepare(
        self,
        request: AudiobookRequest,
        overrides: InputOverrides,
        *,
        preparation: SetupPreparation | None = None,
        on_spacy_model: Callable[[SpacyModelView], bool] | None = None,
        on_preflight: Callable[[PreflightView, SpacyModelView | None], None]
        | None = None,
    ) -> PreparedConversion:
        """Complete setup, resource provisioning, and runnable preflight."""
        if preparation is None:
            preparation = self._audiobook.prepare_setup(
                request, overrides, interactive=False
            )
            selected = preparation.request
        else:
            selected = request

        if preparation.inspection.kind != "book":
            raise InputValidationError(
                "Convert requires a book source such as an EPUB."
            )

        self._validate_selection(selected)
        resolved = self._audiobook.save_setup(preparation, selected)
        preparation = resolved.preparation
        spacy_model = self._prepare_spacy(
            resolved.request, on_spacy_model=on_spacy_model
        )
        preflight = self._audiobook.preflight(resolved)
        if on_preflight is not None:
            on_preflight(preflight, spacy_model)
        require_runnable_workflow(preflight.workflow)
        return PreparedConversion(preparation, resolved, spacy_model, preflight)

    def execute(
        self,
        prepared: PreparedConversion,
        *,
        on_progress: Callable[[ApplicationEvent], None] | None = None,
    ) -> ConversionResultView:
        """Render a previously prepared conversion."""
        return self._audiobook.render(prepared.resolved, on_progress=on_progress)

    def _validate_selection(self, request: AudiobookRequest) -> None:
        if request.engine is None or request.target is None or request.language is None:
            return None
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
                default_voice=selected.default_voice,
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
                f"--new-variant requires --voice for target {request.target!r}, "
                "which has no default voice."
            )

    def _prepare_spacy(
        self,
        request: AudiobookRequest,
        *,
        on_spacy_model: Callable[[SpacyModelView], bool] | None,
    ) -> SpacyModelView | None:
        if request.spacy not in {"sm", "md", "lg", "trf"}:
            return None
        if request.language is None:
            raise InputValidationError("Language is required to resolve a spaCy model.")
        model = self._catalog.inspect_spacy_model(request.language, request.spacy)
        if on_spacy_model is not None and not on_spacy_model(model):
            raise InputValidationError(
                f"spaCy model {model.model!r} is required to continue."
            )
        if model.installed:
            return model
        return self._catalog.ensure_spacy_model(
            request.language, request.spacy, offline=request.offline
        )
