#!/usr/bin/env python3
"""Run paragraph conversion twice to demonstrate unit-boundary resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ttsforge.conversion import ConversionOptions, TTSConverter
from ttsforge.paragraph_output import paragraph_directory


def _report_workspace(output: Path) -> None:
    directory = paragraph_directory(output)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        print("No paragraph manifest exists yet.")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files", [])
    print(f"Retained units: {len(entries)} ({manifest_path})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start the first pass with a new workspace; the second pass resumes it.",
    )
    args = parser.parse_args()

    output = args.output or args.epub.with_suffix(".m4b")
    for pass_number in (1, 2):
        options = ConversionOptions(
            voice=args.voice,
            output_format=output.suffix.lstrip(".") or "m4b",
            conversion_unit="paragraph",
            use_spacy=None,
            resume=not (args.fresh and pass_number == 1),
        )
        print(
            f"Pass {pass_number}: "
            + ("fresh workspace" if not options.resume else "resume compatible units")
        )
        with TTSConverter(options=options) as converter:
            result = converter.convert_epub(args.epub, output)
        if not result.success:
            print(result.error_message or "Conversion failed")
            return 1
        _report_workspace(output)

    print(
        "Resume identity requires the same input, selected chapters, generation "
        "fingerprint, and conversion_unit. Use --fresh to intentionally restart."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
