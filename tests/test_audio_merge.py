"""Safety and escaping tests for FFmpeg audio merging."""

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ttsforge.audio_merge import AudioMerger


def test_concat_path_escapes_apostrophes_and_backslashes(tmp_path: Path) -> None:
    path = tmp_path / "O'Brien\\chapter.wav"
    escaped = AudioMerger._concat_path(path)
    assert escaped.startswith("'") and escaped.endswith("'")
    assert "'\\''" in escaped
    assert "\\\\" in escaped


def test_ffmetadata_escapes_control_characters() -> None:
    value = AudioMerger._metadata_value("a=b;c#d\\e\nnext")
    assert value == "a\\=b\\;c\\#d\\\\e\\nnext"


def test_merge_validates_parallel_metadata_and_missing_files(tmp_path: Path) -> None:
    merger = AudioMerger(lambda message, level="info": None)
    chapter = tmp_path / "chapter.wav"
    chapter.touch()
    with pytest.raises(ValueError, match="equal lengths"):
        merger.merge_chapter_wavs(
            [chapter], [], ["Chapter"], tmp_path / "out.m4b", _meta()
        )
    with pytest.raises(FileNotFoundError):
        merger.merge_chapter_wavs(
            [tmp_path / "missing.wav"],
            [1.0],
            ["Chapter"],
            tmp_path / "out.m4b",
            _meta(),
        )
    with pytest.raises(ValueError, match="At least one"):
        merger.merge_chapter_wavs([], [], [], tmp_path / "out.wav", _meta())
    with pytest.raises(ValueError, match="negative"):
        merger.merge_chapter_wavs(
            [chapter], [-1.0], ["Chapter"], tmp_path / "out.wav", _meta()
        )


def test_concat_and_metadata_reject_unsafe_newlines() -> None:
    with pytest.raises(ValueError, match="newlines"):
        AudioMerger._concat_path(Path("bad\nname.wav"))
    assert "\\r" in AudioMerger._metadata_value("line\r")


def test_wav_merge_writes_audio_and_silence(tmp_path: Path) -> None:
    from ttsforge.audio_merge import MergeMeta

    first = tmp_path / "one.wav"
    second = tmp_path / "two.wav"
    sf.write(first, np.ones(4, dtype=np.float32), 24000, subtype="PCM_16")
    sf.write(second, np.full(3, 0.5, dtype=np.float32), 24000, subtype="PCM_16")
    output = tmp_path / "merged.wav"
    AudioMerger(lambda message, level="info": None).merge_chapter_wavs(
        [first, second],
        [4 / 24000, 3 / 24000],
        ["One", "Two"],
        output,
        MergeMeta(fmt="wav", silence_between_chapters=0.01),
    )
    data, rate = sf.read(output)
    assert rate == 24000
    assert len(data) == 4 + 3 + 240


def test_wav_merge_rejects_wrong_sample_rate(tmp_path: Path) -> None:
    from ttsforge.audio_merge import MergeMeta

    chapter = tmp_path / "wrong.wav"
    sf.write(chapter, np.zeros(4, dtype=np.float32), 8000)
    with pytest.raises(ValueError, match="mono files"):
        AudioMerger(lambda message, level="info": None).merge_chapter_wavs(
            [chapter],
            [1.0],
            ["Wrong"],
            tmp_path / "output.wav",
            MergeMeta(fmt="wav", silence_between_chapters=0),
        )


def test_ffmpeg_formats_and_m4b_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ttsforge.audio_merge import MergeMeta

    chapter = tmp_path / "chapter.wav"
    chapter.touch()
    calls: list[list[str]] = []
    merger = AudioMerger(lambda message, level="info": None)

    def fake_run(cmd: list[str], operation: str) -> None:
        calls.append(cmd)
        Path(cmd[-1]).touch()

    monkeypatch.setattr(merger, "_run_ffmpeg", fake_run)
    monkeypatch.setattr("ttsforge.audio_merge.get_ffmpeg_path", lambda: "ffmpeg")
    for fmt in ("opus", "mp3", "flac"):
        output = tmp_path / f"out.{fmt}"
        merger.merge_chapter_wavs(
            [chapter],
            [1.0],
            ["Chapter"],
            output,
            MergeMeta(fmt=fmt, silence_between_chapters=0),
        )
        assert output.exists()
    output = tmp_path / "out.m4b"
    cover = tmp_path / "cover.jpg"
    cover.touch()
    monkeypatch.setattr(merger, "add_chapters_to_m4b", lambda *args: None)
    merger.merge_chapter_wavs(
        [chapter, chapter],
        [1.0, 2.0],
        ["One", "Two"],
        output,
        MergeMeta(
            fmt="m4b",
            silence_between_chapters=0.5,
            title="Book",
            author="Me",
            cover_image=cover,
        ),
    )
    assert output.exists()
    assert any("-metadata" in cmd and "title=Book" in cmd for cmd in calls)


def test_m4b_chapter_update_is_atomic_and_optional_cover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "book.m4b"
    output.write_bytes(b"old")
    chapters = [
        {"title": "One", "start": 0.0, "end": 1.0},
        {"title": "Two", "start": 1.0, "end": 2.0},
    ]
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], operation: str) -> None:
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"new")

    merger = AudioMerger(lambda message, level="info": None)
    monkeypatch.setattr(merger, "_run_ffmpeg", fake_run)
    monkeypatch.setattr("ttsforge.audio_merge.get_ffmpeg_path", lambda: "ffmpeg")
    merger.add_chapters_to_m4b(output, chapters, None)
    assert output.read_bytes() == b"new"
    assert any("-map_chapters" in cmd for cmd in calls)
    before = len(calls)
    merger.add_chapters_to_m4b(output, chapters[:1], None)
    assert len(calls) == before


def test_merge_cleans_unique_workspace_after_ffmpeg_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    merger = AudioMerger(lambda message, level="info": None)
    chapter = tmp_path / "O'Brien.wav"
    chapter.touch()
    monkeypatch.setattr("ttsforge.audio_merge.get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        "ttsforge.audio_merge.create_process",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr="invalid concat path"
        ),
    )
    with pytest.raises(RuntimeError, match="invalid concat path"):
        merger.merge_chapter_wavs(
            [chapter], [1.0], ["Chapter"], tmp_path / "out.m4b", _meta()
        )
    assert list(tmp_path.glob(".out.ttsforge-*")) == []


def _meta():
    from ttsforge.audio_merge import MergeMeta

    return MergeMeta(fmt="m4b", silence_between_chapters=0)
