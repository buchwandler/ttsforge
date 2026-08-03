"""CLI contract tests for the independent conversion-unit option."""

from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from ttsforge.cli import app, commands_conversion
from ttsforge.conversion import ConversionOptions
from ttsforge.render_units import validate_conversion_unit


def test_conversion_unit_is_distinct_from_split_mode():
    options = ConversionOptions(split_mode="paragraph", conversion_unit="chapter")
    assert options.split_mode == "paragraph"
    assert options.conversion_unit == "chapter"


def test_invalid_conversion_unit_is_rejected():
    try:
        validate_conversion_unit("sentence")
    except ValueError as exc:
        assert "chapter" in str(exc) and "paragraph" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid conversion unit accepted")


def test_convert_help_exposes_optional_conversion_unit():
    result = CliRunner().invoke(app, ["convert", "--help"], terminal_width=240)
    assert result.exit_code == 0
    assert "--conversion-unit" in result.output
    assert "chapter" in result.output
    assert "paragraph" in result.output


def test_paragraph_summary_mentions_visible_output(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(
        commands_conversion,
        "console",
        Console(file=stream, width=240, color_system=None, highlight=False),
    )
    commands_conversion._show_conversion_summary(
        epub_file=Path("book.epub"),
        output=Path("Book.m4b"),
        output_format="m4b",
        voice="af_heart",
        language="a",
        speed=1.0,
        onnx_provider="cpu",
        model_source="huggingface",
        model_variant="v1.0",
        model_quality="fp32",
        num_chapters=2,
        title="Book",
        author="Author",
        conversion_unit="paragraph",
        paragraphs_dir=Path("Book_paragraphs"),
    )
    output = stream.getvalue()
    assert "Paragraph WAV per paragraph" in output
    assert "Book_paragraphs" in output
    assert "Fixed-width global sequence" in output
