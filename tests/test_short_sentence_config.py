import json
from pathlib import Path

from click.testing import CliRunner
from pykokoro.short_sentence_handler import RandomizedPhraseResolveMode

from ttsforge.cli import main
from ttsforge.short_sentence_config import (
    default_advanced_short_sentence_data,
    resolve_short_sentence_config,
    short_sentence_fallback_note,
    validate_short_sentence_config,
)


def test_resolve_default_uses_randomized_phrase_mode() -> None:
    config = resolve_short_sentence_config(None)

    assert config is not None
    assert config.enabled is True
    assert config.phrase_fallback_tries == 5
    assert config.min_phoneme_length == 30
    assert config.resolve_mode == "randomized-phrase"


def test_resolve_direct_phrase_config_uses_phrase_defaults() -> None:
    config = resolve_short_sentence_config(
        "mode=phrase,selection=auto,max-tries=4,threshold=30",
        language_code="b",
    )
    defaults = default_advanced_short_sentence_data()

    assert config is not None
    assert config.enabled is True
    assert config.resolve_mode == "phrase"
    assert config.phrase_fallback_tries == 4
    assert config.min_phoneme_length == 30
    phrase = config.resolve_modes["phrase"]
    assert phrase.phrase_selection == "auto"
    assert phrase.neutral_phrase == defaults["natural-phrase"]["b"]
    assert phrase.end_phrase == defaults["end-phrase"]["b"]


def test_short_sentence_fallback_note_uses_configured_wrap_fallback() -> None:
    note = short_sentence_fallback_note(
        "mode=phrase,selection=auto,fallback-mode=wrap",
        language_code="d",
    )

    assert note is not None
    assert "Missing phrases for language 'd'" in note
    assert "natural-phrase" in note
    assert "end-phrase" in note
    assert "fallback-mode=wrap" in note


def test_short_sentence_fallback_note_uses_configured_none_fallback() -> None:
    note = short_sentence_fallback_note(
        "mode=randomized,selection=end,fallback-mode=none",
        language_code="d",
    )

    assert note is not None
    assert "Missing phrases for language 'd'" in note
    assert "end-phrases" in note
    assert "natural-phrases" not in note
    assert "fallback-mode=none" in note


def test_short_sentence_fallback_note_omits_when_language_has_defaults() -> None:
    note = short_sentence_fallback_note(
        "mode=phrase,selection=auto,fallback-mode=wrap",
        language_code="b",
    )

    assert note is None


def test_resolve_warns_for_unrecognized_options() -> None:
    warnings: list[str] = []

    config = resolve_short_sentence_config(
        "mode=randomized,unknown=value",
        warn=warnings.append,
    )

    assert config is not None
    assert any("Unrecognized short-sentence option 'unknown'" in w for w in warnings)


def test_validate_rejects_unknown_mode() -> None:
    errors = validate_short_sentence_config("mode=bogus,threshold=30")

    assert errors
    assert "Unknown short-sentence mode 'bogus'" in errors[0]


