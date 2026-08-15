"""Focused lifecycle tests for paragraph conversion with a public fake provider."""

import json
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
from ttsforge.render_units import (
    PARAGRAPH_CONTENT_HASH_SCHEMA,
    PARAGRAPH_UNIT_IDENTITY_SCHEMA,
    stable_hash,
)
from ttsforge.short_sentence_stats import ShortSentenceStats
from ttsforge.ssmd_support import SSMDPolicy


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


class VariableRunner(FakeRunner):
    def __init__(
        self,
        count: int,
        *,
        mismatch_index: int | None = None,
        text_mismatch_index: int | None = None,
        structure_mismatch_index: int | None = None,
    ):
        super().__init__()
        self.count = count
        self.mismatch_index = mismatch_index
        self.text_mismatch_index = text_mismatch_index
        self.structure_mismatch_index = structure_mismatch_index

    def prepare_paragraph_units(self, text, **kwargs):
        descriptors = []
        for index in range(self.count):
            text_hash = f"unit-{index}"
            if index == self.mismatch_index:
                text_hash = f"changed-{index}"
            text = f"Unit {index}"
            if index == self.text_mismatch_index:
                text = f"Edit {index}"
            paragraph_index = index
            if index == self.structure_mismatch_index:
                paragraph_index += 100
            descriptors.append(
                SimpleNamespace(
                    index=index,
                    paragraph_idx=paragraph_index,
                    text=text,
                    text_hash=text_hash,
                    char_start=index * 5,
                    char_end=index * 5 + 5,
                    marker_names=(),
                )
            )
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
        pause_sentence=0.5,
        pause_paragraph=0.9,
        ssmd_policy=SSMDPolicy(emphasis_mode="approximate"),
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

    def cancel_after_first(progress):
        if progress.current_unit == 1:
            first.cancel()

    first = TTSConverter(options, progress_callback=cancel_after_first)
    first._runner = FakeRunner()
    first_result = first.convert_chapters_resumable(chapters, output, resume=False)
    assert not first_result.success

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
    assert [result.descriptor.index for result in first_runner.prepared[0].results] == [
        0
    ]

    logs: list[str] = []
    second = TTSConverter(
        options,
        log_callback=lambda message, level: logs.append(message),
    )
    second_runner = StochasticHashRunner()
    second._runner = second_runner
    second_result = second.convert_chapters_resumable(chapters, output, resume=True)

    assert second_result.success, second_result.error_message
    assert [
        result.descriptor.index for result in second_runner.prepared[0].results
    ] == [1]
    assert any(
        "Resuming paragraph conversion: 1/2 units completed" in message
        and "Next unit: chapter 1, paragraph 2" in message
        for message in logs
    )


def test_paragraph_resume_rejects_changed_saved_ssmd_emphasis(tmp_path: Path):
    output = tmp_path / "book.wav"
    chapters = [Chapter(title="One", content="first", index=0)]
    saved_options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
        ssmd_policy=SSMDPolicy(emphasis_mode="approximate"),
    )

    def cancel_after_first(progress):
        if progress.current_unit == 1:
            first.cancel()

    first = TTSConverter(saved_options, progress_callback=cancel_after_first)
    first._runner = FakeRunner()
    first_result = first.convert_chapters_resumable(chapters, output, resume=False)
    assert not first_result.success
    state_file = next(tmp_path.glob(".Book-*_chapters/state.json"))
    state = ConversionState.load(state_file)
    assert state is not None

    changed = TTSConverter(
        ConversionOptions(
            output_format="wav",
            output_dir=tmp_path,
            title="Book",
            conversion_unit="paragraph",
            ssmd_policy=SSMDPolicy(emphasis_mode="plain"),
        )
    )
    changed._resolved_sentence_models = first._resolved_sentence_models
    changed._resolved_g2p_models = first._resolved_g2p_models
    validation = changed._resume_state_matches(
        state,
        chapters,
        state.source_hash,
        changed._generation_identity(),
        Path(state.work_dir or state_file.parent),
        output_path=output,
    )

    assert validation.reusable is False
    assert validation.reason == "generation-fingerprint-changed"
    assert any(
        difference.path == "ssmd_policy.emphasis_mode"
        for difference in validation.differences
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


def _cancel_after_unit(converter: TTSConverter, unit_number: int):
    def callback(progress):
        if progress.current_unit == unit_number:
            converter.cancel()

    return callback


def _partial_variable_conversion(tmp_path: Path, completed_units: int = 35):
    output = tmp_path / "book.wav"
    options = ConversionOptions(
        output_format="wav",
        output_dir=tmp_path,
        title="Book",
        conversion_unit="paragraph",
    )
    first = TTSConverter(options)
    first.progress_callback = _cancel_after_unit(first, completed_units)
    first._runner = VariableRunner(62)
    result = first.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=False
    )
    assert not result.success
    state_file = next(tmp_path.glob(".Book-*_chapters/state.json"))
    state = ConversionState.load(state_file)
    assert state is not None
    assert state.get_completed_unit_count() == completed_units
    return output, options, state_file, state


