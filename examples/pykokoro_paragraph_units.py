#!/usr/bin/env python3
"""Render PyKokoro public paragraph units one at a time."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from ttsforge.kokoro_runner import KokoroRunOptions, KokoroRunner

DOCUMENT = """---
title: Unit boundary demo
voice_bindings:
  kokoro:
    narrator: af_heart
---
# Unit boundary demo

This is the first paragraph with *moderate emphasis*.

This is the second paragraph ...500ms with an explicit break.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("paragraph_units"))
    parser.add_argument("--voice", default="af_heart")
    args = parser.parse_args()

    options = KokoroRunOptions(
        voice=args.voice,
        speed=1.0,
        use_gpu=False,
        onnx_provider="cpu",
        pause_clause=0.3,
        pause_sentence=0.5,
        pause_paragraph=0.9,
        pause_variance=0.05,
        use_spacy=None,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with KokoroRunner(options, log=lambda message, level="info": print(f"[{level}] {message}")) as runner:
        with runner.prepare_paragraph_units(
            DOCUMENT,
            lang_code="en-us",
            pause_mode="auto",
        ) as prepared:
            for descriptor in prepared.units:
                print(
                    f"unit={descriptor.index} paragraph={descriptor.paragraph_index} "
                    f"chars={descriptor.char_start}:{descriptor.char_end} "
                    f"text={descriptor.text!r}"
                )
            for result in prepared.render():
                path = args.output_dir / f"unit_{result.descriptor.index:04d}.wav"
                try:
                    sf.write(path, np.asarray(result.audio), result.sample_rate)
                    print(f"wrote {path}")
                finally:
                    # The next iteration may release this result; persist/copy it first.
                    result.release_audio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
