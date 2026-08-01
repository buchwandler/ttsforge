"""TTSForge-owned policy for AudioSig-backed SSMD prosody processing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

ProsodyMethod = Literal[
    "phase_vocoder",
    "wsola",
    "esola",
    "td_psola",
    "psola",
]

_PROSODY_METHODS: frozenset[str] = frozenset(
    {"phase_vocoder", "wsola", "esola", "td_psola", "psola"}
)


def canonical_prosody_method(method: ProsodyMethod) -> str:
    """Return the AudioSig canonical spelling for a prosody method."""
    if method == "psola":
        return "td_psola"
    return method


def _validate_method(method: object, field_name: str) -> str:
    if not isinstance(method, str) or method not in _PROSODY_METHODS:
        allowed = ", ".join(sorted(_PROSODY_METHODS))
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return method


def _normalize_fallback_methods(
    primary: str, fallback_methods: object
) -> tuple[str, ...]:
    if not isinstance(fallback_methods, tuple):
        raise ValueError("fallback_methods must be a tuple of prosody methods")

    primary_canonical = canonical_prosody_method(primary)  # type: ignore[arg-type]
    result: list[str] = []
    seen: set[str] = {primary_canonical}
    for index, method in enumerate(fallback_methods):
        value = _validate_method(method, f"fallback_methods[{index}]")
        canonical = canonical_prosody_method(value)  # type: ignore[arg-type]
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ProsodyPolicy:
    """Validated, backend-neutral settings for SSMD rate/pitch processing."""

    method: ProsodyMethod = "wsola"
    fallback_methods: tuple[ProsodyMethod, ...] = ("wsola", "phase_vocoder")
    strict: bool = False
    clip: bool = False
    n_fft: int = 2048
    hop_length: int | None = None
    filter_width: int = 32
    rolloff: float = 0.945
    boundary_blend_ms: float = 5.0

    def __post_init__(self) -> None:
        method = _validate_method(self.method, "method")
        if not isinstance(self.strict, bool):
            raise ValueError("strict must be a boolean")
        if not isinstance(self.clip, bool):
            raise ValueError("clip must be a boolean")
        if isinstance(self.n_fft, bool) or not isinstance(self.n_fft, int):
            raise ValueError("n_fft must be an integer >= 2")
        if self.n_fft < 2:
            raise ValueError("n_fft must be an integer >= 2")
        if self.hop_length is not None:
            if isinstance(self.hop_length, bool) or not isinstance(
                self.hop_length, int
            ):
                raise ValueError("hop_length must be null or an integer > 0")
            if self.hop_length <= 0:
                raise ValueError("hop_length must be null or an integer > 0")
            if self.hop_length > self.n_fft:
                raise ValueError("hop_length must be less than or equal to n_fft")
        if isinstance(self.filter_width, bool) or not isinstance(
            self.filter_width, int
        ):
            raise ValueError("filter_width must be an integer > 0")
        if self.filter_width <= 0:
            raise ValueError("filter_width must be an integer > 0")
        if isinstance(self.rolloff, bool) or not isinstance(self.rolloff, (int, float)):
            raise ValueError("rolloff must be finite and greater than 0 and at most 1")
        if not math.isfinite(float(self.rolloff)) or not 0 < self.rolloff <= 1:
            raise ValueError("rolloff must be finite and greater than 0 and at most 1")
        if isinstance(self.boundary_blend_ms, bool) or not isinstance(
            self.boundary_blend_ms, (int, float)
        ):
            raise ValueError("boundary_blend_ms must be finite and non-negative")
        if not math.isfinite(float(self.boundary_blend_ms)) or self.boundary_blend_ms < 0:
            raise ValueError("boundary_blend_ms must be finite and non-negative")

        normalized_fallbacks = _normalize_fallback_methods(method, self.fallback_methods)
        object.__setattr__(self, "fallback_methods", normalized_fallbacks)


def build_pykokoro_prosody_config(policy: ProsodyPolicy) -> object:
    """Translate a TTSForge policy at the PyKokoro integration boundary."""
    if not isinstance(policy, ProsodyPolicy):
        raise TypeError("policy must be a ProsodyPolicy")
    from pykokoro import ProsodyConfig

    return ProsodyConfig(
        method=canonical_prosody_method(policy.method),
        fallback_methods=tuple(policy.fallback_methods),
        strict=policy.strict,
        clip=policy.clip,
        n_fft=policy.n_fft,
        hop_length=policy.hop_length,
        filter_width=policy.filter_width,
        rolloff=policy.rolloff,
        boundary_blend_ms=policy.boundary_blend_ms,
    )


def prosody_policy_payload(policy: ProsodyPolicy) -> dict[str, object]:
    """Return deterministic, canonical fields for fingerprints and diagnostics."""
    return {
        "prosody_method": canonical_prosody_method(policy.method),
        "prosody_fallback_methods": list(policy.fallback_methods),
        "prosody_strict": policy.strict,
        "prosody_clip": policy.clip,
        "prosody_n_fft": policy.n_fft,
        "prosody_hop_length": policy.hop_length,
        "prosody_filter_width": policy.filter_width,
        "prosody_rolloff": policy.rolloff,
        "prosody_boundary_blend_ms": policy.boundary_blend_ms,
    }
