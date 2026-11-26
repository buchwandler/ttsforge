"""Process-local executor for long-running engine-model operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Lock
from typing import Literal
from uuid import uuid4

from ..application.errors import ApplicationError
from ..application.models import EngineModelView
from ..application.resources import ResourceApplicationService

ResourceOperationAction = Literal["install", "update", "verify", "remove"]
ResourceOperationState = Literal[
    "queued", "running", "completed", "failed", "cancelled"
]


@dataclass(frozen=True, slots=True)
class ResourceOperationError:
    code: str | None
    message: str
    category: str | None
    recoverable: bool
    suggested_action: str | None


@dataclass(frozen=True, slots=True)
class ResourceOperationRecord:
    id: str
    action: ResourceOperationAction
    state: ResourceOperationState
    engine: str
    target: str
    quality: str | None
    current: int | None = None
    total: int | None = None
    message: str | None = None
    result: EngineModelView | None = None
    error: ResourceOperationError | None = None


class ResourceOperationManager:
    """Queue model operations serially and retain pollable process-local state."""

    def __init__(self, resources: ResourceApplicationService) -> None:
        self._resources = resources
        self._lock = Lock()
        self._operations: dict[str, ResourceOperationRecord] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ttsforge-model-operation"
        )

    def submit(
        self,
        action: ResourceOperationAction,
        engine: str,
        target: str,
        *,
        quality: str | None = None,
        source: str | None = None,
        force: bool = False,
    ) -> ResourceOperationRecord:
        self._resources.validate_action(action, engine, target, quality=quality)
        operation = ResourceOperationRecord(
            id=str(uuid4()),
            action=action,
            state="queued",
            engine=engine,
            target=target,
            quality=quality,
        )
        with self._lock:
            self._operations[operation.id] = operation
            self._executor.submit(self._run, operation, source, force)
        return operation

    def get(self, operation_id: str) -> ResourceOperationRecord:
        with self._lock:
            operation = self._operations.get(operation_id)
        if operation is None:
            raise KeyError(operation_id)
        return operation

    def shutdown(self) -> None:
        """Wait for the non-cancellable Readio worker before server shutdown."""
        self._executor.shutdown(wait=True)

    def _run(
        self,
        operation: ResourceOperationRecord,
        source: str | None,
        force: bool,
    ) -> None:
        self._replace(operation.id, state="running")
        try:
            if operation.action == "install":
                self._resources.install_model(
                    operation.engine,
                    operation.target,
                    quality=operation.quality,
                    source=source,
                    force=force,
                )
            elif operation.action == "update":
                self._resources.update_model(
                    operation.engine,
                    operation.target,
                    quality=operation.quality,
                )
            elif operation.action == "verify":
                self._resources.verify_model(
                    operation.engine,
                    operation.target,
                    quality=operation.quality,
                )
            else:
                self._resources.remove_model(
                    operation.engine,
                    operation.target,
                    quality=operation.quality,
                )
            result = self._resources.model_status(
                operation.engine,
                operation.target,
                quality=operation.quality,
            )
        except Exception as error:  # noqa: BLE001
            self._replace(
                operation.id,
                state="failed",
                error=_operation_error(error),
            )
        else:
            self._replace(operation.id, state="completed", result=result)

    def _replace(
        self,
        operation_id: str,
        *,
        state: ResourceOperationState,
        result: EngineModelView | None = None,
        error: ResourceOperationError | None = None,
    ) -> None:
        with self._lock:
            self._operations[operation_id] = replace(
                self._operations[operation_id],
                state=state,
                result=result,
                error=error,
            )


def _operation_error(error: Exception) -> ResourceOperationError:
    if isinstance(error, ApplicationError):
        return ResourceOperationError(
            code=getattr(error, "code", None),
            message=str(error),
            category=getattr(error, "category", None),
            recoverable=getattr(error, "recoverable", False),
            suggested_action=getattr(error, "suggested_action", None),
        )
    return ResourceOperationError(
        code="resource_operation_failed",
        message="The engine model operation failed.",
        category="resource operation failure",
        recoverable=False,
        suggested_action=None,
    )