def _rewrite_as_schema7_provider_identity(state: ConversionState, state_file: Path):
    state.version = 7
    state.paragraph_unit_identity_schema = 1
    chapter = state.chapters[0]
    for unit in chapter.units:
        provider_hash = f"legacy-provider-{unit.unit_index}"
        unit.content_hash = provider_hash
        unit.render_fingerprint = stable_hash(
            {
                "chapter": chapter.render_fingerprint,
                "unit_index": unit.unit_index,
                "source_paragraph_index": unit.source_paragraph_index,
                "chapter_unit_index": unit.chapter_unit_index,
                "kind": unit.kind,
                "text_hash": provider_hash,
                "char_start": unit.unit_index * 5,
                "char_end": unit.unit_index * 5 + 5,
            }
        )
    state.save(state_file)


def test_paragraph_resume_plan_mismatch_preserves_completed_prefix(tmp_path: Path):
    output, options, state_file, state = _partial_variable_conversion(tmp_path)
    before_state = state_file.read_bytes()
    assert state.paragraphs_dir is not None
    before_output = {
        path.name: path.read_bytes()
        for path in Path(state.paragraphs_dir).iterdir()
        if path.is_file()
    }
    runner = VariableRunner(62, text_mismatch_index=3)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-unit-plan-changed" in (result.error_message or "")
    assert runner.prepared and runner.prepared[0].results == []
    reloaded = ConversionState.load(state_file)
    assert reloaded is not None
    assert reloaded.get_completed_unit_count() == 35
    assert reloaded.get_next_incomplete_unit() is not None
    assert reloaded.get_next_incomplete_unit().sequence_index == 35
    assert state_file.read_bytes() == before_state
    assert {
        path.name: path.read_bytes()
        for path in Path(state.paragraphs_dir).iterdir()
        if path.is_file()
    } == before_output


def test_schema2_resume_ignores_provider_hash_only_changes_and_keeps_audio(
    tmp_path: Path,
):
    output, options, state_file, state = _partial_variable_conversion(
        tmp_path, completed_units=25
    )
    _rewrite_as_schema7_provider_identity(state, state_file)
    assert state.paragraphs_dir is not None
    before_audio = {
        path.name: path.read_bytes()
        for path in Path(state.paragraphs_dir).glob("*.wav")
    }
    runner = VariableRunner(62, mismatch_index=3)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert result.success, result.error_message
    assert runner.prepared[0].results[0].descriptor.index == 25
    upgraded = ConversionState.load(state_file)
    assert upgraded is not None
    assert upgraded.version == 8
    assert upgraded.paragraph_unit_identity_schema == PARAGRAPH_UNIT_IDENTITY_SCHEMA
    assert {
        path.name: path.read_bytes()
        for path in Path(upgraded.paragraphs_dir or "").glob("*.wav")
        if path.name in before_audio
    } == before_audio
    manifest = Path(upgraded.paragraphs_dir or "") / "manifest.json"
    assert json.loads(manifest.read_text())["content_hash_schema"] == (
        PARAGRAPH_CONTENT_HASH_SCHEMA
    )


