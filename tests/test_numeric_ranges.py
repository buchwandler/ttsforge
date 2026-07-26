"""CLI and library numeric-range contract tests."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ttsforge.cli import app
from ttsforge.conversion import ConversionOptions
from ttsforge.phoneme_conversion import PhonemeConversionOptions


@pytest.mark.parametrize("speed", [0.5, 1.0, 2.0])
def test_conversion_speed_boundaries_are_accepted(speed: float) -> None:
    assert ConversionOptions(speed=speed).speed == speed


@pytest.mark.parametrize("speed", [0.49, 2.01])
def test_conversion_speed_out_of_range_is_rejected(speed: float) -> None:
    with pytest.raises(ValueError, match="speed"):
        ConversionOptions(speed=speed)


def test_phoneme_speed_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="speed"):
        PhonemeConversionOptions(speed=2.01)


def test_cli_rejects_out_of_range_speed_and_confidence(tmp_path: Path) -> None:
    input_file = tmp_path / "book.txt"
    input_file.write_text("Chapter 1\nText", encoding="utf-8")
    runner = CliRunner()
    speed_result = runner.invoke(app, ["convert", "--speed", "2.1", str(input_file)])
    confidence_result = runner.invoke(
        app,
        [
            "convert",
            "--mixed-language-confidence",
            "1.1",
            str(input_file),
        ],
    )
    assert speed_result.exit_code != 0
    assert "Invalid value" in speed_result.output
    assert confidence_result.exit_code != 0
    assert "Invalid value" in confidence_result.output
