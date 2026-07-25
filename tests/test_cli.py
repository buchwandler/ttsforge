"""Tests for ttsforge.cli module."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ttsforge import DEFAULT_SAMPLE_TEXT
from ttsforge.cli import main
from ttsforge.cli.commands_conversion import (
    _format_short_sentence_hint,
    _format_short_sentence_note,
    _format_short_sentence_summary,
)


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


class TestMainCommand:
    """Tests for main CLI group."""

    def test_main_help(self, runner):
        """Should show help text."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ttsforge" in result.output.lower() or "epub" in result.output.lower()

    def test_main_version(self, runner):
        """Should show version."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0


class TestVoicesCommand:
    """Tests for voices command."""

    def test_voices_list(self, runner):
        """Should list available voices."""
        result = runner.invoke(main, ["voices"])
        assert result.exit_code == 0
        assert "af_bella" in result.output or "Voice" in result.output

    def test_voices_filter_by_language(self, runner):
        """Should filter voices by language."""
        result = runner.invoke(main, ["voices", "--language", "a"])
        assert result.exit_code == 0
        # American English voices should be shown
        assert "af_" in result.output or "am_" in result.output


class TestConfigCommand:
    """Tests for config command."""

    def test_config_show(self, runner):
        """Should show current configuration."""
        result = runner.invoke(main, ["config", "--show"])
        assert result.exit_code == 0
        assert "short_sentence" in result.output

    def test_config_reset(self, runner):
        """Should reset configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
                result = runner.invoke(main, ["config", "--reset"])
                assert result.exit_code == 0
                assert "reset" in result.output.lower()

    def test_config_rejects_invalid_short_sentence_mode(
        self,
        runner,
        tmp_path,
    ):
        """Should not save short-sentence configs with invalid modes."""
        config_path = tmp_path / "config.json"

        with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
            result = runner.invoke(
                main,
                ["config", "--set", "short_sentence", "mode=bogus,threshold=30"],
            )

        assert result.exit_code == 0
        assert "Invalid value for short_sentence" in result.output
        assert "Unknown short-sentence mode 'bogus'" in result.output
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["short_sentence"] != "mode=bogus,threshold=30"


class TestSampleCommand:
    """Tests for sample command."""

    def test_sample_help(self, runner):
        """Should show sample command help."""
        result = runner.invoke(main, ["sample", "--help"])
        assert result.exit_code == 0
        assert "sample" in result.output.lower()
        assert "--voice" in result.output
        assert "--speed" in result.output
        assert "--seed" in result.output

    def test_sample_default_text_defined(self):
        """DEFAULT_SAMPLE_TEXT should be defined."""
        assert isinstance(DEFAULT_SAMPLE_TEXT, str)
        assert len(DEFAULT_SAMPLE_TEXT) > 0

    def test_sample_displays_settings(self, runner):
        """Sample should display current settings (before TTS init fails)."""
        # This test doesn't mock TTSConverter, so it will fail during conversion
        # but we can verify that settings are displayed first
        with tempfile.TemporaryDirectory() as tmpdir:
            with runner.isolated_filesystem(temp_dir=tmpdir):
                result = runner.invoke(main, ["sample"])
                # Settings should be displayed even if conversion fails
                assert "Voice:" in result.output
                assert "Language:" in result.output
                assert "Speed:" in result.output


