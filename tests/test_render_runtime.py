from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from ttsforge.render_runtime import PlaybackSink, render_prepared


class FakeResult:
    def __init__(
        self, index: int, value: float, *, rate: int = 24000, channels: int = 1
    ):
        self.descriptor = SimpleNamespace(index=index)
        self.audio = (
            np.full((4, channels), value, dtype=np.float32)
            if channels > 1
            else np.full(4, value, dtype=np.float32)
        )
        self.sample_rate = rate
        self.markers = [{"name": f"m{index}", "sample_offset": 1}]
        self.released = False

    def release_audio(self) -> None:
        self.released = True
        self.audio = np.empty(0, dtype=np.float32)


class FakePrepared:
    def __init__(self, results):
        self.results = results
        self.document_metadata = {"title": "Test"}

    def render(self, *, skip_indices=()):
        yield from self.results


class RecordingSink:
    def __init__(self, failure: BaseException | None = None):
        self.writes = []
        self.failure = failure

    def write(self, audio, sample_rate):
        if self.failure:
            raise self.failure
        self.writes.append((audio.copy(), sample_rate))

    def close(self):
        pass


def test_render_prepared_releases_after_write_and_rebases_markers():
    results = [FakeResult(0, 1), FakeResult(1, 2)]
    sink = RecordingSink()
    completed = []

    summary = render_prepared(
        FakePrepared(results), sink, on_unit_complete=completed.append
    )

    assert completed == [0, 1]
    assert all(result.released for result in results)
    assert summary.sample_rate == 24000
    assert summary.sample_count == 8
    assert [marker["sample_offset"] for marker in summary.markers] == [1, 5]
    assert [marker["time_s"] for marker in summary.markers] == pytest.approx(
        [1 / 24000, 5 / 24000]
    )


def test_render_prepared_releases_when_sink_fails_and_does_not_complete():
    result = FakeResult(0, 1)
    sink = RecordingSink(RuntimeError("sink failed"))
    completed = []

    with pytest.raises(RuntimeError, match="sink failed"):
        render_prepared(FakePrepared([result]), sink, on_unit_complete=completed.append)

    assert result.released
    assert completed == []


def test_render_prepared_rejects_format_changes():
    first = FakeResult(0, 1, rate=24000)
    second = FakeResult(1, 2, rate=22050)

    with pytest.raises(ValueError, match="format changed"):
        render_prepared(FakePrepared([first, second]), RecordingSink())

    assert first.released and second.released


def test_playback_sink_uses_one_persistent_player_and_drains():
    player = MagicMock()
    factory = MagicMock(return_value=player)
    sink = PlaybackSink(player_factory=factory)

    sink.write(np.zeros(4, dtype=np.float32), 24000)
    sink.write(np.zeros(4, dtype=np.float32), 24000)
    sink.finish()
    sink.close()

    factory.assert_called_once_with(24000, queue_size=2, channels=1)
    player.start.assert_called_once_with()
    assert player.submit.call_count == 2
    player.drain.assert_called_once_with()
    player.close.assert_called_once_with()


def test_playback_sink_rejects_format_change():
    sink = PlaybackSink(player_factory=MagicMock(return_value=MagicMock()))
    sink.write(np.zeros(2, dtype=np.float32), 24000)
    with pytest.raises(ValueError, match="format changed"):
        sink.write(np.zeros(2, dtype=np.float32), 22050)
