"""Stable errors exposed by the TTSForge application boundary."""


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
    """An existing TTSForge workspace cannot be used as a Readio project."""


class ProjectMigrationRequiredError(OperationConflictError):
    """A Readio project requires an explicit schema migration before use."""
