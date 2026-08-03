"""Manifest and ownership tests for paragraph output."""

import json
from pathlib import Path

import numpy as np

from ttsforge.paragraph_output import (
    canonical_filename,
    ensure_owned_directory,
    finalize_wav,
    rebuild_manifest_and_playlist,
)
from ttsforge.render_units import RenderUnitState


def test_manifest_playlist_are_ordered_and_owned(tmp_path: Path):
    directory = tmp_path / "Book_paragraphs"
    ownership = {
        "schema_version": 1,
        "workspace_id": "workspace",
        "source_hash": "source",
        "output_path": str(tmp_path / "Book.wav"),
        "conversion_unit": "paragraph",
    }
    ensure_owned_directory(directory, ownership=ownership)
    units = []
    for sequence in (0, 1):
        name = canonical_filename(
            sequence_index=sequence + 1,
            source_chapter_index=0,
            paragraph_index=sequence + 1,
            kind="paragraph",
            chapter_title="Book",
        )
        finalize_wav(
            samples=np.ones(240, dtype=np.float32),
            sample_rate=24000,
            destination=directory / name,
        )
        units.append(
            RenderUnitState(
                sequence_index=sequence,
                unit_index=sequence,
                chapter_position=0,
                source_chapter_index=0,
                paragraph_index=sequence + 1,
                kind="paragraph",
                content_hash=f"hash-{sequence}",
                render_fingerprint=f"fingerprint-{sequence}",
                char_count=4,
                completed=True,
                audio_file=name,
                duration=0.01,
                content_duration=0.01,
            )
        )

    manifest = rebuild_manifest_and_playlist(
        directory,
        ownership=ownership,
        units=units,
        chapter_titles={0: "Book"},
    )
    assert [entry["file"] for entry in manifest["files"]] == sorted(
        entry["file"] for entry in manifest["files"]
    )
    assert (directory / "playlist.m3u8").read_text(encoding="utf-8").splitlines()[1:] == [
        entry["file"] for entry in manifest["files"]
    ]
    persisted = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["workspace_id"] == "workspace"
    assert not list(directory.glob("*.part"))


def test_unowned_existing_directory_is_rejected(tmp_path: Path):
    directory = tmp_path / "Book_paragraphs"
    directory.mkdir()
    (directory / "unrelated.wav").write_bytes(b"user data")
    try:
        ensure_owned_directory(directory, ownership={"conversion_unit": "paragraph"})
    except ValueError as exc:
        assert "ownership" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unowned paragraph directory was accepted")

