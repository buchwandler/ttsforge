"""Regression tests for the legacy repeated config option grammar."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ttsforge.cli import app
from ttsforge.constants import DEFAULT_CONFIG
from ttsforge.utils import parse_config_cli_value, validate_config_value


def test_spacy_config_preserves_auto_and_boolean_values() -> None:
    assert DEFAULT_CONFIG["use_spacy"] is None
    assert parse_config_cli_value("use_spacy", "auto", None) is None
    assert parse_config_cli_value("use_spacy", "true", None) is True
    assert parse_config_cli_value("use_spacy", "false", None) is False
    validate_config_value("use_spacy", None)
    validate_config_value("use_spacy", True)


def test_config_set_accepts_repeated_pairs_and_dash_prefixed_values(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            [
                "config",
                "--set",
                "default_title",
                "-draft",
                "--set",
                "default_language",
                "b",
            ],
        )

    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["default_title"] == "-draft"
    assert saved["default_language"] == "b"


def test_config_set_rejects_negative_pause_variance(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            ["config", "--set", "pause_variance", "-0.1"],
        )

    assert result.exit_code == 2
    assert "pause_variance" in result.output
    assert "must be non-negative" in result.output
    assert not config_path.exists()


def test_config_set_is_atomic_when_one_repeated_pair_is_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = {"default_language": "a"}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            [
                "config",
                "--set",
                "default_language",
                "b",
                "--set",
                "pause_variance",
                "-0.1",
            ],
        )

    assert result.exit_code == 2
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_config_set_requires_exactly_two_values() -> None:
    result = CliRunner().invoke(app, ["config", "--set", "pause_variance"])
    assert result.exit_code != 0
    assert "requires 2 arguments" in result.output


def test_config_rejects_unknown_options() -> None:
    result = CliRunner().invoke(app, ["config", "--not-an-option"])
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_config_options_cannot_be_combined_with_subcommand() -> None:
    result = CliRunner().invoke(
        app,
        ["config", "--show", "short-sentence", "show"],
    )

    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_config_set_provider_persists_alias_and_full_name(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            ["config", "--set", "onnx_provider", "NnapiExecutionProvider"],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(config_path.read_text(encoding="utf-8"))["onnx_provider"] == (
        "NnapiExecutionProvider"
    )


def test_config_set_invalid_provider_is_atomic(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = {"onnx_provider": "cpu"}
    config_path.write_text(json.dumps(original), encoding="utf-8")
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            ["config", "--set", "onnx_provider", "potato"],
        )
    assert result.exit_code == 2
    assert "Invalid value for onnx_provider" in result.output
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_config_reset_restores_provider_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(app, ["config", "--reset"])
    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["onnx_provider"] == "cpu"
    assert saved["use_gpu"] is False
