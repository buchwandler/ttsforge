"""Short-sentence usage statistics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pykokoro.short_sentence_handler import SHORT_SENTENCE_META_KEY


@dataclass
class ShortSentenceStats:
    """Counts short-sentence handling outcomes for generated audio."""

    total: int = 0
    retries: int = 0
    fallbacks: int = 0

    def add_audio_result(self, result: Any) -> None:
        self.add_segments(getattr(result, "phoneme_segments", []))

    def add_segments(self, segments: list[Any]) -> None:
        for segment in segments:
            metadata = getattr(segment, "ssmd_metadata", None)
            if not isinstance(metadata, dict):
                continue
            short_sentence = metadata.get(SHORT_SENTENCE_META_KEY)
            if not isinstance(short_sentence, dict):
                continue

            self.total += 1
            self.retries += _int_value(short_sentence.get("retry_attempts"))
            fallback_used = short_sentence.get("fallback_used")
            if fallback_used == "wrap":
                self.fallbacks += 1

    def add(self, other: ShortSentenceStats) -> None:
        self.total += other.total
        self.retries += other.retries
        self.fallbacks += other.fallbacks

    def copy(self) -> ShortSentenceStats:
        return ShortSentenceStats(
            total=self.total,
            retries=self.retries,
            fallbacks=self.fallbacks,
        )


def format_short_sentence_stats(stats: ShortSentenceStats) -> str:
    return (
        f"total={stats.total}, retries={stats.retries}, "
        f"fallbacks={stats.fallbacks}"
    )


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
