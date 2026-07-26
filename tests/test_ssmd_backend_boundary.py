"""SSMD-only conversion must not initialize the ONNX backend."""

from __future__ import annotations

from pathlib import Path

from ttsforge.conversion import Chapter, ConversionOptions, TTSConverter


def test_ssmd_only_conversion_does_not_initialize_backend(
    tmp_path: Path, monkeypatch
) -> None:
    converter = TTSConverter(ConversionOptions(title="Book", generate_ssmd_only=True))
    monkeypatch.setattr(
        converter,
        "_init_runner",
        lambda: (_ for _ in ()).throw(AssertionError("backend initialized")),
    )
    result = converter.convert_chapters_resumable(
        [Chapter(title="Chapter", content="Hello world", index=0)],
        tmp_path / "book.m4b",
        resume=False,
    )
    assert result.success is True
    assert result.chapters_dir is not None
    assert list(result.chapters_dir.glob("*.ssmd"))
