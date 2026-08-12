"""Regression tests for source-aware model asset downloads."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from ttsforge.cli import commands_utility


def _context() -> SimpleNamespace:
    return SimpleNamespace(obj={})


def _assets(tmp_path: Path, *, config: Path | None):
    return SimpleNamespace(
        config=config,
        model=tmp_path / "pykokoro-model-name.onnx",
        voices=tmp_path / "pykokoro-voices-name.bin",
    )


def test_github_v1_download_skips_config_and_uses_pykokoro_paths(
    monkeypatch, tmp_path, capsys
) -> None:
    assets = _assets(tmp_path, config=None)
    calls: list[str] = []

    monkeypatch.setattr(
        commands_utility,
        "load_config",
        lambda: {"model_source": "github", "model_variant": "v1.0"},
    )
    monkeypatch.setattr(
        commands_utility, "get_model_asset_paths", lambda **kwargs: assets
    )

    def fail_config(*args, **kwargs):
        pytest.fail(f"config helper called: {args} {kwargs}")

    monkeypatch.setattr(commands_utility, "is_config_downloaded", fail_config)
    monkeypatch.setattr(commands_utility, "download_config", fail_config)

    def download_model(**kwargs):
        calls.append("model")
        assets.model.write_bytes(b"model")

    def download_voices(**kwargs):
        calls.append("voices")
        assets.voices.write_bytes(b"voices")

    monkeypatch.setattr(commands_utility, "download_model_github", download_model)
    monkeypatch.setattr(commands_utility, "download_voices_github", download_voices)

    commands_utility.download(_context(), force=False, quality="fp32")

    output = capsys.readouterr().out
    assert calls == ["model", "voices"]
    assert "pykokoro-model-name.onnx" in output
    assert "pykokoro-voices-name.bin" in output
    assert "embedded / not required" in output
    assert "config.json: Failed" not in output


def test_config_required_download_still_runs_config_logic(
    monkeypatch, tmp_path
) -> None:
    config = tmp_path / "config.json"
    assets = _assets(tmp_path, config=config)
    calls: list[str] = []

    monkeypatch.setattr(commands_utility, "load_config", lambda: {})
    monkeypatch.setattr(
        commands_utility, "get_model_asset_paths", lambda **kwargs: assets
    )
    monkeypatch.setattr(
        commands_utility,
        "is_config_downloaded",
        lambda **kwargs: False,
    )

    def download_config(**kwargs):
        calls.append("config")
        config.write_bytes(b"config")

    def download_model(**kwargs):
        calls.append("model")
        assets.model.write_bytes(b"model")

    def download_voices(**kwargs):
        calls.append("voices")
        assets.voices.write_bytes(b"voices")

    monkeypatch.setattr(commands_utility, "download_config", download_config)
    monkeypatch.setattr(commands_utility, "download_model", download_model)
    monkeypatch.setattr(commands_utility, "download_all_voices", download_voices)

    commands_utility.download(_context(), force=False, quality="fp32")

    assert calls == ["config", "model", "voices"]


def test_complete_github_set_without_config_skips_all_downloaders(
    monkeypatch, tmp_path, capsys
) -> None:
    assets = _assets(tmp_path, config=None)
    assets.model.write_bytes(b"model")
    assets.voices.write_bytes(b"voices")

    monkeypatch.setattr(
        commands_utility,
        "load_config",
        lambda: {"model_source": "github", "model_variant": "v1.0"},
    )
    monkeypatch.setattr(
        commands_utility, "get_model_asset_paths", lambda **kwargs: assets
    )

    def fail_downloader(*args, **kwargs):
        pytest.fail(f"downloader called: {args} {kwargs}")

    monkeypatch.setattr(commands_utility, "download_config", fail_downloader)
    monkeypatch.setattr(commands_utility, "download_model_github", fail_downloader)
    monkeypatch.setattr(commands_utility, "download_voices_github", fail_downloader)
    monkeypatch.setattr(commands_utility, "is_config_downloaded", fail_downloader)

    commands_utility.download(_context(), force=False, quality="fp32")

    assert "All required files are already present." in capsys.readouterr().out


def test_download_does_not_switch_configured_source() -> None:
    source, variant = commands_utility._resolve_model_source_and_variant(
        {"model_source": "huggingface", "model_variant": "v1.1-de"}
    )

    assert (source, variant) == ("huggingface", "v1.1-de")
