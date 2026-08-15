"""Tests for prosody configuration and conversion CLI boundaries."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ttsforge.cli import app
from ttsforge.cli.commands_conversion import _resolve_prosody_policy
from ttsforge.constants import DEFAULT_CONFIG
from ttsforge.conversion import ConversionOptions, TTSConverter
from ttsforge.prosody_support import ProsodyPolicy
from ttsforge.utils import load_config


def test_resolve_prosody_policy_uses_config_then_explicit_overrides() -> None:
    config = {
        **DEFAULT_CONFIG,
        "prosody_method": "esola",
        "prosody_strict": False,
        "prosody_fallback_methods": ["wsola", "phase_vocoder"],
    }
    configured = _resolve_prosody_policy(config)
    assert configured.method == "esola"
    assert configured.strict is False

    overridden = _resolve_prosody_policy(
        config, method_override="psola", strict_override=True
    )
    assert overridden.method == "psola"
    assert overridden.strict is True


def test_schema7_resume_overlays_only_explicit_prosody_fields() -> None:
    saved = (
        TTSConverter(
            ConversionOptions(
                prosody_policy=ProsodyPolicy(method="esola", strict=True),
            )
        )
        ._generation_identity()
        .payload
    )
    changed_config = {
        **DEFAULT_CONFIG,
        "prosody_method": "wsola",
        "prosody_strict": False,
    }

    restored = _resolve_prosody_policy(changed_config, saved_identity=saved)
    strict_override = _resolve_prosody_policy(
        changed_config,
        saved_identity=saved,
        strict_override=False,
    )

    assert restored.method == "esola"
    assert restored.strict is True
    assert strict_override.method == "esola"
    assert strict_override.strict is False


def test_convert_help_exposes_optional_prosody_controls() -> None:
    result = CliRunner().invoke(app, ["convert", "--help"])
    assert result.exit_code == 0, result.output
    assert "--prosody-method" in result.output
    assert "--prosody-strict" in result.output
    assert "--detect-emphasis" in result.output


def test_config_round_trips_prosody_types(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            [
                "config",
                "--set",
                "detect_emphasis",
                "true",
                "--set",
                "prosody_method",
                "psola",
                "--set",
                "prosody_fallback_methods",
                '["wsola","phase_vocoder"]',
                "--set",
                "prosody_strict",
                "1",
                "--set",
                "prosody_n_fft",
                "4096",
                "--set",
                "prosody_hop_length",
                "512",
                "--set",
                "prosody_rolloff",
                "0.8",
            ],
        )
        assert result.exit_code == 0, result.output
        loaded = load_config()

    assert loaded["detect_emphasis"] is True
    assert loaded["prosody_method"] == "psola"
    assert loaded["prosody_fallback_methods"] == ["wsola", "phase_vocoder"]
    assert loaded["prosody_strict"] is True
    assert loaded["prosody_n_fft"] == 4096
    assert loaded["prosody_hop_length"] == 512
    assert loaded["prosody_rolloff"] == 0.8


def test_config_cli_rejects_invalid_boolean(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app, ["config", "--set", "detect_emphasis", "maybe"]
        )
    assert result.exit_code == 2
    assert "Invalid value for detect_emphasis" in result.output
