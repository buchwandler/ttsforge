from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from ttsforge.cli import app, commands_conversion
from ttsforge.constants import DEFAULT_CONFIG
from ttsforge.conversion import ConversionOptions, TTSConverter
from ttsforge.ssmd_support import SSMDPolicy, build_pykokoro_ssmd_config


def test_default_config_and_policy_use_plain_emphasis() -> None:
    assert DEFAULT_CONFIG["ssmd_emphasis_mode"] == "plain"
    assert SSMDPolicy().emphasis_mode == "plain"
    assert build_pykokoro_ssmd_config(SSMDPolicy()).emphasis_mode == "plain"


def test_enable_flag_explicitly_opts_into_approximation() -> None:
    assert (
        commands_conversion._resolve_ssmd_emphasis_mode(
            configured="plain",
            explicit=None,
            enable_approximation=True,
        )
        == "approximate"
    )


def test_explicit_mode_overrides_persistent_config() -> None:
    assert (
        commands_conversion._resolve_ssmd_emphasis_mode(
            configured="approximate",
            explicit="plain",
            enable_approximation=False,
        )
        == "plain"
    )


def test_persisted_mode_is_used_when_cli_mode_is_omitted() -> None:
    assert (
        commands_conversion._resolve_ssmd_emphasis_mode(
            configured="approximate",
            explicit=None,
            enable_approximation=False,
        )
        == "approximate"
    )


def test_missing_persisted_mode_falls_back_to_plain() -> None:
    assert (
        commands_conversion._resolve_ssmd_emphasis_mode(
            configured=None,
            explicit=None,
            enable_approximation=False,
        )
        == "plain"
    )


def test_enable_flag_conflicts_with_explicit_mode() -> None:
    with pytest.raises(typer.BadParameter, match="cannot be combined"):
        commands_conversion._resolve_ssmd_emphasis_mode(
            configured="plain",
            explicit="warn",
            enable_approximation=True,
        )


def test_convert_wrapper_preserves_omitted_and_explicit_ssmd_voice_values(
    monkeypatch, tmp_path: Path
) -> None:
    captured: list[dict[str, object]] = []

    def fake_convert(**kwargs: object) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(commands_conversion, "convert", fake_convert)
    source = tmp_path / "book.epub"
    source.write_bytes(b"placeholder")
    runner = CliRunner()

    omitted = runner.invoke(app, ["convert", str(source)])
    assert omitted.exit_code == 0, omitted.output
    assert captured[-1]["ssmd_voice"] is None

    explicit = runner.invoke(
        app,
        [
            "convert",
            str(source),
            "--ssmd-voice",
            "narrator=af_heart",
            "--ssmd-voice",
            "dialogue=af_bella",
        ],
    )
    assert explicit.exit_code == 0, explicit.output
    assert captured[-1]["ssmd_voice"] == ["narrator=af_heart", "dialogue=af_bella"]


def test_schema7_ssmd_resume_uses_saved_policy_and_keeps_pause_overrides_none() -> None:
    saved = (
        TTSConverter(
            ConversionOptions(
                pause_sentence=0.5,
                pause_paragraph=0.9,
                ssmd_policy=SSMDPolicy(emphasis_mode="approximate"),
            )
        )
        ._generation_identity()
        .payload
    )

    resolved = commands_conversion._resolve_ssmd_policy(
        config={"ssmd_emphasis_mode": "plain"},
        saved_identity=saved,
        ssmd_header=None,
        ssmd_unknown_header=None,
        ssmd_missing_voice=None,
        ssmd_emphasis=None,
        enable_ssmd_emphasis=False,
        ssmd_profile_validation=None,
        ssmd_fail_on_warning=None,
        ssmd_voice=None,
        ssmd_bindings={},
        ssmd_pause_defaults=None,
        explicit_pause_sentence=None,
        explicit_pause_paragraph=None,
        pause_voice_change=None,
        ssmd_audio_root=None,
        ssmd_remote_audio=None,
        ssmd_audio_max_bytes=None,
        ssmd_audio_max_duration=None,
    )

    assert resolved.emphasis_mode == "approximate"
    assert resolved.pause_overrides is None


def test_schema7_same_explicit_emphasis_does_not_create_pause_override() -> None:
    saved = (
        TTSConverter(
            ConversionOptions(ssmd_policy=SSMDPolicy(emphasis_mode="approximate"))
        )
        ._generation_identity()
        .payload
    )

    resolved = commands_conversion._resolve_ssmd_policy(
        config={"ssmd_emphasis_mode": "plain"},
        saved_identity=saved,
        ssmd_header=None,
        ssmd_unknown_header=None,
        ssmd_missing_voice=None,
        ssmd_emphasis="approximate",
        enable_ssmd_emphasis=False,
        ssmd_profile_validation=None,
        ssmd_fail_on_warning=None,
        ssmd_voice=None,
        ssmd_bindings={},
        ssmd_pause_defaults=None,
        explicit_pause_sentence=None,
        explicit_pause_paragraph=None,
        pause_voice_change=None,
        ssmd_audio_root=None,
        ssmd_remote_audio=None,
        ssmd_audio_max_bytes=None,
        ssmd_audio_max_duration=None,
    )

    assert resolved.emphasis_mode == "approximate"
    assert resolved.pause_overrides is None


def test_convert_help_lists_all_emphasis_controls() -> None:
    result = CliRunner().invoke(app, ["convert", "--help"], terminal_width=240)

    assert result.exit_code == 0
    assert "plain" in result.output
    assert "approximate" in result.output
    assert "warn" in result.output
    assert "error" in result.output
    convert_command = get_command(app).commands["convert"]
    assert any(
        "--enable-ssmd-emphasis" in option.opts
        for option in convert_command.params
        if hasattr(option, "opts")
    )


def test_conversion_summary_shows_detection_and_rendering_mode(monkeypatch) -> None:
    stream = StringIO()
    monkeypatch.setattr(
        commands_conversion,
        "console",
        Console(file=stream, width=240, color_system=None, highlight=False),
    )

    commands_conversion._show_conversion_summary(
        epub_file=Path("book.epub"),
        output=Path("book.m4b"),
        output_format="m4b",
        voice="af_heart",
        language="a",
        speed=1.0,
        onnx_provider="cpu",
        model_source="huggingface",
        model_variant="v1.0",
        model_quality="fp32",
        num_chapters=10,
        title="Book",
        author="Author",
        detect_emphasis=False,
        ssmd_emphasis_mode="plain",
    )

    output = stream.getvalue()
    assert "EPUB Content Extraction" in output
    assert "Markdown" in output
    assert "EPUB Emphasis Markup" in output
    assert "Unwrapped" in output
    assert "SSMD Emphasis" in output
    assert "Plain (emphasis unchanged)" in output


def test_emphasis_mode_change_invalidates_resume_fingerprint() -> None:
    plain = TTSConverter(
        ConversionOptions(ssmd_policy=SSMDPolicy(emphasis_mode="plain"))
    )
    approximate = TTSConverter(
        ConversionOptions(ssmd_policy=SSMDPolicy(emphasis_mode="approximate"))
    )

    assert plain._generation_fingerprint() != approximate._generation_fingerprint()
