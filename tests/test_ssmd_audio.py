from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
from audiosig import AudioShapeError

from ttsforge.ssmd_audio import LocalSSMDAudioResolver


def test_local_resolver_resolves_relative_audio_and_downmixes(tmp_path) -> None:
    audio_path = tmp_path / "clip.wav"
    stereo = np.column_stack(
        [np.ones(2400, dtype=np.float32), np.zeros(2400, dtype=np.float32)]
    )
    sf.write(audio_path, stereo, 24000)

    audio, sample_rate = LocalSSMDAudioResolver(tmp_path).resolve("clip.wav")

    assert sample_rate == 24000
    assert audio.shape == (2400,)
    assert audio.dtype == np.float32
    assert np.allclose(audio, 0.5, atol=1e-4)


def test_local_resolver_preserves_mono_audio_and_sample_rate(tmp_path) -> None:
    audio_path = tmp_path / "mono.wav"
    mono = np.linspace(-1.0, 1.0, 1200, dtype=np.float32)
    sf.write(audio_path, mono, 16000)

    audio, sample_rate = LocalSSMDAudioResolver(tmp_path).resolve("mono.wav")

    assert sample_rate == 16000
    assert audio.dtype == np.float32
    assert audio.shape == mono.shape
    assert np.allclose(audio, mono, atol=1e-4)


def test_local_resolver_downmixes_all_channels_arithmetic_mean(tmp_path) -> None:
    audio_path = tmp_path / "three-channel.wav"
    three_channel = np.column_stack(
        [
            np.full(1200, -1.0, dtype=np.float32),
            np.full(1200, 0.5, dtype=np.float32),
            np.full(1200, 1.0, dtype=np.float32),
        ]
    )
    sf.write(audio_path, three_channel, 22050)

    audio, sample_rate = LocalSSMDAudioResolver(tmp_path).resolve("three-channel.wav")

    assert sample_rate == 22050
    assert audio.dtype == np.float32
    assert audio.shape == (1200,)
    assert np.allclose(audio, 1 / 6, atol=1e-4)


def test_audio_shape_error_keeps_resolver_value_error_contract(
    tmp_path, monkeypatch
) -> None:
    class FakeSoundFile:
        frames = 1
        samplerate = 24000

        def __init__(self, data):
            del data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self, *, dtype, always_2d):
            del dtype, always_2d
            return np.array(1.0, dtype=np.float32)

    (tmp_path / "invalid.wav").write_bytes(b"not-a-real-file")
    monkeypatch.setattr("ttsforge.ssmd_audio.sf.SoundFile", FakeSoundFile)

    with pytest.raises(AudioShapeError):
        LocalSSMDAudioResolver(tmp_path).resolve("invalid.wav")


def test_local_resolver_enforces_allowed_root_and_byte_limit(tmp_path) -> None:
    document_dir = tmp_path / "document"
    document_dir.mkdir()
    outside = tmp_path / "outside.wav"
    sf.write(outside, np.zeros(2400, dtype=np.float32), 24000)

    resolver = LocalSSMDAudioResolver(
        document_dir, allowed_root=document_dir, max_bytes=10
    )
    with pytest.raises(PermissionError):
        resolver.resolve(str(outside))

    inside = document_dir / "inside.wav"
    sf.write(inside, np.zeros(2400, dtype=np.float32), 24000)
    with pytest.raises(ValueError, match="byte limit"):
        resolver.resolve("inside.wav")


def test_remote_audio_is_disabled_and_non_https_is_rejected(tmp_path) -> None:
    resolver = LocalSSMDAudioResolver(tmp_path)

    with pytest.raises(PermissionError, match="disabled"):
        resolver.resolve("https://example.com/audio.wav")

    enabled = LocalSSMDAudioResolver(tmp_path, allow_remote=True)
    with pytest.raises(PermissionError, match="HTTPS"):
        enabled.resolve("http://example.com/audio.wav")
