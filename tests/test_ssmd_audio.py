from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

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
    assert np.allclose(audio, 0.5, atol=1e-4)


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
