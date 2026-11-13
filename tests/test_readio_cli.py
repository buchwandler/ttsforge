from __future__ import annotations

from click import unstyle
from typer.testing import CliRunner

from ttsforge.cli import app


def test_convert_help_documents_current_audiobook_controls() -> None:
    result = CliRunner().invoke(
        app, ["convert", "--help"], color=False, env={"FORCE_COLOR": ""}
    )

    output = unstyle(result.output)
    assert result.exit_code == 0, output
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
        assert option in output
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
