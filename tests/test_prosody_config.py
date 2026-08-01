"""Tests for TTSForge's backend-neutral prosody policy."""

import math

import pytest

from ttsforge.prosody_support import (
    ProsodyPolicy,
    build_pykokoro_prosody_config,
    canonical_prosody_method,
    prosody_policy_payload,
)


@pytest.mark.parametrize(
    "method", ["phase_vocoder", "wsola", "esola", "td_psola", "psola"]
)
def test_supported_methods_translate(method: str) -> None:
    policy = ProsodyPolicy(method=method)  # type: ignore[arg-type]
    translated = build_pykokoro_prosody_config(policy)
    assert translated.method == canonical_prosody_method(method)  # type: ignore[arg-type]


def test_policy_translates_all_advanced_fields() -> None:
    policy = ProsodyPolicy(
        method="esola",
        fallback_methods=("wsola", "phase_vocoder"),
        strict=True,
        clip=True,
        n_fft=4096,
        hop_length=512,
        filter_width=16,
        rolloff=0.8,
        boundary_blend_ms=10.0,
    )
    translated = build_pykokoro_prosody_config(policy)
    assert translated.method == "esola"
    assert translated.fallback_methods == ("wsola", "phase_vocoder")
    assert translated.strict is True
    assert translated.clip is True
    assert translated.n_fft == 4096
    assert translated.hop_length == 512
    assert translated.filter_width == 16
    assert translated.rolloff == 0.8
    assert translated.boundary_blend_ms == 10.0


def test_fallbacks_are_canonicalized_and_primary_is_not_repeated() -> None:
    policy = ProsodyPolicy(
        method="psola",
        fallback_methods=("psola", "td_psola", "wsola", "wsola", "phase_vocoder"),
    )
    assert policy.fallback_methods == ("wsola", "phase_vocoder")
    assert prosody_policy_payload(policy)["prosody_method"] == "td_psola"
    assert prosody_policy_payload(policy)["prosody_fallback_methods"] == [
        "wsola",
        "phase_vocoder",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_fft": 1},
        {"hop_length": 0},
        {"hop_length": 2049},
        {"filter_width": 0},
        {"rolloff": 0.0},
        {"rolloff": math.inf},
        {"boundary_blend_ms": -1.0},
        {"boundary_blend_ms": math.nan},
        {"strict": 1},
        {"clip": "false"},
    ],
)
def test_policy_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ProsodyPolicy(**kwargs)  # type: ignore[arg-type]


def test_psola_and_td_psola_have_equal_canonical_payloads() -> None:
    assert prosody_policy_payload(
        ProsodyPolicy(method="psola")
    ) == prosody_policy_payload(ProsodyPolicy(method="td_psola"))
