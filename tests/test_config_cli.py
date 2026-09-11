"""Regression tests for the schema-2 configuration CLI."""

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


def test_config_set_persists_nested_override(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(app, ["config", "set", "tts.language", "de"])

    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert saved["tts"]["language"] == "de"


def test_config_set_is_atomic_when_value_is_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = {"schema_version": 2, "tts": {"language": "en-us"}}
    config_path.write_text(json.dumps(original), encoding="utf-8")
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app, ["config", "set", "runtime.provider", "potato"]
        )

    assert result.exit_code == 1
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_config_set_provider_persists_nested_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app, ["config", "set", "runtime.provider", "NnapiExecutionProvider"]
        )
    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["runtime"]["provider"] == "NnapiExecutionProvider"


def test_config_reset_restores_provider_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(app, ["config", "--reset"])
    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved == {"schema_version": 2}


def test_config_get_reads_dotted_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"schema_version": 2, "tts": {"language": "de"}}),
        encoding="utf-8",
    )
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(app, ["config", "get", "tts.language"])
    assert result.exit_code == 0
    assert result.output.strip() == '"de"'
