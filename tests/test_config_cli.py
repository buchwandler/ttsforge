"""Regression tests for the legacy repeated config option grammar."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ttsforge.cli import app


def test_config_set_accepts_repeated_pairs_and_negative_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        result = CliRunner().invoke(
            app,
            [
                "config",
                "--set",
                "pause_variance",
                "-0.1",
                "--set",
                "default_language",
                "b",
            ],
        )

    assert result.exit_code == 0, result.output
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["pause_variance"] == -0.1
    assert saved["default_language"] == "b"


def test_config_set_requires_exactly_two_values() -> None:
    result = CliRunner().invoke(app, ["config", "--set", "pause_variance"])
    assert result.exit_code != 0
    assert "requires 2 arguments" in result.output


def test_config_rejects_unknown_options() -> None:
    result = CliRunner().invoke(app, ["config", "--not-an-option"])
    assert result.exit_code != 0
    assert "No such option" in result.output
