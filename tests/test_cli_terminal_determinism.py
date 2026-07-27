"""CLI assertions that are independent of terminal rendering details."""

import re

from typer.testing import CliRunner

from ttsforge.cli import app


def _semantic_output(output: str) -> str:
    """Normalize ANSI and physical wrapping before semantic assertions."""
    without_ansi = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    return " ".join(without_ansi.split())


def _clear_forced_color(monkeypatch) -> None:
    for name in ("FORCE_COLOR", "CLICOLOR_FORCE", "CLICOLOR"):
        monkeypatch.delenv(name, raising=False)


def test_root_help_honors_no_color(monkeypatch) -> None:
    """Rich layout remains readable while NO_COLOR removes ANSI styling."""
    _clear_forced_color(monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.output
    semantic = _semantic_output(result.output)
    assert "ttsforge" in semantic.lower()
    assert "Options" in semantic
    assert "Commands" in semantic
    assert "convert" in semantic
    assert "phonemes" in semantic


def test_root_help_uses_rich_layout_under_forced_color(monkeypatch) -> None:
    """The public help path uses Typer's Rich formatter."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    semantic = _semantic_output(result.output)
    assert "Options" in semantic
    assert "Commands" in semantic
    assert "convert" in semantic


def test_root_help_hides_legacy_short_sentence_command(monkeypatch) -> None:
    _clear_forced_color(monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    semantic = _semantic_output(result.output)
    assert "config" in semantic
    assert "short-sentence-advanced-config" not in semantic


def test_config_help_exposes_short_sentence_command(monkeypatch) -> None:
    _clear_forced_color(monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")

    result = CliRunner().invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    semantic = _semantic_output(result.output)
    assert "short-sentence" in semantic
    assert "--set" in semantic


def test_convert_help_uses_semantic_fragments(monkeypatch) -> None:
    """Command help does not depend on Rich's exact line wrapping."""
    _clear_forced_color(monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")

    result = CliRunner().invoke(app, ["convert", "--help"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.output
    semantic = _semantic_output(result.output)
    for fragment in ("--voice", "--speed", "--resume", "--seed"):
        assert fragment in semantic


def test_version_is_plain_under_forced_color(monkeypatch) -> None:
    """Version output is stable even when a terminal requests color."""
    monkeypatch.setenv("FORCE_COLOR", "1")

    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.output
    assert result.output.startswith("ttsforge version ")
