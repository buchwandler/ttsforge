#!/usr/bin/env python3
"""Convert an EPUB into bounded, resumable paragraph render units."""

from __future__ import annotations

import argparse
from pathlib import Path

from ttsforge.conversion import ConversionOptions, TTSConverter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--voice", default="af_heart")
    args = parser.parse_args()

    output = args.output or args.epub.with_suffix(".m4b")
    options = ConversionOptions(
        voice=args.voice,
        output_format=output.suffix.lstrip(".") or "m4b",
        conversion_unit="paragraph",
        use_spacy=None,
    )

    def report(progress) -> None:
        print(
            f"chapter {progress.current_chapter}/{progress.total_chapters} "
            f"unit {progress.current_unit}/{progress.total_units} "
            f"kind={progress.unit_kind or 'chapter'} "
            f"paragraph={progress.current_paragraph}"
        )

    with TTSConverter(
        options=options,
        progress_callback=report,
        log_callback=lambda message, level="info": print(f"[{level}] {message}"),
    ) as converter:
        result = converter.convert_epub(args.epub, output)

    if not result.success:
        print(result.error_message or "Conversion failed")
        return 1

    print(f"Audiobook: {result.output_path}")
    print(f"Paragraph WAVs: {result.paragraphs_dir}")
    if result.paragraphs_dir:
        print(f"Manifest: {result.paragraphs_dir / 'manifest.json'}")
        print(f"Playlist: {result.paragraphs_dir / 'playlist.m3u8'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
