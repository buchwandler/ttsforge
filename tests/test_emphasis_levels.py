"""Regression tests for the user-facing SSMD emphasis level contract."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ttsforge.cli import app, commands_conversion
from ttsforge.conversion import ConversionOptions, TTSConverter
from ttsforge.resume_identity import diff_generation_identity
from ttsforge.ssmd_support import (
    EMPHASIS_PRESETS,
    SSMDPolicy,
    build_pykokoro_ssmd_config,
    infer_emphasis_level,
    resolve_emphasis_level,
)


@pytest.mark.parametrize(
    ("level", "mode", "scale"),
    [
        (0, "plain", 1.0),
        (1, "approximate", 0.5),
        (2, "approximate", 1.0),
        (3, "approximate", 1.5),
    ],
)
def test_emphasis_presets_and_pykokoro_forwarding(
    level: int, mode: str, scale: float
) -> None:
    preset = resolve_emphasis_level(level)
    assert EMPHASIS_PRESETS[level] == preset
    assert (preset.mode, preset.gain_scale) == (mode, scale)
    policy = SSMDPolicy(emphasis_mode=mode, emphasis_gain_scale=scale)  # type: ignore[arg-type]
    assert build_pykokoro_ssmd_config(policy).emphasis_gain_scale == scale
    assert infer_emphasis_level(policy.emphasis_mode, policy.emphasis_gain_scale) == level


@pytest.mark.parametrize("value", [-0.1, 2.1, float("inf"), float("nan"), True])
def test_policy_rejects_invalid_emphasis_gain_scale(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        SSMDPolicy(emphasis_gain_scale=value)  # type: ignore[arg-type]


def test_emphasis_resolver_precedence_and_legacy_equivalence() -> None:
    assert commands_conversion._resolve_emphasis_controls(
        configured_level=None,
        configured_mode="plain",
        explicit_level=2,
        explicit_mode=None,
        legacy_enable=False,
    ) == ("approximate", 1.0, 2)
    assert commands_conversion._resolve_emphasis_controls(
        configured_level=None,
        configured_mode="plain",
        explicit_level=None,
        explicit_mode=None,
        legacy_enable=True,
    ) == ("approximate", 1.0, 2)
    assert commands_conversion._resolve_emphasis_controls(
        configured_level=3,
        configured_mode="plain",
        explicit_level=None,
        explicit_mode=None,
        legacy_enable=False,
    ) == ("approximate", 1.5, 3)
    assert commands_conversion._resolve_emphasis_controls(
        configured_level=None,
        configured_mode="warn",
        explicit_level=None,
        explicit_mode=None,
        legacy_enable=False,
    ) == ("warn", 1.0, None)


@pytest.mark.parametrize(
    ("explicit_level", "explicit_mode", "legacy_enable"),
    [(2, None, True), (2, "approximate", False), (None, "approximate", True)],
)
def test_emphasis_controls_reject_ambiguous_combinations(
    explicit_level: int | None, explicit_mode: str | None, legacy_enable: bool
) -> None:
    with pytest.raises(typer.BadParameter, match="Choose only one emphasis control"):
        commands_conversion._resolve_emphasis_controls(
            configured_level=None,
            configured_mode="plain",
            explicit_level=explicit_level,
            explicit_mode=explicit_mode,
            legacy_enable=legacy_enable,
        )


def test_configured_strict_policy_conflicts_with_level() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        commands_conversion._resolve_emphasis_controls(
            configured_level=2,
            configured_mode="warn",
            explicit_level=None,
            explicit_mode=None,
            legacy_enable=False,
        )


def test_convert_option_preserves_omission_and_explicit_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[dict[str, object]] = []

    def fake_convert(**kwargs: object) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(commands_conversion, "convert", fake_convert)
    source = tmp_path / "book.epub"
    source.write_bytes(b"placeholder")
    runner = CliRunner()

    assert runner.invoke(app, ["convert", str(source)]).exit_code == 0
    assert captured[-1]["emphasis_level"] is None
    assert (
        runner.invoke(app, ["convert", str(source), "--emphasis-level", "0"]).exit_code
        == 0
    )
    assert captured[-1]["emphasis_level"] == 0


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_cli_accepts_emphasis_levels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, level: int
) -> None:
    monkeypatch.setattr(commands_conversion, "convert", lambda **kwargs: None)
    source = tmp_path / "book.epub"
    source.write_bytes(b"placeholder")
    result = CliRunner().invoke(
        app, ["convert", str(source), "--emphasis-level", str(level)]
    )
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("level", [-1, 4])
def test_cli_rejects_out_of_range_emphasis_levels(
    tmp_path: Path, level: int
) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"placeholder")
    result = CliRunner().invoke(
        app, ["convert", str(source), "--emphasis-level", str(level)]
    )
    assert result.exit_code == 2


def test_emphasis_levels_change_fingerprints_in_paragraph_mode() -> None:
    fingerprints = {
        level: TTSConverter(
            ConversionOptions(
                conversion_unit="paragraph",
                ssmd_policy=SSMDPolicy(
                    emphasis_mode=preset.mode,
                    emphasis_gain_scale=preset.gain_scale,
                ),
            )
        )._generation_fingerprint()
        for level, preset in EMPHASIS_PRESETS.items()
    }
    assert len(set(fingerprints.values())) == 4


def test_legacy_identity_without_gain_scale_migrates_to_one() -> None:
    saved = {"ssmd_policy": {"emphasis_mode": "approximate"}}
    current = {
        "ssmd_policy": {"emphasis_mode": "approximate", "emphasis_gain_scale": 1.0}
    }
    assert diff_generation_identity(saved, current) == ()
    assert commands_conversion._ssmd_policy_from_identity(saved).emphasis_gain_scale == 1.0
