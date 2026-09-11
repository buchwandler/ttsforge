"""Tests for the v0.4 short-sentence configuration contract."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ttsforge.cli import app
from ttsforge.pykokoro_adapter import RandomizedPhraseResolveMode
from ttsforge.short_sentence_config import (
    default_advanced_short_sentence_data,
    resolve_short_sentence_config,
    short_sentence_fallback_note,
)


def test_resolve_direct_phrase_config_uses_canonical_language_defaults() -> None:
    config = resolve_short_sentence_config(
        "mode=phrase,selection=auto,max-tries=4,threshold=30",
        language_code="en-gb",
    )
    defaults = default_advanced_short_sentence_data()

    assert config is not None
    assert config.enabled is True
    assert config.resolve_mode == "phrase"
    assert config.phrase_fallback_tries == 4
    assert config.min_phoneme_length == 30
    assert config.resolve_modes["phrase"].phrase_selection == "auto"
    assert config.resolve_modes["phrase"].neutral_phrase == (
        defaults["natural-phrase"]["en-gb"]
    )


def test_short_sentence_fallback_note_reports_canonical_language() -> None:
    note = short_sentence_fallback_note(
        "mode=phrase,selection=auto,fallback-mode=wrap", language_code="de"
    )
    assert note is not None
    assert "Missing phrases for language 'de'" in note


def test_resolve_loads_json_config_with_custom_language_phrases(tmp_path: Path) -> None:
    config_path = tmp_path / "short_sentence.json"
    config_path.write_text(
        json.dumps(
            {
                "mode": "randomized",
                "threshold": 7,
                "selection": "natural",
                "max-tries": 2,
                "natural-phrases": {"en-gb": ["Custom natural {segment}"]},
                "end-phrases": {"en-gb": ["Custom end {segment}"]},
            }
        ),
        encoding="utf-8",
    )

    config = resolve_short_sentence_config(
        f"config={config_path}", language_code="en-gb"
    )
    assert config is not None
    randomized = config.resolve_modes["randomized-phrase"]
    assert isinstance(randomized, RandomizedPhraseResolveMode)
    assert randomized.neutral_phrases == ["Custom natural {segment}"]
    assert randomized.end_phrases == ["Custom end {segment}"]


def test_advanced_default_json_uses_canonical_languages() -> None:
    data = default_advanced_short_sentence_data()
    assert data["natural-phrases"]["en-us"]
    assert data["natural-phrases"]["en-gb"]
    assert "a" not in data["natural-phrases"]


def test_short_sentence_config_command_initializes_nested_override(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    with (
        patch(
            "ttsforge.short_sentence_config.get_user_config_path",
            return_value=config_path,
        ),
        patch("ttsforge.utils.get_user_config_path", return_value=config_path),
    ):
        result = CliRunner().invoke(app, ["config", "short-sentence", "init"])

    assert result.exit_code == 0, result.output
    advanced_path = tmp_path / "short_sentence_advanced.json"
    assert advanced_path.exists()
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["conversion"]["short_sentence"] == (
        f"config={advanced_path}"
    )
