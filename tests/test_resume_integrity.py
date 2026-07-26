"""Regression coverage for conservative v2 resume matching."""

from pathlib import Path

import numpy as np
import soundfile as sf

from ttsforge.conversion import (
    Chapter,
    ChapterState,
    ConversionOptions,
    ConversionState,
    TTSConverter,
    _canonical_fingerprint,
    _hash_content,
)
from ttsforge.phoneme_conversion import (
    PhonemeChapterState,
    PhonemeConversionOptions,
    PhonemeConversionState,
    PhonemeConverter,
)
from ttsforge.phonemes import PhonemeBook, PhonemeChapter, PhonemeSegment


def _text_state(
    converter: TTSConverter, chapter: Chapter, work_dir: Path
) -> ConversionState:
    generation = converter._generation_fingerprint()
    content_hash = _hash_content(chapter.content)
    render = _canonical_fingerprint(
        {
            "generation": generation,
            "source_index": chapter.index,
            "title": chapter.title,
            "content_sha256": content_hash,
        }
    )
    return ConversionState(
        version=2,
        source_hash="source",
        source_selection=[chapter.index],
        generation_fingerprint=generation,
        work_dir=str(work_dir),
        chapters=[
            ChapterState(
                index=chapter.index,
                title=chapter.title,
                content_hash=content_hash,
                render_fingerprint=render,
                completed=True,
                audio_file="chapter.wav",
            )
        ],
    )


def test_text_resume_rejects_changed_content_settings_and_legacy_state(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "chapter.wav"
    sf.write(audio_path, np.zeros(2400, dtype=np.float32), 24000)
    chapter = Chapter(title="Chapter", content="Original", index=4)
    converter = TTSConverter(ConversionOptions(title="Book"))
    state = _text_state(converter, chapter, tmp_path)

    assert converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )
    assert not converter._resume_state_matches(
        state,
        [Chapter(title="Chapter", content="Changed", index=4)],
        "source",
        converter._generation_fingerprint(),
        tmp_path,
    )
    changed_converter = TTSConverter(ConversionOptions(title="Book", voice="af_heart"))
    assert not changed_converter._resume_state_matches(
        state,
        [chapter],
        "source",
        changed_converter._generation_fingerprint(),
        tmp_path,
    )
    state.version = 1
    assert not converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )


def test_text_resume_rejects_missing_or_corrupt_audio(tmp_path: Path) -> None:
    chapter = Chapter(title="Chapter", content="Original", index=0)
    converter = TTSConverter(ConversionOptions(title="Book"))
    state = _text_state(converter, chapter, tmp_path)
    assert not converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )


def test_phoneme_resume_rejects_changed_book_content(tmp_path: Path) -> None:
    chapter = PhonemeChapter(
        title="Chapter",
        chapter_index=0,
        segments=[PhonemeSegment(text="hello", phonemes="hello", tokens=[1])],
    )
    book = PhonemeBook(title="Book", chapters=[chapter])
    options = PhonemeConversionOptions()
    converter = PhonemeConverter(book, options)
    generation = converter._generation_fingerprint()
    content_hash = converter._chapter_content_hash(chapter)
    render = _canonical_fingerprint(
        {
            "generation": generation,
            "source_index": 0,
            "title": chapter.title,
            "content_sha256": content_hash,
        }
    )
    state = PhonemeConversionState(
        version=2,
        source_hash=_canonical_fingerprint(book.to_dict()),
        selected_chapters=[0],
        generation_fingerprint=generation,
        chapters=[
            PhonemeChapterState(
                index=0,
                title=chapter.title,
                segment_count=1,
                content_hash=content_hash,
                render_fingerprint=render,
                completed=False,
            )
        ],
    )
    assert converter._resume_state_matches(
        state, [chapter], [0], state.source_hash, generation, tmp_path
    )
    changed = PhonemeChapter(
        title="Chapter",
        chapter_index=0,
        segments=[PhonemeSegment(text="changed", phonemes="changed", tokens=[1])],
    )
    changed_book = PhonemeBook(title="Book", chapters=[changed])
    changed_converter = PhonemeConverter(changed_book, options)
    assert not changed_converter._resume_state_matches(
        state,
        [changed],
        [0],
        _canonical_fingerprint(changed_book.to_dict()),
        changed_converter._generation_fingerprint(),
        tmp_path,
    )
