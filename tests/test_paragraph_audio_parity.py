"""Timeline invariants for paragraph artifacts and ordered concatenation."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from ttsforge.audio_merge import AudioMerger, OrderedAudioInput
from ttsforge.paragraph_output import canonical_filename, finalize_wav
from ttsforge.render_units import PreparedUnitDescriptor, map_descriptors


def test_title_and_body_mapping_uses_expected_paragraph_numbers():
    descriptors = [
        PreparedUnitDescriptor(0, 0, "title", "title", 0, 5),
        PreparedUnitDescriptor(1, 7, "body", "body", 6, 10),
    ]
    titled = map_descriptors(
        descriptors,
        chapter_position=0,
        source_chapter_index=4,
        chapter_fingerprint="chapter",
        sequence_start=0,
        announced_title=True,
    )
    plain = map_descriptors(
        descriptors,
        chapter_position=0,
        source_chapter_index=4,
        chapter_fingerprint="chapter",
        sequence_start=0,
        announced_title=False,
    )
    assert [(unit.kind, unit.paragraph_index) for unit in titled] == [
        ("title", 0),
        ("paragraph", 1),
    ]
    assert [unit.paragraph_index for unit in plain] == [1, 2]
    assert [unit.source_paragraph_index for unit in titled] == [0, 7]
    assert [unit.chapter_unit_index for unit in titled] == [0, 1]
    assert titled[1].to_dict()["source_paragraph_index"] == 7


def test_render_identity_ignores_provider_hash_but_tracks_exact_text():
    stable = SimpleNamespace(
        index=0,
        paragraph_idx=0,
        text="same text",
        text_hash="provider-a",
        char_start=0,
        char_end=9,
    )
    changed_provider = SimpleNamespace(**{**vars(stable), "text_hash": "provider-b"})
    changed_text = SimpleNamespace(**{**vars(stable), "text": "other text"})

    first = map_descriptors(
        [stable],
        chapter_position=0,
        source_chapter_index=0,
        chapter_fingerprint="chapter",
        sequence_start=0,
        announced_title=False,
    )[0]
    provider_changed = map_descriptors(
        [changed_provider],
        chapter_position=0,
        source_chapter_index=0,
        chapter_fingerprint="chapter",
        sequence_start=0,
        announced_title=False,
    )[0]
    text_changed = map_descriptors(
        [changed_text],
        chapter_position=0,
        source_chapter_index=0,
        chapter_fingerprint="chapter",
        sequence_start=0,
        announced_title=False,
    )[0]

    assert first.content_hash == provider_changed.content_hash
    assert first.render_fingerprint == provider_changed.render_fingerprint
    assert first.content_hash != text_changed.content_hash
    assert first.render_fingerprint != text_changed.render_fingerprint


def test_interchapter_silence_is_inside_final_unit_and_not_reinserted(tmp_path: Path):
    directory = tmp_path / "paragraphs"
    directory.mkdir()
    first = directory / canonical_filename(
        sequence_index=1,
        source_chapter_index=0,
        paragraph_index=1,
        kind="paragraph",
        chapter_title="One",
    )
    second = directory / canonical_filename(
        sequence_index=2,
        source_chapter_index=1,
        paragraph_index=1,
        kind="paragraph",
        chapter_title="Two",
    )
    first_duration = finalize_wav(
        samples=np.ones(240, dtype=np.float32),
        sample_rate=24000,
        destination=first,
        trailing_chapter_silence=0.02,
    )
    second_duration = finalize_wav(
        samples=np.ones(240, dtype=np.float32),
        sample_rate=24000,
        destination=second,
    )
    output = tmp_path / "merged.wav"
    AudioMerger(log=lambda message, level="info": None).merge_ordered_wavs(
        [
            OrderedAudioInput(first, 0, 0, "One", first_duration, 0.01, 0.02),
            OrderedAudioInput(second, 1, 1, "Two", second_duration, 0.01, 0.0),
        ],
        output,
    )
    samples, _ = sf.read(output, dtype="float32")
    assert len(samples) == 240 + 480 + 240
