"""Focused synchronization tests for the streaming player."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

import ttsforge.audio_player as audio_player
from ttsforge.audio_player import PlaybackPosition, StreamingAudioPlayer


def _drain(player: StreamingAudioPlayer, finished: threading.Event) -> None:
    while not finished.is_set() or not player._audio_queue.empty():
        try:
            chunk = player._audio_queue.get(timeout=0.05)
        except Exception:
            continue
        if chunk is not None:
            with player._queue_not_full:
                player._queued_samples -= len(chunk)
                player._queue_not_full.notify_all()


def test_oversized_chunk_is_split_and_does_not_deadlock() -> None:
    player = StreamingAudioPlayer(
        sample_rate=1000, buffer_size=2, max_buffer_seconds=0.01
    )
    finished = threading.Event()
    drain_thread = threading.Thread(target=_drain, args=(player, finished))
    drain_thread.start()
    producer = threading.Thread(
        target=player.add_audio, args=(np.ones(25, dtype=np.float32),)
    )
    producer.start()
    producer.join(timeout=1)
    finished.set()
    drain_thread.join(timeout=1)
    assert not producer.is_alive()
    assert player._queued_samples == 0


def test_stop_releases_producer_waiting_for_capacity() -> None:
    player = StreamingAudioPlayer(
        sample_rate=1000, buffer_size=2, max_buffer_seconds=0.01
    )
    player.add_audio(np.ones(10, dtype=np.float32))
    producer = threading.Thread(
        target=player.add_audio, args=(np.ones(10, dtype=np.float32),)
    )
    producer.start()
    time.sleep(0.05)
    player.stop()
    producer.join(timeout=1)
    assert not producer.is_alive()
    assert player._queued_samples == 0


def test_callback_handles_mono_stereo_end_and_empty_queue() -> None:
    played: list[int] = []
    player = StreamingAudioPlayer(
        sample_rate=10, channels=1, buffer_size=4, on_chunk_played=played.append
    )
    player.add_audio(np.arange(3, dtype=np.float32))
    output = np.full((5, 1), -1.0, dtype=np.float32)
    player._audio_callback(output, 5, None, None)
    assert output[:, 0].tolist() == [0.0, 1.0, 2.0, 0.0, 0.0]
    assert played == [1]
    assert player.chunks_played == 1
    assert player.duration_played == pytest.approx(0.3)

    stereo = StreamingAudioPlayer(sample_rate=10, channels=2, buffer_size=4)
    stereo.add_audio(np.array([0.25, 0.5], dtype=np.float32))
    stereo_output = np.zeros((2, 2), dtype=np.float32)
    stereo._audio_callback(stereo_output, 2, None, None)
    np.testing.assert_array_equal(stereo_output, [[0.25, 0.25], [0.5, 0.5]])

    player.finish_adding()
    end_output = np.full((2, 1), -1.0, dtype=np.float32)
    player._audio_callback(end_output, 2, None, None)
    assert player.wait_until_done(0)


def test_callback_silences_when_paused_or_stopped() -> None:
    player = StreamingAudioPlayer(buffer_size=4)
    player.add_audio(np.ones(4, dtype=np.float32))
    output = np.full((4, 1), 2.0, dtype=np.float32)

    player.pause()
    player._audio_callback(output, 4, None, None)
    assert np.all(output == 0)
    assert player.is_paused and not player.is_playing

    player.resume()
    assert player.is_playing is False
    assert player.toggle_pause() is True
    assert player.toggle_pause() is False
    player.request_stop()
    player._audio_callback(output, 4, None, None)
    assert np.all(output == 0)
    assert player.should_stop


def test_start_stop_uses_optional_sounddevice(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_stream = MagicMock()
    fake_sd = MagicMock(OutputStream=MagicMock(return_value=fake_stream))
    monkeypatch.setattr(audio_player, "_import_sounddevice", lambda: fake_sd)
    player = StreamingAudioPlayer(sample_rate=8000, channels=2, buffer_size=128)

    player.start()
    player.start()
    fake_sd.OutputStream.assert_called_once()
    fake_stream.start.assert_called_once()
    assert player.is_playing
    player.stop()
    fake_stream.stop.assert_called_once()
    fake_stream.close.assert_called_once()
    assert not player.is_playing


def test_queue_lifecycle_and_input_normalization() -> None:
    player = StreamingAudioPlayer(buffer_size=4)
    player.add_audio(np.empty(0, dtype=np.float64))
    player.add_audio(np.ones((2, 2), dtype=np.float64))
    chunk = player._audio_queue.get_nowait()
    assert chunk.dtype == np.float32
    assert chunk.shape == (4,)
    player.finish_adding()
    assert player._audio_queue.get_nowait() is None
    assert player.wait_until_done(0) is False
    player.request_stop()
    assert player.wait_until_done(0)


def test_playback_position_persistence_and_invalid_data(tmp_path) -> None:
    position = PlaybackPosition("book.epub", 2, 4, timestamp=12.5)
    assert PlaybackPosition.from_dict(position.to_dict()) == position
    assert (
        PlaybackPosition.from_dict(
            {"file_path": "x", "chapter_index": 0, "segment_index": 1}
        ).file_path
        == "x"
    )

    audio_player.save_playback_position(position, tmp_path)
    assert audio_player.load_playback_position(tmp_path) == position
    path = tmp_path / "reading_position.json"
    path.write_text("not json", encoding="utf-8")
    assert audio_player.load_playback_position(tmp_path) is None
    audio_player.clear_playback_position(tmp_path)
    assert not path.exists()


def test_sounddevice_error_and_blocking_playback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audio_player,
        "_import_sounddevice",
        lambda: (_ for _ in ()).throw(ImportError("missing")),
    )
    with pytest.raises(ImportError):
        audio_player._import_sounddevice()

    fake_sd = MagicMock()
    monkeypatch.setattr(audio_player, "_import_sounddevice", lambda: fake_sd)
    audio = np.zeros(4, dtype=np.float32)
    audio_player.play_audio_blocking(audio, 8000)
    fake_sd.play.assert_called_once_with(audio, 8000)
    fake_sd.wait.assert_called_once_with()
