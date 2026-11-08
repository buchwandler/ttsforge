"""Stable errors exposed by the TTSForge application boundary."""

from __future__ import annotations

from collections.abc import Mapping


class ApplicationError(Exception):
    """Base class for expected application-operation failures."""


class InputValidationError(ApplicationError, ValueError):
    """An operation request or catalog selection is invalid."""


class OperationConflictError(ApplicationError, ValueError):
    """An operation conflicts with saved state or project requirements."""


class CatalogSelectionError(InputValidationError):
    """A deterministic row or public-identifier selection was invalid."""


class SetupConflictError(OperationConflictError):
    """Explicit setup changes conflict with saved dependent choices."""


class ProjectScopeConflictError(OperationConflictError):
    """A request tries to change chapters persisted in an existing project."""


class LegacyWorkspaceError(OperationConflictError):
    """An existing Readio 0.4 workspace cannot be resumed by TTSForge 0.5."""


class WorkflowFailureError(ApplicationError):
    """A structured Readio workflow failure normalized for TTSForge callers."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        stage: str | None = None,
        package: str | None = None,
        selector: str | None = None,
        code: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.stage = stage
        self.package = package
        self.selector = selector
        self.code = code
        self.details = dict(details or {})
