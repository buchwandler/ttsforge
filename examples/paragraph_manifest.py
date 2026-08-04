#!/usr/bin/env python3
"""Inspect a paragraph manifest without loading ONNX or TTS models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_manifest(path: Path, *, print_ordered_list: bool = False) -> int:
    directory = path.parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("manifest files must be a list")

    expected_sequence = 1
    for entry in entries:
        sequence = entry.get("sequence")
        if sequence != expected_sequence:
            raise ValueError(
                f"manifest sequence is not contiguous at {sequence}; "
                f"expected {expected_sequence}"
            )
        audio = directory / str(entry["file"])
        if not audio.is_file():
            raise FileNotFoundError(audio)
        marker_name = entry.get("marker_file")
        if marker_name is not None and not (directory / str(marker_name)).is_file():
            raise FileNotFoundError(directory / str(marker_name))
        print(
            f"{sequence:04d} kind={entry.get('kind', 'unknown')} "
            f"chapter={entry.get('source_chapter')} "
            f"source_paragraph={entry.get('source_paragraph')} "
            f"duration={entry.get('duration', 0):.3f}s "
            f"wav={entry['file']} marker={marker_name or '-'}"
        )
        expected_sequence += 1

    if print_ordered_list:
        for entry in entries:
            print(entry["file"])
    print(f"Validated {len(entries)} render units in {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--ordered-list", action="store_true", help="Print the ordered WAV list too."
    )
    args = parser.parse_args()
    try:
        return inspect_manifest(args.manifest, print_ordered_list=args.ordered_list)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
