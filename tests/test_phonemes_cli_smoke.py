"""Smoke coverage for the phoneme CLI adapter."""

from unittest.mock import patch

from typer.testing import CliRunner

from ttsforge.cli import app
from ttsforge.phonemes import PhonemeBook, PhonemeChapter, PhonemeSegment


def test_phonemes_preview_reports_semantic_result() -> None:
    result = CliRunner().invoke(app, ["phonemes", "preview", "Hello"])
    assert result.exit_code == 0
    assert "Language:" in result.output
    assert "Phonemes:" in result.output


def test_phonemes_info_reports_invalid_json(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("not json", encoding="utf-8")
    result = CliRunner().invoke(app, ["phonemes", "info", str(path)])
    assert result.exit_code != 0
    assert "Error loading phoneme file" in result.output


def test_phonemes_convert_reports_invalid_file(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(app, ["phonemes", "convert", str(path)])
    assert result.exit_code != 0
    assert "Error loading phoneme file" in result.output or "Error" in result.output


def test_phonemes_convert_rejects_invalid_persisted_pause_variance_before_prompt(
    tmp_path,
) -> None:
    book = PhonemeBook(
        title="Demo",
        chapters=[
            PhonemeChapter(
                title="One",
                segments=[PhonemeSegment("Hello", "həlˈO", [1, 2])],
            )
        ],
    )
    path = tmp_path / "book.json"
    book.save(path)

    with patch(
        "ttsforge.cli.commands_phonemes.load_config",
        return_value={"pause_variance": -0.1},
    ):
        result = CliRunner().invoke(app, ["phonemes", "convert", str(path)])

    assert result.exit_code == 2
    assert "pause_variance" in result.output
    assert "Proceed with conversion?" not in result.output
    assert "Traceback" not in result.output


def test_phonemes_info_reports_metadata_and_stats(tmp_path) -> None:
    book = PhonemeBook(
        title="Demo",
        chapters=[
            PhonemeChapter(
                title="One",
                segments=[PhonemeSegment("Hello", "həlˈO", [1, 2])],
            )
        ],
        metadata={"source": "test"},
    )
    path = tmp_path / "book.json"
    book.save(path)
    result = CliRunner().invoke(app, ["phonemes", "info", str(path), "--stats"])
    assert result.exit_code == 0
    assert "Demo" in result.output
    assert "Segment Statistics" in result.output


def test_phonemes_export_reports_reader_errors(tmp_path) -> None:
    path = tmp_path / "not-an-epub.txt"
    path.write_text("plain text", encoding="utf-8")
    result = CliRunner().invoke(app, ["phonemes", "export", str(path)])
    assert result.exit_code == 0
    assert "Exported" in result.output
