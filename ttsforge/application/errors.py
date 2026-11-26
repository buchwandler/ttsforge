"""Stable errors exposed by the TTSForge application boundary."""

from __future__ import annotations

from collections.abc import Mapping

from .models import WorkflowStepView


class ApplicationError(Exception):
    """Base class for expected application-operation failures."""


class BlockedWorkflowError(ApplicationError):
    """A preflight plan cannot execute because one or more stages are blocked."""

    def __init__(self, blocked_steps: tuple[WorkflowStepView, ...]) -> None:
        self.blocked_steps = blocked_steps
        self.code = "workflow_blocked"
        self.details = {
            "blocked_steps": [
                {
                    "stage": step.stage,
                    "action": step.action,
                    "state": step.state,
                    "reason": step.reason,
                    "package": step.package,
                    "selector": step.selector,
                }
                for step in blocked_steps
            ]
        }
        summary = "; ".join(f"{step.stage}: {step.reason}" for step in blocked_steps)
        super().__init__(f"Workflow is blocked: {summary}")


class InputValidationError(ApplicationError, ValueError):
    """An operation request or catalog selection is invalid."""


class ResourceValidationError(InputValidationError):
    """A model resource request is invalid at the application boundary."""

    def __init__(self, message: str, *, code: str = "invalid_resource_request") -> None:
        super().__init__(message)
        self.code = code


class OperationConflictError(ApplicationError, ValueError):
    """An operation conflicts with saved state or project requirements."""


class ResourceOperationConflictError(OperationConflictError):
    """A model mutation conflicts with an active audiobook job."""

    def __init__(self, active_job_id: str) -> None:
        super().__init__(
            f"Engine model mutations are unavailable while audiobook job "
            f"{active_job_id} is active."
        )
        self.code = "resource_operation_conflict"
        self.details = {"active_job_id": active_job_id}


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
        recoverable: bool = False,
        suggested_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.stage = stage
        self.package = package
        self.selector = selector
        self.code = code
        self.details = dict(details or {})
        self.recoverable = recoverable
        self.suggested_action = suggested_action
