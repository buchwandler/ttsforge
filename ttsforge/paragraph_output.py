"""Owned paragraph output directories and atomic audio artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import soundfile as sf

from .constants import SAMPLE_RATE
from .render_units import (
    PARAGRAPH_MANIFEST_SCHEMA,
    PARAGRAPH_OUTPUT_SCHEMA,
    RenderUnitState,
)
from .utils import atomic_write_json

SEQUENCE_WIDTH = 8
CHAPTER_WIDTH = 6
PARAGRAPH_WIDTH = 6
MAX_BASENAME_LENGTH = 240
FINALIZED_WAV_RE = re.compile(
    r"^\d{8}__c\d{6}__p\d{6}__(?:title|paragraph)__.+\.wav$"
)
OWNERSHIP_KEYS = ("schema_version", "workspace_id", "source_hash", "output_path", "conversion_unit")


def paragraph_directory(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_paragraphs")


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_").upper()
    return safe or "UNTITLED"


def canonical_filename(
    *,
    sequence_index: int,
    source_chapter_index: int,
    paragraph_index: int,
    kind: str,
    chapter_title: str,
) -> str:
    """Return the fixed-width filename whose lexical order is playback order."""
    if sequence_index < 1 or source_chapter_index < 0 or paragraph_index < 0:
        raise ValueError("sequence and unit indices must be non-negative")
    if kind not in {"title", "paragraph"}:
        raise ValueError("kind must be title or paragraph")
    prefix = (
        f"{sequence_index:0{SEQUENCE_WIDTH}d}"
        f"__c{source_chapter_index + 1:0{CHAPTER_WIDTH}d}"
        f"__p{paragraph_index:0{PARAGRAPH_WIDTH}d}__{kind}__"
    )
    suffix = _slug(chapter_title)
    available = MAX_BASENAME_LENGTH - len(prefix) - len(".wav")
    return f"{prefix}{suffix[:max(1, available)]}.wav"


def is_canonical_filename(name: str) -> bool:
    return bool(FINALIZED_WAV_RE.fullmatch(name))


def owned_path(directory: Path, name: str) -> Path:
    candidate = (directory / name).resolve()
    root = directory.resolve()
    if candidate.parent != root:
        raise ValueError(f"Paragraph artifact escapes owned directory: {name}")
    return candidate


def ensure_owned_directory(
    directory: Path,
    *,
    ownership: Mapping[str, object],
    fresh: bool = False,
) -> None:
    """Create or validate a paragraph directory without deleting user files."""
    if not directory.exists():
        directory.mkdir(parents=True)
        return
    if not directory.is_dir():
        raise ValueError(f"Paragraph output path is not a directory: {directory}")

    manifest_path = directory / "manifest.json"
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Refusing paragraph directory without valid TTSForge ownership: {directory}"
        ) from exc
    if any(existing.get(key) != ownership.get(key) for key in OWNERSHIP_KEYS):
        raise ValueError("Paragraph output ownership belongs to another conversion")
    if fresh:
        cleanup_owned_artifacts(directory, existing)


def cleanup_owned_artifacts(directory: Path, manifest: Mapping[str, object]) -> None:
    """Remove only files named by a matching TTSForge manifest and its temp files."""
    files = manifest.get("files", [])
    if isinstance(files, list):
        for entry in files:
            if isinstance(entry, dict) and isinstance(entry.get("file"), str):
                owned_path(directory, entry["file"]).unlink(missing_ok=True)
            if isinstance(entry, dict) and isinstance(entry.get("marker_file"), str):
                owned_path(directory, entry["marker_file"]).unlink(missing_ok=True)
    for path in directory.iterdir():
        if path.name.startswith(".") and path.name.endswith(".part"):
            path.unlink(missing_ok=True)


def _write_temp_wav(
    samples: np.ndarray,
    sample_rate: int,
    destination: Path,
    trailing_chapter_silence: float,
) -> Path:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        with sf.SoundFile(
            str(temp_path),
            mode="w",
            samplerate=sample_rate,
            channels=1,
            format="WAV",
            subtype="PCM_16",
        ) as output:
            if len(audio):
                output.write(audio)
            remaining = int(round(max(0.0, trailing_chapter_silence) * sample_rate))
            silence = np.zeros(min(65536, max(1, remaining)), dtype=np.float32)
            while remaining:
                count = min(remaining, len(silence))
                output.write(silence[:count])
                remaining -= count
        validate_wav(temp_path, sample_rate=sample_rate)
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def validate_wav(
    path: Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    expected_duration: float | None = None,
    tolerance: float = 0.02,
) -> float:
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"Invalid paragraph WAV: {path}")
    info = sf.info(str(path))
    if info.channels != 1 or info.samplerate != sample_rate or info.frames <= 0:
        raise ValueError(
            f"Paragraph WAV must be mono {sample_rate} Hz with positive frames: {path}"
        )
    duration = info.frames / info.samplerate
    if expected_duration is not None and abs(duration - expected_duration) > tolerance:
        raise ValueError(
            f"Paragraph WAV duration mismatch for {path}: {duration:.4f} vs "
            f"{expected_duration:.4f} seconds"
        )
    return duration


def finalize_wav(
    *,
    samples: np.ndarray,
    sample_rate: int,
    destination: Path,
    trailing_chapter_silence: float = 0.0,
) -> float:
    """Write, validate, and atomically publish a finalized paragraph WAV."""
    if not is_canonical_filename(destination.name):
        raise ValueError(f"Non-canonical paragraph WAV name: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _write_temp_wav(
        samples,
        sample_rate,
        destination,
        trailing_chapter_silence,
    )
    try:
        duration = validate_wav(temp_path, sample_rate=sample_rate)
        os.replace(temp_path, destination)
        validate_wav(destination, sample_rate=sample_rate)
        return duration
    finally:
        temp_path.unlink(missing_ok=True)


def _manifest_entry(
    unit: RenderUnitState,
    *,
    chapter_title: str,
    directory: Path,
) -> dict[str, object] | None:
    if not unit.completed or not unit.audio_file:
        return None
    path = owned_path(directory, unit.audio_file)
    if not path.is_file() or not is_canonical_filename(path.name):
        return None
    duration = validate_wav(path, sample_rate=unit.sample_rate)
    entry: dict[str, object] = {
        "sequence": unit.sequence_index + 1,
        "file": path.name,
        "source_chapter": unit.source_chapter_index,
        "paragraph": unit.paragraph_index,
        "kind": unit.kind,
        "chapter_title": chapter_title,
        "duration": duration,
        "content_duration": unit.content_duration,
        "trailing_chapter_silence": unit.trailing_chapter_silence,
        "char_count": unit.char_count,
        "content_hash": unit.content_hash,
        "sample_rate": unit.sample_rate,
    }
    if unit.marker_file:
        marker = owned_path(directory, unit.marker_file)
        if marker.is_file():
            entry["marker_file"] = marker.name
    return entry


def rebuild_manifest_and_playlist(
    directory: Path,
    *,
    ownership: Mapping[str, object],
    units: Sequence[RenderUnitState],
    chapter_titles: Mapping[int, str],
) -> dict[str, object]:
    """Atomically regenerate deterministic visible metadata from finalized state."""
    entries = [
        entry
        for unit in sorted(units, key=lambda item: item.sequence_index)
        if (entry := _manifest_entry(
            unit,
            chapter_title=chapter_titles.get(unit.chapter_position, "Untitled"),
            directory=directory,
        ))
    ]
    manifest: dict[str, object] = {
        **dict(ownership),
        "schema_version": PARAGRAPH_MANIFEST_SCHEMA,
        "output_schema": PARAGRAPH_OUTPUT_SCHEMA,
        "sample_rate": SAMPLE_RATE,
        "files": entries,
    }
    atomic_write_json(directory / "manifest.json", manifest, indent=2, ensure_ascii=True)
    playlist_lines = ["#EXTM3U", *(str(entry["file"]) for entry in entries)]
    playlist = directory / "playlist.m3u8"
    fd, temp_name = tempfile.mkstemp(prefix=".playlist.", suffix=".part", dir=directory)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_text("\n".join(playlist_lines) + "\n", encoding="utf-8", newline="\n")
        os.replace(temp_path, playlist)
    finally:
        temp_path.unlink(missing_ok=True)
    return manifest
