#!/usr/bin/env python3
"""Interrupt paragraph conversion, then resume at the first incomplete unit."""

from __future__ import annotations

import argparse
from pathlib import Path

from ttsforge.conversion import ConversionOptions, ConversionState, TTSConverter
from ttsforge.paragraph_output import paragraph_directory


def _report_state(state: ConversionState) -> None:
    completed = state.get_completed_unit_count()
    total = state.get_total_unit_count()
    seeds = [chapter.paragraph_random_seed for chapter in state.chapters]
    print(f"Saved units: {completed}/{total}")
    print(f"Persisted chapter preparation seeds: {seeds}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument(
        "--stop-after",
        type=int,
        default=1,
        help="Cancel after this many finalized units in the first pass (default: 1).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Optional explicit random seed; automatic per-chapter seeds are "
            "used by default."
        ),
    )
    args = parser.parse_args()
    if args.stop_after < 1:
        parser.error("--stop-after must be at least 1")

    output = args.output or args.epub.with_suffix(".m4b")
    common = {
        "voice": args.voice,
        "output_format": output.suffix.lstrip(".") or "m4b",
        "output_dir": output.parent,
        "title": output.stem,
        "conversion_unit": "paragraph",
        "random_seed": args.seed,
        "use_spacy": None,
    }

    first_converter: TTSConverter | None = None

    def cancel_after_limit(progress) -> None:
        if progress.current_unit >= args.stop_after and first_converter is not None:
            first_converter._cancelled = True

    print(f"First pass: cancel after {args.stop_after} finalized unit(s).")
    first_options = ConversionOptions(**common, resume=False)
    with TTSConverter(
        options=first_options,
        progress_callback=cancel_after_limit,
    ) as converter:
        first_converter = converter
        first_result = converter.convert_epub(args.epub, output)

    if first_result.success:
        print("The first pass completed; choose a smaller --stop-after value.")
        return 1
    if first_result.chapters_dir is None:
        print(
            first_result.error_message
            or "The interrupted pass did not save a workspace."
        )
        return 1

    state_file = first_result.chapters_dir / "state.json"
    state = ConversionState.load(state_file)
    if state is None:
        print(f"Unable to load saved state: {state_file}")
        return 1
    next_unit = state.get_next_incomplete_unit()
    if next_unit is None:
        print("No incomplete unit was saved; choose a smaller --stop-after value.")
        return 1
    _report_state(state)
    print(
        "Next unit before restart: "
        f"chapter {next_unit.chapter_position + 1}, "
        f"paragraph {int(next_unit.chapter_unit_index or 0) + 1}"
    )

    resumed_units: list[int] = []
    second_options = ConversionOptions(**common, resume=True)
    print("Second pass: create a new converter and resume.")
    with TTSConverter(
        options=second_options,
        progress_callback=lambda progress: resumed_units.append(progress.current_unit),
    ) as converter:
        second_result = converter.convert_epub(args.epub, output)
    if not second_result.success:
        print(second_result.error_message or "Resume failed")
        return 1

    expected_first_unit = next_unit.sequence_index + 1
    if not resumed_units or resumed_units[0] != expected_first_unit:
        print(
            "Resume verification failed: expected first rendered unit "
            f"{expected_first_unit}, observed {resumed_units[:1]}"
        )
        return 1

    print(
        f"Resume verified: rendering began at unit {resumed_units[0]} and "
        f"completed {output}."
    )
    print(f"Paragraph artifacts: {paragraph_directory(output)}")
    print("Use --fresh when an explicit full restart is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
