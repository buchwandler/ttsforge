"""Tests for TTSForge's provider precedence without ONNX Runtime imports."""

import pytest

from ttsforge.cli.backend_config import resolve_onnx_provider


@pytest.mark.parametrize(
    ("config", "provider", "use_gpu", "expected"),
    [
        ({"onnx_provider": "cpu"}, " nnapi ", None, "nnapi"),
        ({"onnx_provider": "nnapi"}, None, True, "auto"),
        ({"onnx_provider": "nnapi"}, None, False, "cpu"),
        ({"onnx_provider": "xnnpack"}, None, None, "xnnpack"),
        ({"use_gpu": True}, None, None, "auto"),
        ({"use_gpu": False}, None, None, "cpu"),
        ({}, None, None, "cpu"),
    ],
)
def test_provider_precedence(
    config: dict[str, object],
    provider: str | None,
    use_gpu: bool | None,
    expected: str,
) -> None:
    assert (
        resolve_onnx_provider(
            config,
            provider_override=provider,
            use_gpu_override=use_gpu,
        )
        == expected
    )


def test_provider_and_legacy_flag_conflict() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_onnx_provider({}, provider_override="nnapi", use_gpu_override=True)
