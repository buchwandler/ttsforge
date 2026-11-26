from __future__ import annotations

from dataclasses import replace

import pytest

from ttsforge.application.errors import ResourceValidationError, WorkflowFailureError
from ttsforge.application.models import EngineModelView
from ttsforge.application.resources import ResourceApplicationService


class FakeResourceBackend:
    def __init__(self, model: EngineModelView | None = None) -> None:
        self.model = model or _model()
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.failure: Exception | None = None

    def _call(self, name: str, *args: object, **kwargs: object) -> EngineModelView:
        self.calls.append((name, args, kwargs))
        if self.failure is not None:
            raise self.failure
        return self.model

    def list_models(self, engine: str, **kwargs: object) -> tuple[EngineModelView, ...]:
        self._call("list_models", engine, **kwargs)
        return (self.model,)

    def model_status(
        self, engine: str, target: str, **kwargs: object
    ) -> EngineModelView:
        return self._call("model_status", engine, target, **kwargs)

    def install_model(
        self, engine: str, target: str, **kwargs: object
    ) -> EngineModelView:
        return self._call("install_model", engine, target, **kwargs)

    def update_model(
        self, engine: str, target: str, **kwargs: object
    ) -> EngineModelView:
        return self._call("update_model", engine, target, **kwargs)

    def verify_model(
        self, engine: str, target: str, **kwargs: object
    ) -> EngineModelView:
        return self._call("verify_model", engine, target, **kwargs)

    def remove_model(
        self, engine: str, target: str, **kwargs: object
    ) -> EngineModelView:
        return self._call("remove_model", engine, target, **kwargs)


def _model(**changes: object) -> EngineModelView:
    model = EngineModelView(
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
        updatable=True,
        removable=True,
        verifiable=True,
        reason=None,
    )
    return replace(model, **changes)


def test_models_preserves_model_metadata_and_forwards_filters() -> None:
    model = _model(
        bytes_installed=None,
        bytes_download=None,
        installed=False,
        state="missing",
    )
    backend = FakeResourceBackend(model)
    service = ResourceApplicationService(backend)

    result = service.models(
        engine=" kitten ",
        language="en-US",
        installed=None,
        available=True,
        offline=True,
        refresh=True,
    )

    assert result == (model,)
    assert backend.calls == [
        (
            "list_models",
            ("kitten",),
            {
                "language": "en-US",
                "installed": None,
                "available": True,
                "offline": True,
                "refresh": True,
            },
        )
    ]
    assert result[0].bytes_installed is None
    assert result[0].bytes_download is None
    assert result[0].storage_id == "provider-storage-id"


@pytest.mark.parametrize("installed", [True, False])
def test_models_rejects_conflicting_installed_and_available_filters(
    installed: bool,
) -> None:
    service = ResourceApplicationService(FakeResourceBackend())

    with pytest.raises(ResourceValidationError) as error:
        service.models(engine="kitten", installed=installed, available=True)

    assert error.value.code == "invalid_resource_request"


@pytest.mark.parametrize(
    ("method", "capability", "action"),
    [
        ("install_model", "installable", "install_model"),
        ("update_model", "updatable", "update_model"),
        ("verify_model", "verifiable", "verify_model"),
        ("remove_model", "removable", "remove_model"),
    ],
)
def test_model_actions_check_capability_then_delegate(
    method: str, capability: str, action: str
) -> None:
    backend = FakeResourceBackend(_model(**{capability: True}))
    service = ResourceApplicationService(backend)

    result = getattr(service, method)("kitten", "kitten-v1")

    assert result == backend.model
    assert [call[0] for call in backend.calls] == ["model_status", action]


def test_update_rejects_models_without_update_support() -> None:
    service = ResourceApplicationService(FakeResourceBackend(_model(updatable=False)))

    with pytest.raises(ResourceValidationError) as error:
        service.update_model("kitten", "kitten-v1")

    assert error.value.code == "model_update_unsupported"


def test_install_rejects_models_without_install_support() -> None:
    service = ResourceApplicationService(FakeResourceBackend(_model(installable=False)))

    with pytest.raises(ResourceValidationError) as error:
        service.install_model("kitten", "kitten-v1")

    assert error.value.code == "model_install_unsupported"


def test_invalid_selectors_fail_before_backend_call() -> None:
    backend = FakeResourceBackend()
    service = ResourceApplicationService(backend)

    with pytest.raises(ResourceValidationError):
        service.model_status("kitten", " ")

    assert backend.calls == []


def test_backend_failures_are_normalized_without_raw_exception_text() -> None:
    backend = FakeResourceBackend()
    backend.failure = RuntimeError("private provider detail")
    service = ResourceApplicationService(backend)

    with pytest.raises(WorkflowFailureError) as error:
        service.models(engine="kitten")

    assert error.value.code == "resource_inventory_failed"
    assert error.value.category == "resource inventory failure"
    assert "private provider detail" not in str(error.value)