class TestConvertCommand:
    """Tests for convert command."""

    def test_convert_help(self, runner):
        """Should show convert command help."""
        result = runner.invoke(main, ["convert", "--help"])
        assert result.exit_code == 0
        assert "convert" in result.output.lower()
        assert "--voice" in result.output
        assert "--resume" in result.output or "resume" in result.output.lower()
        assert "--disable-short-sentence" in result.output
        assert "--enable-short-sentence" not in result.output
        assert "--seed" in result.output

    def test_read_help_has_disable_short_sentence_only(self, runner):
        """Read command should only expose the disable short-sentence flag."""
        result = runner.invoke(main, ["read", "--help"])
        assert result.exit_code == 0
        assert "--disable-short-sentence" in result.output
        assert "--enable-short-sentence" not in result.output
        assert "--seed" in result.output

    def test_convert_requires_input(self, runner):
        """Should require input file."""
        result = runner.invoke(main, ["convert"])
        assert result.exit_code != 0

    def test_convert_invalid_file(self, runner):
        """Should handle invalid file gracefully."""
        result = runner.invoke(main, ["convert", "nonexistent.epub"])
        assert result.exit_code != 0

    def test_convert_verbose_configures_debug_logging(
        self,
        runner,
        tmp_path,
        monkeypatch,
    ):
        """Verbose conversion should enable DEBUG root logging."""
        input_file = tmp_path / "book.epub"
        input_file.write_text("not an epub", encoding="utf-8")
        calls = []

        def fake_basic_config(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "ttsforge.cli.commands_conversion.logging.basicConfig",
            fake_basic_config,
        )

        result = runner.invoke(
            main,
            [
                "convert",
                str(input_file),
                "--verbose",
                "--short-sentence",
                "mode=bogus",
            ],
        )

        assert result.exit_code != 0
        assert calls == [
            {
                "level": logging.DEBUG,
                "format": "%(levelname)s [%(name)s] - %(message)s",
            }
        ]

    def test_convert_rejects_invalid_short_sentence_mode_before_summary(
        self,
        runner,
        tmp_path,
    ):
        """Invalid short-sentence mode should abort before the conversion summary."""
        input_file = tmp_path / "book.epub"
        input_file.write_text("not an epub", encoding="utf-8")

        result = runner.invoke(
            main,
            [
                "convert",
                str(input_file),
                "--short-sentence",
                "mode=bogus,threshold=30",
            ],
        )

        assert result.exit_code != 0
        assert "Invalid short-sentence config" in result.output
        assert "Unknown short-sentence mode 'bogus'" in result.output
        assert "Conversion Summary" not in result.output

    def test_short_sentence_summary_formats_resolved_default(self):
        """Summary should show the resolved config, not only the raw default."""
        summary = _format_short_sentence_summary(None, None, "a")

        assert summary.startswith("mode=randomized,threshold=30")
        assert "selection=auto" in summary

    def test_short_sentence_summary_formats_direct_phrase_config(self):
        """Summary should reflect direct CLI short-sentence config values."""
        summary = _format_short_sentence_summary(
            "mode=phrase,selection=auto,max-tries=4,threshold=30",
            None,
            "b",
        )

        assert summary.startswith("mode=phrase,threshold=30")
        assert "selection=auto" in summary
        assert "max-tries=4" in summary

    def test_short_sentence_note_reports_missing_language_phrases(self):
        """Summary note should explain configured fallback for missing language data."""
        note = _format_short_sentence_note(
            "mode=phrase,selection=auto,fallback-mode=none",
            None,
            "d",
        )

        assert note is not None
        assert "Missing phrases for language 'd'" in note
        assert "fallback-mode=none" in note

    def test_short_sentence_summary_formats_resolved_advanced_json(self, tmp_path):
        """Summary should reflect JSON-loaded settings and language fallback."""
        config_path = tmp_path / "short_sentence.json"
        config_path.write_text(
            (
                '{"mode":"randomized","threshold":7,"selection":"end",'
                '"max-tries":2,"fallback-mode":"none",'
                '"natural-phrases":{"b":["Before {segment} after"]},'
                '"end-phrases":{"b":["End {segment}"]},'
                '"frame-duration-ms":8,"energy-threshold":0.12,'
                '"silence-threshold":0.002,"min-silence-seconds":0.04}'
            ),
            encoding="utf-8",
        )

        summary = _format_short_sentence_summary(f"config={config_path}", None, "b")

        assert summary == (
            "mode=randomized,threshold=7,selection=end,max-tries=2"
        )

    def test_short_sentence_summary_disable_override_wins(self):
        """Disable override should be represented as an accepted short-sentence value."""
        summary = _format_short_sentence_summary(
            "mode=randomized,threshold=7",
            False,
            "a",
        )

        assert summary == "off"

    def test_short_sentence_summary_caps_threshold(self):
        """Summary should show the clamped threshold that will be used."""
        summary = _format_short_sentence_summary(
            "mode=phrase,threshold=999,max-tries=10",
            None,
            "b",
        )

        assert summary.startswith("mode=phrase,threshold=300")

    def test_short_sentence_hint_shows_for_english_only(self):
        """Hint should be limited to English short-sentence runs."""
        hint = _format_short_sentence_hint("mode=phrase,threshold=40", None, "b")

        assert hint is not None
        assert "--short-sentence 'threshold=40,max-tries=10'" in hint
        assert (
            _format_short_sentence_hint("mode=phrase,threshold=40", None, "d")
            is None
        )
        assert _format_short_sentence_hint("mode=off", None, "a") is None


class TestListCommand:
    """Tests for list command."""

    def test_list_help(self, runner):
        """Should show list command help."""
        result = runner.invoke(main, ["list", "--help"])
        assert result.exit_code == 0

    def test_list_requires_input(self, runner):
        """Should require input file."""
        result = runner.invoke(main, ["list"])
        assert result.exit_code != 0


class TestInfoCommand:
    """Tests for info command."""

    def test_info_help(self, runner):
        """Should show info command help."""
        result = runner.invoke(main, ["info", "--help"])
        assert result.exit_code == 0

    def test_info_requires_input(self, runner):
        """Should require input file."""
        result = runner.invoke(main, ["info"])
        assert result.exit_code != 0


class TestCliOptions:
    """Tests for CLI option validation."""

    def test_invalid_voice_rejected(self, runner):
        """Invalid voice should be rejected."""
        result = runner.invoke(main, ["sample", "--voice", "invalid_voice"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_invalid_language_rejected(self, runner):
        """Invalid language should be rejected."""
        result = runner.invoke(main, ["sample", "--language", "x"])
        assert result.exit_code != 0

    def test_invalid_format_rejected(self, runner):
        """Invalid format should be rejected."""
        result = runner.invoke(main, ["sample", "--format", "invalid"])
        assert result.exit_code != 0

    def test_invalid_split_mode_rejected(self, runner):
        """Invalid split mode should be rejected."""
        result = runner.invoke(main, ["sample", "--split-mode", "invalid"])
        assert result.exit_code != 0
