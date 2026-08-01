"""Tests for the released AudioSig compatibility API used by TTSForge."""

from audiosig import downmix_to_mono, generate_silence


def test_released_audiosig_compatibility_functions_are_importable() -> None:
    assert callable(downmix_to_mono)
    assert callable(generate_silence)
