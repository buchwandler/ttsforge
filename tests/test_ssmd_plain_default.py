"""Tests for the v0.4 SSMD emphasis surface."""

from __future__ import annotations

from typer.testing import CliRunner

from ttsforge.cli import app


def test_convert_help_exposes_emphasis_level_without_legacy_switch() -> None:
    result = CliRunner().invoke(app, ["convert", "--help"], terminal_width=240)
    assert result.exit_code == 0
    assert "--emphasis-level" in result.output
    assert "--enable-ssmd-emphasis" not in result.output


def test_removed_emphasis_switch_is_rejected() -> None:
    result = CliRunner().invoke(app, ["convert", "book.epub", "--enable-ssmd-emphasis"])
    assert result.exit_code == 2
    assert "No such option" in result.output


def test_removed_short_sentence_advanced_command_is_rejected() -> None:
    result = CliRunner().invoke(app, ["short-sentence-advanced-config", "init"])
    assert result.exit_code == 2
    assert "No such command" in result.output
