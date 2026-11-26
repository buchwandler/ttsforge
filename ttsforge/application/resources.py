"""Frontend-neutral model resource inventory and lifecycle operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .errors import ResourceValidationError, WorkflowFailureError
from .models import EngineModelView


class ResourceBackend(Protocol):
    def list_models(
        self,
        engine: str,
        *,
        language: str | None = None,
        installed: bool | None = None,
        available: bool = False,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[EngineModelView, ...]: ...

    def model_status(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView: ...

    def install_model(
        self,
        engine: str,
        target: str,
        *,
        quality: str | None = None,
        source: str | None = None,
        force: bool = False,
    ) -> EngineModelView: ...

    def update_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView: ...

    def verify_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView: ...

    def remove_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView: ...


class ResourceApplicationService:
    """Validate model selectors and delegate normalized resource operations."""

    def __init__(self, backend: ResourceBackend) -> None:
        self._backend = backend

    def models(
        self,
        *,
        engine: str,
        language: str | None = None,
        installed: bool | None = None,
        available: bool = False,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[EngineModelView, ...]:
        _required_selector("engine", engine)
        if installed is not None and available:
            raise ResourceValidationError(
                "The installed and available model filters cannot both be true."
            )
        try:
            return self._backend.list_models(
                engine.strip(),
                language=language,
                installed=installed,
                available=available,
                offline=offline,
                refresh=refresh,
            )
        except WorkflowFailureError:
            raise
        except Exception as error:
            raise WorkflowFailureError(
                "The engine model inventory is unavailable.",
                category="resource inventory failure",
                code="resource_inventory_failed",
            ) from error

    def model_status(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        _validate_model_selector(engine, target, quality)
        try:
            return self._backend.model_status(
                engine.strip(), target.strip(), quality=quality
            )
        except WorkflowFailureError:
            raise
        except Exception as error:
            raise WorkflowFailureError(
                "The engine model status is unavailable.",
                category="resource inventory failure",
                code="resource_inventory_failed",
            ) from error

    def validate_action(
        self, action: str, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        model = self._actionable_model(engine, target, quality)
        capabilities = {
            "install": ("installable", "model_install_unsupported"),
            "update": ("updatable", "model_update_unsupported"),
            "verify": ("verifiable", "model_verify_unsupported"),
            "remove": ("removable", "model_remove_unsupported"),
        }
        capability = capabilities.get(action)
        if capability is None:
            raise ResourceValidationError(
                "This engine model action is not supported.",
                code="model_action_unsupported",
            )
        supported_attribute, error_code = capability
        if not getattr(model, supported_attribute):
            raise ResourceValidationError(
                f"The {action} action is not supported for this engine model.",
                code=error_code,
            )
        return model

    def install_model(
        self,
        engine: str,
        target: str,
        *,
        quality: str | None = None,
        source: str | None = None,
        force: bool = False,
    ) -> EngineModelView:
        self.validate_action("install", engine, target, quality=quality)
        return self._run_operation(
            self._backend.install_model,
            engine.strip(),
            target.strip(),
            quality=quality,
            source=source,
            force=force,
        )

    def update_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        self.validate_action("update", engine, target, quality=quality)
        return self._run_operation(
            self._backend.update_model,
            engine.strip(),
            target.strip(),
            quality=quality,
        )

    def verify_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        self.validate_action("verify", engine, target, quality=quality)
        return self._run_operation(
            self._backend.verify_model,
            engine.strip(),
            target.strip(),
            quality=quality,
        )

    def remove_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        self.validate_action("remove", engine, target, quality=quality)
        return self._run_operation(
            self._backend.remove_model,
            engine.strip(),
            target.strip(),
            quality=quality,
        )

    def _actionable_model(
        self, engine: str, target: str, quality: str | None
    ) -> EngineModelView:
        _validate_model_selector(engine, target, quality)
        return self.model_status(engine, target, quality=quality)

    @staticmethod
    def _run_operation(
        operation: Callable[..., EngineModelView], *args: object, **kwargs: object
    ) -> EngineModelView:
        try:
            return operation(*args, **kwargs)
        except WorkflowFailureError:
            raise
        except Exception as error:
            raise WorkflowFailureError(
                "The engine model operation failed.",
                category="resource operation failure",
                code="resource_operation_failed",
            ) from error


def _required_selector(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ResourceValidationError(f"A non-empty {name} selector is required.")


def _validate_model_selector(engine: str, target: str, quality: str | None) -> None:
    _required_selector("engine", engine)
    _required_selector("target", target)
    if quality is not None and not quality.strip():
        raise ResourceValidationError("Quality cannot be empty when provided.")
