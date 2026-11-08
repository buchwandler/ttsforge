from __future__ import annotations

from typer.testing import CliRunner

from ttsforge.cli import app


def test_convert_help_documents_current_audiobook_controls() -> None:
    result = CliRunner().invoke(app, ["convert", "--help"])

    assert result.exit_code == 0, result.output
    for option in (
        "--chapters",
        "--project",
        "--output",
        "--engine",
        "--target",
        "--voice",
        "--engine-option",
        "--replace-output",
        "--rebuild-from",
        "--fresh",
        "--non-interactive",
        "--json",
    ):
        assert option in result.output
    for obsolete_option in (
        "--format",
        "--model",
        "--model-source",
        "--quality",
        "--reconfigure",
        "--unit",
        "--force",
    ):
        assert obsolete_option not in result.output
