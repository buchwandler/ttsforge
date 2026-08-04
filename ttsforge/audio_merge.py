# ttsforge/audio_merge.py
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import soundfile as sf

from .constants import SAMPLE_RATE
from .utils import create_process, get_ffmpeg_path


@dataclass(slots=True)
class MergeMeta:
    fmt: str
    silence_between_chapters: float
    title: str | None = None
    author: str | None = None
    cover_image: Path | None = None


@dataclass(frozen=True, slots=True)
class OrderedAudioInput:
    path: Path
    sequence_index: int
    chapter_position: int
    chapter_title: str
    duration: float
    content_duration: float
    trailing_chapter_silence: float


@dataclass(frozen=True, slots=True)
class ChapterBoundary:
    chapter_position: int
    title: str
    start: float
    end: float


class AudioMerger:
    class LogCallback(Protocol):
        def __call__(self, message: str, level: str = "info") -> None: ...

    def __init__(self, log: AudioMerger.LogCallback):
        self.log = log

    @staticmethod
    def _concat_path(path: Path) -> str:
        """Quote a path for FFmpeg's concat demuxer."""
        value = str(path.absolute())
        if "\n" in value or "\r" in value:
            raise ValueError(f"FFmpeg concat paths cannot contain newlines: {path}")
        value = value.replace("\\", "\\\\").replace("'", "'\\''")
        return f"'{value}'"

    @staticmethod
    def _metadata_value(value: object) -> str:
        """Escape FFmetadata control characters without changing semantics."""
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
        )

    @staticmethod
    def _validate_inputs(
        chapter_files: list[Path],
        chapter_durations: list[float],
        chapter_titles: list[str],
    ) -> None:
        if not chapter_files:
            raise ValueError("At least one chapter file is required")
        if not (len(chapter_files) == len(chapter_durations) == len(chapter_titles)):
            raise ValueError(
                "chapter_files, chapter_durations, and chapter_titles must have "
                "equal lengths"
            )
        missing = [str(path) for path in chapter_files if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"Chapter audio file(s) not found: {', '.join(missing)}"
            )
        if any(duration < 0 for duration in chapter_durations):
            raise ValueError("Chapter durations cannot be negative")

    @staticmethod
    def _run_ffmpeg(cmd: list[str], operation: str) -> None:
        result = create_process(cmd, capture_output=True)
        assert isinstance(result, subprocess.CompletedProcess)
        if result.returncode == 0:
            return
        stderr = result.stderr or ""
        tail = str(stderr)[-2000:]
        detail = f"\nFFmpeg output (tail):\n{tail}" if tail else ""
        raise RuntimeError(f"ffmpeg failed while {operation}{detail}")

    def add_chapters_to_m4b(
        self, output_path: Path, chapters: list[dict[str, Any]], cover: Path | None
    ) -> None:
        if len(chapters) <= 1:
            return
        ffmpeg = get_ffmpeg_path()

        if not output_path.is_file():
            raise FileNotFoundError(f"M4B output not found: {output_path}")
        with tempfile.TemporaryDirectory(
            dir=output_path.parent, prefix=f".{output_path.stem}.ttsforge-"
        ) as temp_name:
            temp_dir = Path(temp_name)
            chapters_file = temp_dir / "chapters.txt"
            chapters_file.write_text(self._ffmetadata(chapters), encoding="utf-8")
            tmp_path = temp_dir / output_path.name
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(output_path),
                "-i",
                str(chapters_file),
                "-map",
                "0:a",
                "-map_metadata",
                "1",
                "-map_chapters",
                "1",
                "-c:a",
                "copy",
            ]

            if cover and cover.exists():
                cmd += [
                    "-i",
                    str(cover),
                    "-map",
                    "2",
                    "-c:v",
                    "copy",
                    "-disposition:v",
                    "attached_pic",
                ]

            cmd.append(str(tmp_path))
            self._run_ffmpeg(cmd, "adding m4b chapters")
            os.replace(tmp_path, output_path)

    def merge_chapter_wavs(
        self,
        chapter_files: list[Path],
        chapter_durations: list[float],
        chapter_titles: list[str],
        output_path: Path,
        meta: MergeMeta,
    ) -> None:
        self._validate_inputs(chapter_files, chapter_durations, chapter_titles)
        if meta.fmt == "wav":
            with tempfile.TemporaryDirectory(
                dir=output_path.parent, prefix=f".{output_path.stem}.ttsforge-"
            ) as temp_name:
                temp_output = Path(temp_name) / output_path.name
                self._merge_wavs(
                    chapter_files, temp_output, meta.silence_between_chapters
                )
                os.replace(temp_output, output_path)
            return

        ffmpeg = get_ffmpeg_path()
        with tempfile.TemporaryDirectory(
            dir=output_path.parent, prefix=f".{output_path.stem}.ttsforge-"
        ) as temp_name:
            temp_dir = Path(temp_name)
            concat_file = temp_dir / "concat.txt"
            silence_file = temp_dir / "silence.wav"
            temp_output = temp_dir / output_path.name

            if meta.silence_between_chapters > 0 and len(chapter_files) > 1:
                self._write_silence_wav(silence_file, meta.silence_between_chapters)

            with concat_file.open("w", encoding="utf-8") as f:
                for i, ch in enumerate(chapter_files):
                    f.write(f"file {self._concat_path(ch)}\n")
                    if i < len(chapter_files) - 1 and meta.silence_between_chapters > 0:
                        f.write(f"file {self._concat_path(silence_file)}\n")

            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]

            if meta.fmt == "m4b":
                if meta.cover_image and meta.cover_image.exists():
                    cmd += [
                        "-i",
                        str(meta.cover_image),
                        "-map",
                        "0:a",
                        "-map",
                        "1",
                        "-c:v",
                        "copy",
                        "-disposition:v",
                        "attached_pic",
                    ]
                cmd += [
                    "-c:a",
                    "aac",
                    "-q:a",
                    "2",
                    "-movflags",
                    "+faststart+use_metadata_tags",
                ]
                if meta.title:
                    cmd += ["-metadata", f"title={meta.title}"]
                if meta.author:
                    cmd += ["-metadata", f"artist={meta.author}"]
            elif meta.fmt == "opus":
                cmd += ["-c:a", "libopus", "-b:a", "24000"]
            elif meta.fmt == "mp3":
                cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
            elif meta.fmt == "flac":
                cmd += ["-c:a", "flac"]

            cmd.append(str(temp_output))
            self._run_ffmpeg(cmd, "merging chapters")
            os.replace(temp_output, output_path)

        if meta.fmt == "m4b" and len(chapter_files) > 1:
            times = []
            t = 0.0
            for i, (dur, title) in enumerate(
                zip(chapter_durations, chapter_titles, strict=True)
            ):
                times.append({"title": title, "start": t, "end": t + dur})
                t += dur
                if i < len(chapter_durations) - 1:
                    t += meta.silence_between_chapters
            self.add_chapters_to_m4b(output_path, times, meta.cover_image)

    def merge_ordered_wavs(
        self,
        inputs: Sequence[OrderedAudioInput],
        output_path: Path,
        *,
        chapter_boundaries: Sequence[ChapterBoundary] = (),
        meta: MergeMeta | None = None,
    ) -> None:
        """Concatenate finalized paragraph WAVs without adding any gaps."""
        ordered = tuple(sorted(inputs, key=lambda item: item.sequence_index))
        if not ordered:
            raise ValueError("At least one ordered audio input is required")
        if any(item.sequence_index != index for index, item in enumerate(ordered)):
            raise ValueError(
                "Ordered audio inputs must have contiguous sequence indices"
            )
        for item in ordered:
            if not item.path.is_file():
                raise FileNotFoundError(item.path)
            if item.duration < 0 or item.content_duration < 0:
                raise ValueError("Ordered audio durations cannot be negative")

        effective_meta = meta or MergeMeta(fmt="wav", silence_between_chapters=0.0)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if effective_meta.fmt == "wav":
            with tempfile.TemporaryDirectory(
                dir=output_path.parent, prefix=f".{output_path.stem}.ttsforge-"
            ) as temp_name:
                temporary = Path(temp_name) / output_path.name
                self._merge_wavs([item.path for item in ordered], temporary, 0.0)
                os.replace(temporary, output_path)
            return

        ffmpeg = get_ffmpeg_path()
        with tempfile.TemporaryDirectory(
            dir=output_path.parent, prefix=f".{output_path.stem}.ttsforge-"
        ) as temp_name:
            temp_dir = Path(temp_name)
            concat_file = temp_dir / "concat.txt"
            temporary = temp_dir / output_path.name
            concat_file.write_text(
                "".join(f"file {self._concat_path(item.path)}\n" for item in ordered),
                encoding="utf-8",
            )
            command = [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
            ]
            if effective_meta.fmt == "m4b":
                if effective_meta.cover_image and effective_meta.cover_image.exists():
                    command += [
                        "-i",
                        str(effective_meta.cover_image),
                        "-map",
                        "0:a",
                        "-map",
                        "1",
                        "-c:v",
                        "copy",
                        "-disposition:v",
                        "attached_pic",
                    ]
                command += [
                    "-c:a",
                    "aac",
                    "-q:a",
                    "2",
                    "-movflags",
                    "+faststart+use_metadata_tags",
                ]
                if effective_meta.title:
                    command += ["-metadata", f"title={effective_meta.title}"]
                if effective_meta.author:
                    command += ["-metadata", f"artist={effective_meta.author}"]
            elif effective_meta.fmt == "opus":
                command += ["-c:a", "libopus", "-b:a", "24000"]
            elif effective_meta.fmt == "mp3":
                command += ["-c:a", "libmp3lame", "-q:a", "2"]
            elif effective_meta.fmt == "flac":
                command += ["-c:a", "flac"]
            else:
                raise ValueError(f"Unsupported format: {effective_meta.fmt}")
            command.append(str(temporary))
            self._run_ffmpeg(command, "merging ordered paragraph audio")
            os.replace(temporary, output_path)

        if effective_meta.fmt == "m4b" and chapter_boundaries:
            self.add_chapters_to_m4b(
                output_path,
                [
                    {
                        "title": boundary.title,
                        "start": boundary.start,
                        "end": boundary.end,
                    }
                    for boundary in chapter_boundaries
                ],
                effective_meta.cover_image,
            )

    def _merge_wavs(
        self,
        chapter_files: list[Path],
        output_path: Path,
        silence_between_chapters: float,
    ) -> None:
        """Merge WAV chapters without requiring an external encoder."""
        silence_samples = int(silence_between_chapters * SAMPLE_RATE)
        silence = np.zeros(min(silence_samples, 65536), dtype="float32")

        with sf.SoundFile(
            str(output_path),
            "w",
            samplerate=SAMPLE_RATE,
            channels=1,
            format="WAV",
            subtype="PCM_16",
        ) as output:
            for chapter_index, chapter_file in enumerate(chapter_files):
                with sf.SoundFile(str(chapter_file), "r") as chapter:
                    if chapter.samplerate != SAMPLE_RATE or chapter.channels != 1:
                        raise ValueError(
                            "WAV chapters must be mono files at "
                            f"{SAMPLE_RATE} Hz: {chapter_file}"
                        )

                    while True:
                        audio = chapter.read(65536, dtype="float32")
                        if len(audio) == 0:
                            break
                        output.write(audio)

                if chapter_index < len(chapter_files) - 1:
                    remaining = silence_samples
                    while remaining > 0:
                        chunk_size = min(remaining, len(silence))
                        output.write(silence[:chunk_size])
                        remaining -= chunk_size

    def _write_silence_wav(self, path: Path, duration: float) -> None:
        samples = int(duration * SAMPLE_RATE)
        silence = np.zeros(min(samples, 65536), dtype="float32")
        with sf.SoundFile(
            str(path), "w", samplerate=SAMPLE_RATE, channels=1, format="wav"
        ) as f:
            remaining = samples
            while remaining > 0:
                chunk_size = min(remaining, len(silence))
                f.write(silence[:chunk_size])
                remaining -= chunk_size

    def _ffmetadata(self, chapters: list[dict[str, Any]]) -> str:
        lines = [";FFMETADATA1"]
        for ch in chapters:
            title = self._metadata_value(ch["title"])
            lines += [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={int(ch['start'] * 1000)}",
                f"END={int(ch['end'] * 1000)}",
                f"title={title}",
                "",
            ]
        return "\n".join(lines)
