"""Runtime helpers for rendering PyKokoro prepared units.

This module owns the in-memory lifecycle between a prepared PyKokoro result and
an output sink.  It intentionally contains no audiobook state or Readio
imports; callers decide how completed units are persisted.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


class AudioSink(Protocol):
    """Destination for rendered audio chunks."""

    def write(self, audio: np.ndarray, sample_rate: int) -> None: ...

    def close(self) -> None: ...


class FinishableAudioSink(AudioSink, Protocol):
    """Optional sink extension used when a caller must wait for playback."""

    def finish(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RenderSummary:
    """Aggregate metadata for one prepared-unit render."""

    sample_rate: int
    sample_count: int
    channels: int
    markers: tuple[dict[str, Any], ...] = ()
    document_metadata: Mapping[str, Any] = field(default_factory=dict)


class PlaybackSink:
    """Persistent PyKokoro playback sink with lazy optional dependency loading."""

    def __init__(
        self,
        *,
        queue_size: int = 2,
        device: int | str | None = None,
        player_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.queue_size = queue_size
        self.device = device
        self._player_factory = player_factory
        self._player: Any | None = None
        self._sample_rate: int | None = None
        self._channels: int | None = None

    @property
    def player(self) -> Any | None:
        return self._player

    def _make_player(self, sample_rate: int, channels: int) -> Any:
        factory = self._player_factory
        if factory is None:
            try:
                from .pykokoro_adapter import get_sound_device_player

                SoundDevicePlayer = get_sound_device_player()
            except ImportError as exc:
                raise RuntimeError(
                    "Audio playback requires the optional dependency "
                    "'sounddevice'. Install with: pip install ttsforge[audio]."
                ) from exc
            factory = SoundDevicePlayer
        kwargs: dict[str, Any] = {"queue_size": self.queue_size, "channels": channels}
        if self.device is not None:
            kwargs["device"] = self.device
        player = factory(sample_rate, **kwargs)
        player.start()
        return player

    def write(self, audio: np.ndarray, sample_rate: int) -> None:
        array = _validate_audio(audio)
        channels = 1 if array.ndim == 1 else int(array.shape[1])
        if self._player is None:
            self._player = self._make_player(sample_rate, channels)
            self._sample_rate = sample_rate
            self._channels = channels
        elif (sample_rate, channels) != (self._sample_rate, self._channels):
            raise ValueError(
                "playback audio format changed: "
                f"expected {self._sample_rate} Hz/{self._channels} channels, "
                f"got {sample_rate} Hz/{channels} channels"
            )
        self._player.submit(array)

    def finish(self) -> None:
        if self._player is not None:
            self._player.drain()

    def close(self) -> None:
        player, self._player = self._player, None
        if player is not None:
            player.close()

    def write_silence(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("silence duration must be non-negative")
        if seconds == 0:
            return
        if self._sample_rate is None or self._channels is None:
            raise RuntimeError("cannot write silence before playback format is known")
        frames = round(seconds * self._sample_rate)
        if frames:
            shape = (frames,) if self._channels == 1 else (frames, self._channels)
            self.write(np.zeros(shape, dtype=np.float32), self._sample_rate)


def _validate_audio(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio)
    if array.ndim not in (1, 2):
        raise ValueError("rendered audio must be a 1D mono or 2D channel array")
    if array.shape[0] == 0:
        raise ValueError("rendered audio must not be empty")
    if array.ndim == 2 and array.shape[1] <= 0:
        raise ValueError("rendered audio must have at least one channel")
    return array


def _result_audio(result: Any) -> tuple[np.ndarray, int, int]:
    audio = _validate_audio(np.asarray(result.audio))
    sample_rate = int(result.sample_rate)
    if sample_rate <= 0:
        raise ValueError("rendered audio sample_rate must be positive")
    channels = 1 if audio.ndim == 1 else int(audio.shape[1])
    return audio, sample_rate, channels


def _rebased_markers(
    result: Any, sample_offset: int, sample_rate: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for marker in getattr(result, "markers", ()) or ():
        record = (
            dict(marker)
            if isinstance(marker, Mapping)
            else {
                "name": str(getattr(marker, "name", "")),
                "char_offset": int(getattr(marker, "char_offset", 0)),
                "sample_offset": int(getattr(marker, "sample_offset", 0)),
            }
        )
        local_offset = int(record.get("sample_offset", 0))
        absolute_offset = sample_offset + local_offset
        record["sample_offset"] = absolute_offset
        record["time_s"] = absolute_offset / sample_rate
        records.append(record)
    return records


def render_prepared(
    prepared: Any,
    sink: AudioSink,
    *,
    indices: Sequence[int] | None = None,
    on_unit_complete: Callable[[int], None] | None = None,
) -> RenderSummary:
    """Render selected prepared units into ``sink`` with deterministic ownership.

    A unit is complete only after its audio has been accepted by the sink.  The
    PyKokoro result is released in ``finally`` even when validation or writing
    fails, and markers are rebased to the aggregate stream offset.
    """
    selected = set(indices) if indices is not None else None
    sample_rate: int | None = None
    channels: int | None = None
    sample_count = 0
    markers: list[dict[str, Any]] = []
    completed_indices: set[int] = set()

    for fallback_index, result in enumerate(prepared.render(skip_indices=())):
        descriptor = getattr(result, "descriptor", None)
        index = int(getattr(descriptor, "index", fallback_index))
        if selected is not None and index not in selected:
            release = getattr(result, "release_audio", None)
            if callable(release):
                release()
            continue
        try:
            audio, result_rate, result_channels = _result_audio(result)
            if sample_rate is None:
                sample_rate, channels = result_rate, result_channels
            elif (result_rate, result_channels) != (sample_rate, channels):
                raise ValueError(
                    "rendered audio format changed: "
                    f"expected {sample_rate} Hz/{channels} channels, "
                    f"got {result_rate} Hz/{result_channels} channels"
                )
            assert sample_rate is not None and channels is not None
            unit_markers = _rebased_markers(result, sample_count, sample_rate)
            sink.write(audio, result_rate)
            markers.extend(unit_markers)
            sample_count += int(audio.shape[0])
            completed_indices.add(index)
            if on_unit_complete is not None:
                on_unit_complete(index)
        finally:
            release = getattr(result, "release_audio", None)
            if callable(release):
                release()

    if sample_rate is None:
        sample_rate = 0
        channels = 0
    metadata = getattr(prepared, "document_metadata", {})
    return RenderSummary(
        sample_rate=sample_rate,
        sample_count=sample_count,
        channels=channels or 0,
        markers=tuple(markers),
        document_metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )
