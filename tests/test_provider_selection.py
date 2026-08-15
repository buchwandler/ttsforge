"""Regression coverage for the generic TTSForge/PyKokoro provider contract."""

import pytest
from pykokoro.exceptions import ConfigurationError
from pykokoro.onnx_session import resolve_execution_provider


def test_desktop_provider_resolution_and_unavailable_error() -> None:
    available = ("OpenVINOExecutionProvider", "CPUExecutionProvider")

    assert resolve_execution_provider("cpu", available=available) == (
        "CPUExecutionProvider"
    )
    assert resolve_execution_provider("openvino", available=available) == (
        "OpenVINOExecutionProvider"
    )
    assert resolve_execution_provider("auto", available=available) == (
        "OpenVINOExecutionProvider"
    )
    with pytest.raises(
        ConfigurationError, match="Requested execution provider is unavailable"
    ):
        resolve_execution_provider("nnapi", available=available)


def test_termux_provider_resolution_and_unavailable_error() -> None:
    available = (
        "NnapiExecutionProvider",
        "XnnpackExecutionProvider",
        "CPUExecutionProvider",
    )

    assert resolve_execution_provider("nnapi", available=available) == (
        "NnapiExecutionProvider"
    )
    assert resolve_execution_provider("xnnpack", available=available) == (
        "XnnpackExecutionProvider"
    )
    assert resolve_execution_provider("auto", available=available) == (
        "NnapiExecutionProvider"
    )
    with pytest.raises(
        ConfigurationError, match="Requested execution provider is unavailable"
    ):
        resolve_execution_provider("openvino", available=available)


def test_pykokoro_environment_override_remains_documented_contract(monkeypatch) -> None:
    available = ("OpenVINOExecutionProvider", "CPUExecutionProvider")
    monkeypatch.setenv("ONNX_PROVIDER", "cpu")

    assert resolve_execution_provider("openvino", available=available) == (
        "CPUExecutionProvider"
    )
