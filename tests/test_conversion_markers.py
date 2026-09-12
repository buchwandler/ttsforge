"""Regression tests for aggregate marker finalization."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from ttsforge.conversion import (
    Chapter,
    ConversionOptions,
    RenderedChapter,
    TTSConverter,
)


def test_m4b_finalization_uses_merger_rate_and_globalizes_resume_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "book.m4b"
    options = ConversionOptions(
        output_format="m4b",
        output_dir=tmp_path,
        title="Book",
        silence_between_chapters=0.5,
    )
    chapters = [
        Chapter(title="One", content="first", index=0),
        Chapter(title="Two", content="second", index=1),
    ]

    def fake_render(
        self: TTSConverter,
        chapter: Chapter,
        output_file: Path,
        ssmd_content: str,
        ssmd_file: Path,
    ) -> RenderedChapter:
        sf.write(output_file, np.zeros(16000, dtype=np.float32), 16000)
        return RenderedChapter(
            duration=1.0,
            rendered_path=output_file,
            sample_rate=16000,
            diagnostics=(),
            markers=[
                {
                    "name": chapter.title,
                    "char_offset": 0,
                    "sample_offset": 16000,
                    "time_s": 1.0,
                }
            ],
            document_metadata={},
        )

    def fake_merge(
        chapter_files: list[Path],
        chapter_durations: list[float],
        chapter_titles: list[str],
        output_path: Path,
        meta: object,
    ) -> int:
        output_path.write_bytes(b"fake m4b")
        return 16000

    monkeypatch.setattr(TTSConverter, "_preflight_spacy_models", lambda self: None)
    monkeypatch.setattr(TTSConverter, "_render_chapter_wav", fake_render)

    real_info = sf.info

    def no_m4b_probe(path: str, *args: object, **kwargs: object):
        if str(path).endswith(".m4b"):
            raise AssertionError("final M4B must not be probed with soundfile")
        return real_info(path, *args, **kwargs)
    monkeypatch.setattr("ttsforge.conversion.sf.info", no_m4b_probe)

    first = TTSConverter(options)
    first._load_or_generate_ssmd = lambda *args, **kwargs: (
        "text",
        "hash",
        SimpleNamespace(title="", issues=()),
    )
    first._merger.merge_chapter_wavs = fake_merge
    result = first.convert_chapters_resumable(chapters, output, resume=False)

    assert result.success, result.error_message
    payload = json.loads(output.with_suffix(".m4b.markers.json").read_text())
    assert payload["sample_rate"] == 16000
    assert payload["markers"][1]["time_s"] == pytest.approx(2.5)
    assert payload["markers"][1]["sample_offset"] == 40000

    second = TTSConverter(options)
    second._merger.merge_chapter_wavs = fake_merge
    monkeypatch.setattr(
        second,
        "_render_chapter_wav",
        lambda *args, **kwargs: pytest.fail("resumed chapters must not rerender"),
    )
    resumed = second.convert_chapters_resumable(chapters, output, resume=True)

    assert resumed.success, resumed.error_message
    resumed_payload = json.loads(
        output.with_suffix(".m4b.markers.json").read_text()
    )
    assert resumed_payload["sample_rate"] == 16000
    assert resumed_payload["markers"] == payload["markers"]
