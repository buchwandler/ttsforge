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
from .narrations import NarrationApplicationService
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
        self._narrations = NarrationApplicationService(audiobook, catalog)

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
            if request.new_variant:
                preparation = self._narrations.prepare_setup(
                    request, overrides, interactive=False
                )
            else:
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

        self._narrations.validate_selection(selected)
        if selected.new_variant:
            resolved = self._narrations.create_from_preparation(preparation, selected)
        else:
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
