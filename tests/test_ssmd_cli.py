from __future__ import annotations

import json

from typer.testing import CliRunner

from ttsforge.cli import app


def test_ssmd_inspect_json_does_not_initialize_onnx(tmp_path, monkeypatch) -> None:
    path = tmp_path / "document.ssmd"
    path.write_text("---\ntitle: CLI review\n---\nHello.\n", encoding="utf-8")
    monkeypatch.setitem(__import__("sys").modules, "pykokoro.onnx_backend", None)

    result = CliRunner().invoke(app, ["ssmd", "inspect", str(path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["title"] == "CLI review"
    assert payload["plain_text_characters"] == len("Hello.\n")


def test_ssmd_validate_strict_promotes_warning(tmp_path) -> None:
    path = tmp_path / "document.ssmd"
    path.write_text("---\ncustom: value\n---\nHello.\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["ssmd", "validate", str(path), "--strict"])

    assert result.exit_code == 1
    assert "header.unknown_key" in result.output
