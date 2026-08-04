"""Tests for no-gap ordered paragraph merging."""

from pathlib import Path

import numpy as np
import soundfile as sf

from ttsforge.audio_merge import AudioMerger, OrderedAudioInput


def _write(path: Path, value: float, frames: int = 240) -> None:
    sf.write(path, np.full(frames, value, dtype=np.float32), 24000)


def test_ordered_wav_merge_inserts_no_additional_gaps(tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "merged.wav"
    _write(first, 0.1)
    _write(second, 0.2)

    merger = AudioMerger(log=lambda message, level="info": None)
    merger.merge_ordered_wavs(
        [
            OrderedAudioInput(first, 0, 0, "One", 0.01, 0.01, 0.0),
            OrderedAudioInput(second, 1, 0, "One", 0.01, 0.01, 0.0),
        ],
        output,
    )

    samples, rate = sf.read(output, dtype="float32")
    assert rate == 24000
    assert len(samples) == 480
    assert np.allclose(samples[:240], 0.1, atol=1 / 32768)
    assert np.allclose(samples[240:], 0.2, atol=1 / 32768)