def test_resolve_loads_json_config_with_custom_language_randomized_phrases(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "short_sentence.json"
    config_path.write_text(
        json.dumps(
            {
                "mode": "randomized",
                "threshold": 7,
                "selection": "natural",
                "max-tries": 2,
                "natural-phrases": {
                    "b": ["Custom natural {segment}"],
                },
                "end-phrases": {
                    "b": ["Custom end {segment}"],
                },
            }
        ),
        encoding="utf-8",
    )

    config = resolve_short_sentence_config(f"config={config_path}", language_code="b")

    assert config is not None
    assert config.phrase_fallback_tries == 2
    assert config.min_phoneme_length == 7
    randomized = config.resolve_modes["randomized-phrase"]
    assert isinstance(randomized, RandomizedPhraseResolveMode)
    assert randomized.phrase_selection == "neutral"
    assert randomized.neutral_phrases == ["Custom natural {segment}"]
    assert randomized.end_phrases == ["Custom end {segment}"]


def test_resolve_uses_fallback_mode_when_language_has_no_phrases(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "short_sentence.json"
    config_path.write_text(
        json.dumps(
            {
                "mode": "randomized",
                "fallback-mode": "none",
                "natural-phrases": {"a": ["Custom natural {segment}"]},
                "end-phrases": {"a": ["Custom end {segment}"]},
            }
        ),
        encoding="utf-8",
    )

    config = resolve_short_sentence_config(f"config={config_path}", language_code="d")

    assert config is not None
    assert config.resolve_mode is False


def test_resolve_relative_json_config_from_user_config_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    main_config_path = tmp_path / "config.json"
    linked_path = tmp_path / "short_sentence.json"
    linked_path.write_text(
        json.dumps(
            {
                "mode": "phrase",
                "threshold": 6,
                "natural-phrase": {"a": "Custom natural {segment}"},
                "end-phrase": {"a": "Custom end {segment}"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: main_config_path,
    )

    config = resolve_short_sentence_config("config=short_sentence.json")

    assert config is not None
    assert config.resolve_mode == "phrase"
    assert config.min_phoneme_length == 6


def test_advanced_default_json_includes_direct_and_phrase_options() -> None:
    data = default_advanced_short_sentence_data()

    for key in ("mode", "threshold", "selection", "max-tries"):
        assert key in data
    assert data["mode"] == "randomized"
    assert data["threshold"] == 30
    assert data["selection"] == "auto"
    assert data["max-tries"] == 5
    assert data["fallback-mode"] == "wrap"
    assert data["natural-phrases"]["a"]
    assert data["natural-phrases"]["b"]
    assert data["end-phrases"]["a"]
    assert data["end-phrases"]["b"]


def test_short_sentence_advanced_config_command_writes_and_links(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr("ttsforge.utils.get_user_config_path", lambda: config_path)

    result = CliRunner().invoke(main, ["short-sentence-advanced-config", "init"])

    assert result.exit_code == 0
    advanced_path = tmp_path / "short_sentence_advanced.json"
    assert "short_sentence_advanced.json" in result.output
    assert advanced_path.exists()
    saved_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_config["short_sentence"] == f"config={advanced_path}"


def test_short_sentence_advanced_config_command_shows_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    advanced_path = tmp_path / "short_sentence_advanced.json"
    advanced_path.write_text(
        json.dumps({"mode": "phrase", "threshold": 12}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr("ttsforge.utils.get_user_config_path", lambda: config_path)

    result = CliRunner().invoke(main, ["short-sentence-advanced-config", "show"])

    assert result.exit_code == 0
    assert "short_sentence_advanced.json" in result.output
    assert '"mode": "phrase"' in result.output
    assert '"threshold": 12' in result.output


def test_short_sentence_advanced_config_command_reset_restores_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    advanced_path = tmp_path / "short_sentence_advanced.json"
    advanced_path.write_text(
        json.dumps({"mode": "phrase", "threshold": 12}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr("ttsforge.utils.get_user_config_path", lambda: config_path)

    result = CliRunner().invoke(main, ["short-sentence-advanced-config", "reset"])

    assert result.exit_code == 0
    assert "Reset advanced short-sentence config to defaults" in result.output
    saved_advanced_config = json.loads(advanced_path.read_text(encoding="utf-8"))
    assert saved_advanced_config == default_advanced_short_sentence_data()
    saved_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_config["short_sentence"] == f"config={advanced_path}"


def test_short_sentence_advanced_config_command_without_action_shows_help(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr("ttsforge.utils.get_user_config_path", lambda: config_path)

    result = CliRunner().invoke(main, ["short-sentence-advanced-config"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "[show|init|reset]" in result.output
    assert "ACTION is 'init', 'show', or 'reset'" in result.output
    assert not (tmp_path / "short_sentence_advanced.json").exists()


def test_short_sentence_advanced_config_help_shows_location(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "ttsforge.short_sentence_config.get_user_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr("ttsforge.utils.get_user_config_path", lambda: config_path)

    result = CliRunner().invoke(main, ["short-sentence-advanced-config", "--help"])

    assert result.exit_code == 0
    assert tmp_path.name in result.output
    assert "short_sentence_advanced.json" in result.output
