"""Focused lifecycle tests for paragraph conversion with a public fake provider."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from ttsforge.conversion import (
    Chapter,
    ConversionOptions,
    ConversionState,
    TTSConverter,
)
from ttsforge.short_sentence_stats import ShortSentenceStats


class FakeResult:
    def __init__(self, descriptor, value: float):
        self.descriptor = descriptor
        self.audio = np.full(240, value, dtype=np.float32)
        self.sample_rate = 24000
        self.markers = []
        self.document_metadata = {}
        self.trace = SimpleNamespace(warnings=[])
        self.released = False

    def release_audio(self):
        self.released = True
        self.audio = np.empty(0, dtype=np.float32)


class FakePrepared:
    def __init__(self, descriptors):
        self.units = descriptors
        self.document_metadata = {}
        self.diagnostics = ()
        self.results: list[FakeResult] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def render(self, *, skip_indices=()):
        for descriptor in self.units:
            if descriptor.index in set(skip_indices):
                continue
            result = FakeResult(descriptor, descriptor.index + 1)
            self.results.append(result)
            yield result


class FakeRunner:
    def __init__(self):
        self.prepared: list[FakePrepared] = []

    def prepare_paragraph_units(self, text, **kwargs):
        descriptors = [
            SimpleNamespace(
                index=0,
                paragraph_idx=0,
                text="Title",
                text_hash="title-hash",
                char_start=0,
                char_end=5,
                marker_names=(),
            ),
            SimpleNamespace(
                index=1,
                paragraph_idx=1,
                text="Body",
                text_hash="body-hash",
                char_start=6,
                char_end=10,
                marker_names=(),
            ),
        ]
        prepared = FakePrepared(descriptors)
        self.prepared.append(prepared)
        return prepared

    def get_short_sentence_stats(self):
        return ShortSentenceStats()


class StochasticHashRunner(FakeRunner):
    """Model PyKokoro's unstable descriptor identity when no seed is given."""

    _unseeded_preparations = 0

    def __init__(self):
        super().__init__()
        self.random_seeds: list[int | None] = []

    def prepare_paragraph_units(self, text, **kwargs):
        random_seed = kwargs.get("random_seed")
        self.random_seeds.append(random_seed)
        if random_seed is None:
            type(self)._unseeded_preparations += 1
            identity = f"unseeded-{type(self)._unseeded_preparations}"
        else:
            identity = f"seeded-{random_seed}"
        descriptors = [
            SimpleNamespace(
                index=0,
                paragraph_idx=0,
                text="Title",
                text_hash=f"title-{identity}",
                char_start=0,
                char_end=5,
                marker_names=(),
            ),
            SimpleNamespace(
                index=1,
                paragraph_idx=1,
                text="Body",
                text_hash=f"body-{identity}",
                char_start=6,
                char_end=10,
                marker_names=(),
            ),
        ]
        prepared = FakePrepared(descriptors)
        self.prepared.append(prepared)
        return prepared


def test_paragraph_conversion_writes_ordered_units_and_merges(tmp_path: Path):
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
        silence_between_chapters=0.01,
    )
    converter = TTSConverter(options)
    fake = FakeRunner()
    converter._runner = fake
    chapters = [
        Chapter(title="One", content="first", index=0),
        Chapter(title="Two", content="second", index=1),
    ]

    result = converter.convert_chapters_resumable(chapters, output, resume=False)

    assert result.success, result.error_message
    assert result.conversion_unit == "paragraph"
    assert result.paragraphs_dir is not None
    files = sorted(result.paragraphs_dir.glob("*.wav"))
    assert [path.name[:8] for path in files] == [
        "00000001",
        "00000002",
        "00000003",
        "00000004",
    ]
    assert result.paragraphs_dir.joinpath("manifest.json").is_file()
    assert result.paragraphs_dir.joinpath("playlist.m3u8").is_file()
    merged, rate = sf.read(output, dtype="float32")
    assert rate == 24000
    assert len(merged) == sum(sf.info(path).frames for path in files)
    assert all(item.released for prepared in fake.prepared for item in prepared.results)