def test_schema2_resume_rejects_equal_length_prepared_text_change(
    tmp_path: Path,
):
    output, options, state_file, state = _partial_variable_conversion(
        tmp_path, completed_units=5
    )
    before_state = state_file.read_bytes()
    assert state.paragraphs_dir is not None
    before_output = {
        path.name: path.read_bytes()
        for path in Path(state.paragraphs_dir).iterdir()
        if path.is_file()
    }
    runner = VariableRunner(62, text_mismatch_index=3)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-unit-plan-changed" in (result.error_message or "")
    assert runner.prepared[0].results == []
    assert state_file.read_bytes() == before_state
    assert {
        path.name: path.read_bytes()
        for path in Path(state.paragraphs_dir).iterdir()
        if path.is_file()
    } == before_output


def test_schema7_identity_migration_rejects_structural_change(tmp_path: Path):
    output, options, state_file, state = _partial_variable_conversion(
        tmp_path, completed_units=5
    )
    _rewrite_as_schema7_provider_identity(state, state_file)
    before_state = state_file.read_bytes()
    runner = VariableRunner(62, structure_mismatch_index=3)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-unit-plan-changed" in (result.error_message or "")
    assert runner.prepared[0].results == []
    assert state_file.read_bytes() == before_state


def test_schema7_identity_migration_rejects_changed_ssmd_before_inference(
    tmp_path: Path,
):
    output, options, state_file, state = _partial_variable_conversion(
        tmp_path, completed_units=5
    )
    chapter_state = state.chapters[0]
    ssmd_path = Path(state.work_dir or state_file.parent) / (
        chapter_state.ssmd_file or ""
    )
    ssmd_path.write_text(ssmd_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    before_state = state_file.read_bytes()
    runner = VariableRunner(62)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert result.error_message and result.error_message.startswith(
        "paragraph-ssmd-changed"
    )
    assert runner.prepared == []
    assert state_file.read_bytes() == before_state


def test_paragraph_resume_missing_completed_wav_fails_without_rendering(tmp_path: Path):
    output, options, state_file, state = _partial_variable_conversion(tmp_path)
    assert state.paragraphs_dir is not None
    missing = sorted(Path(state.paragraphs_dir).glob("*.wav"))[2]
    missing.unlink()
    before_state = state_file.read_bytes()
    runner = VariableRunner(62)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-audio-missing" in (result.error_message or "")
    assert runner.prepared == []
    assert state_file.read_bytes() == before_state


def test_paragraph_resume_missing_marker_fails_without_rendering(tmp_path: Path):
    output, options, state_file, state = _partial_variable_conversion(tmp_path)
    assert state.paragraphs_dir is not None
    marker = sorted(Path(state.paragraphs_dir).glob("*.markers.json"))[2]
    marker.unlink()
    before_state = state_file.read_bytes()
    runner = VariableRunner(62)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-marker-missing" in (result.error_message or "")
    assert runner.prepared == []
    assert state_file.read_bytes() == before_state


def test_successful_paragraph_resume_starts_at_saved_unit_36(tmp_path: Path):
    output, options, _state_file, _state = _partial_variable_conversion(tmp_path)
    runner = VariableRunner(62)
    progress = []
    resumed = TTSConverter(options, progress_callback=progress.append)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert result.success, result.error_message
    rendered_indices = [item.descriptor.index for item in runner.prepared[0].results]
    assert rendered_indices[0] == 35
    assert progress[0].current_unit == 36
    assert progress[0].current_paragraph == 36
    state_file = next(tmp_path.glob(".Book-*_chapters/state.json"))
    state = ConversionState.load(state_file)
    assert state is not None
    assert state.get_completed_unit_count() == 62


def test_paragraph_resume_allows_suffix_only_replanning(tmp_path: Path):
    output, options, _state_file, _state = _partial_variable_conversion(tmp_path)
    runner = VariableRunner(62, mismatch_index=40)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert result.success, result.error_message
    assert runner.prepared[0].results[0].descriptor.index == 35


def test_paragraph_resume_rejects_noncontiguous_state(tmp_path: Path):
    output, options, state_file, state = _partial_variable_conversion(tmp_path)
    state.chapters[0].units[36].completed = True
    state.save(state_file)
    runner = VariableRunner(62)
    resumed = TTSConverter(options)
    resumed._runner = runner

    result = resumed.convert_chapters_resumable(
        [Chapter(title="One", content="book", index=0)], output, resume=True
    )

    assert not result.success
    assert "paragraph-state-noncontiguous" in (result.error_message or "")
    assert runner.prepared == []
