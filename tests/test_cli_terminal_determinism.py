"""CLI assertions that are independent of terminal rendering details."""

import re

from click.testing import CliRunner

from ttsforge.cli import main


def _semantic_output(output: str) -> str:
    """Normalize ANSI and physical wrapping before semantic assertions."""
    without_ansi = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    return " ".join(without_ansi.split())


def test_root_help_is_semantic_and_color_free(monkeypatch) -> None:
    """Root help remains inspectable under the review terminal settings."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")

    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.output
    semantic = _semantic_output(result.output)
    assert "ttsforge" in semantic.lower()
    assert "convert" in semantic
    assert "phonemes" in semantic


def test_convert_help_uses_semantic_fragments(monkeypatch) -> None:
    """Command help does not depend on Rich's exact line wrapping."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "160")

    result = CliRunner().invoke(main, ["convert", "--help"])

    assert result.exit_code == 0
    semantic = _semantic_output(result.output)
    for fragment in ("--voice", "--speed", "--resume", "--seed"):
        assert fragment in semantic
