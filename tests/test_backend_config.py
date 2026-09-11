"""Tests for TTSForge's provider precedence without ONNX Runtime imports."""

import pytest

from ttsforge.cli.backend_config import (
    resolve_model_source_and_variant,
    resolve_onnx_provider,
)


@pytest.mark.parametrize(
    ("config", "provider", "expected"),
    [
        ({"onnx_provider": "cpu"}, " nnapi ", "nnapi"),
        ({"onnx_provider": "nnapi"}, None, "nnapi"),
        ({"onnx_provider": "xnnpack"}, None, "xnnpack"),
        ({}, None, "cpu"),
    ],
)
def test_provider_precedence(
    config: dict[str, object],
    provider: str | None,
    expected: str,
) -> None:
    assert resolve_onnx_provider(config, provider_override=provider) == expected


@pytest.mark.parametrize(
    "provider",
    [
        "auto",
        "cpu",
        "openvino",
        "nnapi",
        "xnnpack",
        "CPUExecutionProvider",
        "OpenVINOExecutionProvider",
        "NnapiExecutionProvider",
        "XnnpackExecutionProvider",
        "Custom_1ExecutionProvider",
    ],
)
def test_explicit_provider_uses_shared_syntax_contract(provider: str) -> None:
    assert resolve_onnx_provider({}, provider_override=f"  {provider}  ") == provider


@pytest.mark.parametrize("provider", ["", "  ", "potato", "CPU ExecutionProvider"])
def test_invalid_explicit_provider_is_rejected_before_backend(provider: str) -> None:
    with pytest.raises(ValueError, match="Invalid ONNX provider"):
        resolve_onnx_provider({}, provider_override=provider)


def test_invalid_configured_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid ONNX provider"):
        resolve_onnx_provider(
            {"onnx_provider": "potato"},
            provider_override=None,
        )


def test_model_resolution_keeps_automatic_and_explicit_values() -> None:
    assert resolve_model_source_and_variant({}) == (None, None)
    assert resolve_model_source_and_variant(
        {"model_source": "github", "model_variant": "v1.0"}
    ) == ("github", "v1.0")
    assert resolve_model_source_and_variant(
        {"model_source": "github", "model_variant": "v1.2-de-martin"}
    ) == ("github", "v1.2-de-martin")


def test_unknown_model_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown model profile"):
        resolve_model_source_and_variant({"model_variant": "v9"})
