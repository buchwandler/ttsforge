import importlib
import json
import os
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from ttsforge.utils import (
    atomic_write_json,
    create_process,
    ensure_ffmpeg,
    format_filename_template,
    load_config,
    resolve_conversion_defaults,
    run_process,
    sanitize_filename,
    validate_config_value,
)


def test_sanitize_filename() -> None:
    assert sanitize_filename("Hello: World/Testing?") == "Hello_WorldTesting"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("voice", ""),
        ("language", ""),
        ("speed", 0.0),
        ("use_gpu", False),
        ("split_mode", ""),
    ],
)
def test_resolve_conversion_defaults_preserves_falsey_overrides(
    key: str, value: object
) -> None:
    config = {
        "default_voice": "af_heart",
        "default_language": "a",
        "default_speed": 1.0,
        "default_split_mode": "auto",
        "use_gpu": True,
        "phonemization_lang": "en-us",
    }
    assert resolve_conversion_defaults(config, {key: value})[key] == value


def test_format_filename_template() -> None:
    result = format_filename_template(
        "{author}_{book_title}", author="Jane Doe", book_title="My Book"
    )
    assert result == "Jane_Doe_My_Book"


def test_run_process_large_output() -> None:
    script = "import sys; sys.stdout.write('x' * (1024 * 1024))"
    result = run_process([sys.executable, "-c", script], text=True)
    assert result.returncode == 0
    assert result.stdout is not None
    assert len(result.stdout) >= 1024 * 1024


def test_create_process_capture_output() -> None:
    result = create_process(
        [sys.executable, "-c", "print('hello')"], capture_output=True
    )
    assert result.returncode == 0
    assert isinstance(result.stdout, str)
    assert "hello" in result.stdout


def test_create_process_suppressed_output() -> None:
    proc = create_process([sys.executable, "-c", "print('hi')"], suppress_output=True)
    assert proc.wait(timeout=5) == 0


def test_atomic_write_json_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"ok": true}', encoding="utf-8")

    def raise_replace(src: str, dst: str) -> None:
        raise OSError("boom")

    original = path.read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", raise_replace)
    with pytest.raises(OSError):
        atomic_write_json(path, {"ok": False}, indent=2, ensure_ascii=True)

    assert path.read_text(encoding="utf-8") == original


def test_atomic_write_json_uses_unique_same_directory_temps(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    temp_names: list[str] = []
    original_replace = os.replace

    def record_replace(
        src: str | os.PathLike[str], dst: str | os.PathLike[str]
    ) -> None:
        temp_names.append(Path(src).name)
        original_replace(src, dst)

    import threading

    # Sequential calls still prove the old shared `<target>.tmp` protocol is
    # gone; separate threads exercise the same-directory writer path.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(os, "replace", record_replace)
        threads = [
            threading.Thread(target=atomic_write_json, args=(path, {"i": i}))
            for i in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(temp_names) == 4
    assert len(set(temp_names)) == 4
    assert not (tmp_path / "state.json.tmp").exists()


def test_ensure_ffmpeg_system_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/ffmpeg")

    called = {"imported": False}

    def fake_import(name: str):
        called["imported"] = True
        raise ImportError

    monkeypatch.setattr(importlib, "import_module", fake_import)
    assert ensure_ffmpeg() is True
    assert called["imported"] is False


def test_ensure_ffmpeg_static_available(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"added": False}

    def fake_add_paths() -> None:
        state["added"] = True

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: types.SimpleNamespace(add_paths=fake_add_paths),
    )

    def fake_which(cmd: str):
        if cmd != "ffmpeg":
            return None
        return "/fake/ffmpeg" if state["added"] else None

    monkeypatch.setattr(shutil, "which", fake_which)
    assert ensure_ffmpeg() is True
    assert state["added"] is True


def test_ensure_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    def raise_import(name: str):
        raise ImportError

    monkeypatch.setattr(importlib, "import_module", raise_import)
    with pytest.raises(RuntimeError):
        ensure_ffmpeg()


def test_load_config_ignores_invalid_pause_variance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "config.json"
    original = {"pause_variance": -0.1, "default_language": "b"}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        config = load_config()

    captured = capsys.readouterr()
    assert config["pause_variance"] == 0.05
    assert config["default_language"] == "b"
    assert "ignoring invalid config value" in captured.err
    assert "pause_variance" in captured.err
    assert config_path.read_text(encoding="utf-8") == json.dumps(original)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"use_gpu": True}, "auto"),
        ({"use_gpu": False}, "cpu"),
        ({"use_gpu": True, "onnx_provider": "nnapi"}, "nnapi"),
        ({"default_use_gpu": True}, "auto"),
    ],
)
def test_load_config_migrates_provider_in_memory(
    tmp_path: Path, raw: dict[str, object], expected: str
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    with patch("ttsforge.utils.get_user_config_path", return_value=config_path):
        config = load_config()
    assert config["onnx_provider"] == expected
    assert json.loads(config_path.read_text(encoding="utf-8")) == raw


@pytest.mark.parametrize(
    "value",
    ["", "  ", "potato", "CPU ExecutionProvider", "cpu-execution-provider"],
)
def test_validate_config_value_rejects_invalid_provider(value: str) -> None:
    with pytest.raises(ValueError, match="ONNX provider"):
        validate_config_value("onnx_provider", value)


@pytest.mark.parametrize(
    "value",
    ["auto", "NNAPI", "xnnpack", "CPUExecutionProvider", "Custom_1ExecutionProvider"],
)
def test_validate_config_value_accepts_provider_aliases_and_full_names(
    value: str,
) -> None:
    validate_config_value("onnx_provider", value)
