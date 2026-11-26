from __future__ import annotations

from dataclasses import replace
from threading import Event, Lock
from time import monotonic, sleep

import pytest

from ttsforge.application.errors import ResourceValidationError, WorkflowFailureError
from ttsforge.application.models import EngineModelView
from ttsforge.server.resource_operations import ResourceOperationManager


def _model(*, updatable: bool = True) -> EngineModelView:
    return EngineModelView(
        engine="kitten",
        target="kitten-v1",
        quality=None,
        language="en-US",
        label="Kitten v1",
        installed=True,
        available=True,
        state="ready",
        local_version="provider-revision",
        available_version="provider-revision",
        update_state="current",
        bytes_installed=123,
        bytes_download=123,
        storage_id="provider-storage-id",
        installable=True,
        updatable=updatable,
        removable=True,
        verifiable=True,
        reason=None,
    )


class BlockingResources:
    def __init__(self) -> None:
        self.model = _model()
        self.first_started = Event()
        self.release_first = Event()
        self.lock = Lock()
        self.active = 0
        self.maximum_active = 0
        self.started: list[str] = []

    def validate_action(self, action: str, engine: str, target: str, *, quality=None):
        attribute = {
            "install": "installable",
            "update": "updatable",
            "verify": "verifiable",
            "remove": "removable",
        }[action]
        if not getattr(self.model, attribute):
            raise ResourceValidationError(
                "The model action is unsupported.",
                code=f"model_{action}_unsupported",
            )
        return self.model

    def install_model(self, engine: str, target: str, **kwargs):
        self._run("install", block=True)
        return self.model

    def update_model(self, engine: str, target: str, **kwargs):
        self._run("update")
        return self.model

    def verify_model(self, engine: str, target: str, **kwargs):
        self._run("verify")
        return self.model

    def remove_model(self, engine: str, target: str, **kwargs):
        self._run("remove")
        return self.model

    def model_status(self, engine: str, target: str, *, quality=None):
        return replace(self.model, local_version="refreshed-revision")

    def _run(self, action: str, *, block: bool = False) -> None:
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.started.append(action)
        if block:
            self.first_started.set()
            self.release_first.wait(timeout=2)
        with self.lock:
            self.active -= 1


class FailingResources(BlockingResources):
    def install_model(self, engine: str, target: str, **kwargs):
        raise WorkflowFailureError(
            "The model source is temporarily unavailable.",
            category="resource operation failure",
            code="network_unavailable",
            recoverable=True,
            suggested_action="retry",
        )


def _wait_for_terminal(manager: ResourceOperationManager, operation_id: str):
    deadline = monotonic() + 2
    while monotonic() < deadline:
        operation = manager.get(operation_id)
        if operation.state in {"completed", "failed", "cancelled"}:
            return operation
        sleep(0.005)
    raise AssertionError("Resource operation did not finish before the timeout")


def test_operations_are_serialized_and_return_refreshed_indeterminate_results() -> None:
    resources = BlockingResources()
    manager = ResourceOperationManager(resources)
    try:
        first = manager.submit("install", "kitten", "kitten-v1")
        assert first.state == "queued"
        assert resources.first_started.wait(timeout=2)

        second = manager.submit("verify", "kitten", "kitten-v1")
        assert manager.get(second.id).state == "queued"
        assert manager.get(first.id).state == "running"

        resources.release_first.set()
        completed_first = _wait_for_terminal(manager, first.id)
        completed_second = _wait_for_terminal(manager, second.id)

        assert completed_first.state == "completed"
        assert completed_first.result is not None
        assert completed_first.result.local_version == "refreshed-revision"
        assert completed_second.state == "completed"
        assert completed_second.result is not None
        assert completed_second.result.local_version == "refreshed-revision"
        assert all(
            value is None
            for operation in (completed_first, completed_second)
            for value in (operation.current, operation.total, operation.message)
        )
        assert resources.started == ["install", "verify"]
        assert resources.maximum_active == 1
    finally:
        resources.release_first.set()
        manager.shutdown()


def test_failed_operation_retains_normalized_readio_error_fields() -> None:
    manager = ResourceOperationManager(FailingResources())
    try:
        operation = manager.submit("install", "kitten", "kitten-v1")
        failed = _wait_for_terminal(manager, operation.id)
    finally:
        manager.shutdown()

    assert failed.state == "failed"
    assert failed.error is not None
    assert failed.error.code == "network_unavailable"
    assert failed.error.category == "resource operation failure"
    assert failed.error.message == "The model source is temporarily unavailable."
    assert failed.error.recoverable is True
    assert failed.error.suggested_action == "retry"
    assert failed.result is None


def test_unsupported_action_is_rejected_without_creating_an_operation() -> None:
    resources = BlockingResources()
    resources.model = replace(resources.model, updatable=False)
    manager = ResourceOperationManager(resources)
    try:
        with pytest.raises(ResourceValidationError) as error:
            manager.submit("update", "kitten", "kitten-v1")
        assert error.value.code == "model_update_unsupported"
    finally:
        manager.shutdown()