def test_complete_paragraph_state_supports_merge_only_resume(tmp_path: Path):
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
    )
    first = TTSConverter(options)
    first_fake = FakeRunner()
    first._runner = first_fake
    chapters = [Chapter(title="One", content="first", index=0)]
    assert first.convert_chapters_resumable(chapters, output, resume=False).success
    output.unlink()

    class NoInferenceRunner(FakeRunner):
        def prepare_paragraph_units(self, text, **kwargs):
            raise AssertionError("merge-only resume initialized inference")

    second = TTSConverter(options)
    second._runner = NoInferenceRunner()
    result = second.convert_chapters_resumable(chapters, output, resume=True)
    assert result.success, result.error_message
    assert output.is_file()


def test_resumed_progress_includes_retained_unit_characters(tmp_path: Path):
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
    )
    chapters = [Chapter(title="One", content="first", index=0)]
    first = TTSConverter(options)
    first._runner = FakeRunner()
    first_result = first.convert_chapters_resumable(chapters, output, resume=False)
    assert first_result.success
    assert first_result.paragraphs_dir is not None
    files = sorted(first_result.paragraphs_dir.glob("*.wav"))
    assert len(files) == 2
    files[-1].unlink()
    files[-1].with_name(files[-1].name + ".markers.json").unlink()

    progress = []
    resumed = TTSConverter(options, progress_callback=progress.append)
    resumed._runner = FakeRunner()
    result = resumed.convert_chapters_resumable(chapters, output, resume=True)

    assert result.success, result.error_message
    assert progress
    assert progress[-1].chars_processed == len("Title") + len("Body")


def test_unseeded_stochastic_hash_does_not_restart_saved_prefix(
    tmp_path: Path,
):
    """A new process must reuse the effective preparation seed on resume."""
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
    )
    chapters = [Chapter(title="One", content="first", index=0)]

    def cancel_after_first(progress):
        if progress.current_unit == 1:
            first._cancelled = True

    first = TTSConverter(options, progress_callback=cancel_after_first)
    first_runner = StochasticHashRunner()
    first._runner = first_runner
    first_result = first.convert_chapters_resumable(chapters, output, resume=False)
    assert not first_result.success
    assert [result.descriptor.index for result in first_runner.prepared[0].results] == [0]

    logs: list[str] = []
    second = TTSConverter(
        options,
        log_callback=lambda message, level: logs.append(message),
    )
    second_runner = StochasticHashRunner()
    second._runner = second_runner
    second_result = second.convert_chapters_resumable(chapters, output, resume=True)

    assert second_result.success, second_result.error_message
    assert [result.descriptor.index for result in second_runner.prepared[0].results] == [1]
    assert any(
        "Resuming paragraph conversion: 1/2 units completed" in message
        and "Next unit: chapter 1, paragraph 2" in message
        for message in logs
    )


def test_seed_is_saved_before_preparation_failure(tmp_path: Path):
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
    )

    class FailingRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.random_seeds: list[int | None] = []

        def prepare_paragraph_units(self, text, **kwargs):
            self.random_seeds.append(kwargs.get("random_seed"))
            raise RuntimeError("preparation failed")

    runner = FailingRunner()
    converter = TTSConverter(options)
    converter._runner = runner
    result = converter.convert_chapters_resumable(
        [Chapter(title="One", content="first", index=0)],
        output,
        resume=False,
    )

    assert not result.success
    assert len(runner.random_seeds) == 1
    assert runner.random_seeds[0] is not None
    state_file = next(tmp_path.glob(".Book-*_chapters/state.json"))
    state = ConversionState.load(state_file)
    assert state is not None
    assert state.chapters[0].paragraph_random_seed == runner.random_seeds[0]

    retry_runner = StochasticHashRunner()
    retry = TTSConverter(options)
    retry._runner = retry_runner
    retry_result = retry.convert_chapters_resumable(
        [Chapter(title="One", content="first", index=0)],
        output,
        resume=True,
    )
    assert retry_result.success, retry_result.error_message
    assert retry_runner.random_seeds == [runner.random_seeds[0]]
