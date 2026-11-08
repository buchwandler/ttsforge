from __future__ import annotations

from typer.testing import CliRunner

from ttsforge.cli import app


def test_removed_configuration_and_ssmd_commands_are_not_registered() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for obsolete_command in (
        "models",
        "config",
        "ssmd",
        "formats",
        "preview",
        "plan",
    ):
        assert f"{obsolete_command} " not in result.output
