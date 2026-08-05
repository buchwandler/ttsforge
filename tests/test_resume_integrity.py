"""Regression coverage for conservative v2 resume matching."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ttsforge.conversion import (
    Chapter,
    ChapterState,
    ConversionOptions,
    ConversionState,
    ResumeValidation,
    TTSConverter,
    _canonical_fingerprint,
    _chapter_render_fingerprint,
    _hash_content,
    discover_resume_candidate,
    resolve_conversion_workspace,
)
from ttsforge.phoneme_conversion import (
    PhonemeChapterState,
    PhonemeConversionOptions,
    PhonemeConversionState,
    PhonemeConverter,
)
from ttsforge.phonemes import PhonemeBook, PhonemeChapter, PhonemeSegment
from ttsforge.prosody_support import ProsodyPolicy
from ttsforge.render_units import renderer_contract_payload


def _text_state(
    converter: TTSConverter, chapter: Chapter, work_dir: Path
) -> ConversionState:
    generation = converter._generation_fingerprint()
    content_hash = _hash_content(chapter.content)
    render = _chapter_render_fingerprint(chapter, generation)
    return ConversionState(
        version=4,
        source_hash="source",
        onnx_provider=converter.options.effective_onnx_provider(),
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

    validation = converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )
    assert validation.reusable is True
    assert validation.reason is None

    validation = converter._resume_state_matches(
        state,
        [Chapter(title="Chapter", content="Changed", index=4)],
        "source",
        converter._generation_fingerprint(),
        tmp_path,
    )
    assert validation.reusable is False
    assert validation.reason == "chapter-content-changed"

    changed_converter = TTSConverter(ConversionOptions(title="Book", voice="af_heart"))
    validation = changed_converter._resume_state_matches(
        state,
        [chapter],
        "source",
        changed_converter._generation_fingerprint(),
        tmp_path,
    )
    assert validation.reusable is False
    assert validation.reason == "generation-fingerprint-changed"

    state.version = 1
    validation = converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )
    assert validation.reusable is False
    assert validation.reason == "legacy-state-version"


def test_paragraph_schema5_resume_is_rejected_explicitly(tmp_path: Path) -> None:
    chapter = Chapter(title="Chapter", content="Original", index=0)
    converter = TTSConverter(
        ConversionOptions(title="Book", conversion_unit="paragraph")
    )
    generation = converter._generation_fingerprint()
    state = ConversionState(
        version=5,
        conversion_unit="paragraph",
        source_hash="source",
        onnx_provider=converter.options.effective_onnx_provider(),
        source_selection=[0],
        generation_fingerprint=generation,
        chapters=[
            ChapterState(
                index=0,
                title=chapter.title,
                content_hash=_hash_content(chapter.content),
                render_fingerprint=_chapter_render_fingerprint(chapter, generation),
            )
        ],
    )

    validation = converter._resume_state_matches(
        state, [chapter], "source", generation, tmp_path
    )

    assert validation == ResumeValidation(
        reusable=False, reason="paragraph-resume-schema-upgrade"
    )


def test_renderer_contract_uses_pykokoro_081_and_rejects_old_identity() -> None:
    contract = renderer_contract_payload()
    assert contract["pykokoro"] == "0.8.1"
    assert contract["schema"] == 2
    assert contract != {
        "ssmd_contract": "ssmd-0.8-pykokoro-0.7.2",
    }


def test_text_resume_rejects_missing_or_corrupt_audio(tmp_path: Path) -> None:
    chapter = Chapter(title="Chapter", content="Original", index=0)
    converter = TTSConverter(ConversionOptions(title="Book"))
    state = _text_state(converter, chapter, tmp_path)
    validation = converter._resume_state_matches(
        state, [chapter], "source", converter._generation_fingerprint(), tmp_path
    )
    assert validation.reusable is False
    assert validation.reason == "audio-file-invalid"


def test_markdown_v3_state_is_invalidated_with_precise_reason() -> None:
    messages: list[str] = []
    chapter = Chapter(
        title="ONE",
        content="Visible",
        markdown_body="## Sub\n\nVisible\n",
        source_format="markdown",
        source_id="ch1",
        extraction_schema="epub2text.chapter-document/0.2.8",
        index=0,
    )
    converter = TTSConverter(
        ConversionOptions(title="Book"),
        log_callback=lambda message, _level: messages.append(message),
    )
    generation = converter._generation_fingerprint()
    state = ConversionState(
        version=3,
        source_hash="source",
        onnx_provider=converter.options.effective_onnx_provider(),
        source_selection=[0],
        generation_fingerprint=generation,
        chapters=[
            ChapterState(
                index=0,
                title=chapter.title,
                content_hash=_hash_content(chapter.content),
                render_fingerprint=_chapter_render_fingerprint(chapter, generation),
            )
        ],
    )

    result = converter._resume_state_matches(
        state, [chapter], "source", generation, Path(".")
    )

    assert result == ResumeValidation(
        reusable=False,
        reason="epub-extraction-format-changed",
    )
    assert any(
        "EPUB extraction format changed from plain to markdown" in m for m in messages
    )


def test_markdown_v4_state_reuses_only_unchanged_markup() -> None:
    chapter = Chapter(
        title="ONE",
        content="Visible",
        markdown_body="## Sub\n\nVisible\n",
        source_format="markdown",
        source_id="ch1",
        extraction_schema="epub2text.chapter-document/0.2.8",
        index=0,
    )
    converter = TTSConverter(ConversionOptions(title="Book"))
    generation = converter._generation_fingerprint()
    state = ConversionState(
        version=4,
        source_hash="source",
        onnx_provider=converter.options.effective_onnx_provider(),
        source_selection=[0],
        generation_fingerprint=generation,
        chapters=[
            ChapterState(
                index=0,
                title=chapter.title,
                content_hash=_hash_content(chapter.content),
                source_format=chapter.source_format,
                source_id=chapter.source_id,
                source_markup_hash=_chapter_source_markup_hash_for_test(chapter),
                extraction_schema=chapter.extraction_schema,
                render_fingerprint=_chapter_render_fingerprint(chapter, generation),
            )
        ],
    )

    reusable = converter._resume_state_matches(
        state, [chapter], "source", generation, Path(".")
    )
    changed = converter._resume_state_matches(
        state,
        [replace(chapter, markdown_body="## Changed\n\nVisible\n")],
        "source",
        generation,
        Path("."),
    )

    assert reusable.reusable is True
    assert changed == ResumeValidation(
        reusable=False,
        reason="chapter-content-changed",
    )


def _chapter_source_markup_hash_for_test(chapter: Chapter) -> str:
    return _hash_content(chapter.markdown_body or "")


def test_structured_validation_reasons(tmp_path: Path) -> None:
    """Test that _resume_state_matches returns structured reasons."""
    chapter = Chapter(title="Ch1", content="Hello world", index=0)
    converter = TTSConverter(ConversionOptions(title="Book"))
    generation = converter._generation_fingerprint()
    content_hash = _hash_content(chapter.content)
    render = _chapter_render_fingerprint(chapter, generation)

    # Source hash mismatch
    state = ConversionState(
        version=3,
        source_hash="different",
        onnx_provider=converter.options.effective_onnx_provider(),
        source_selection=[0],
        generation_fingerprint=generation,
        work_dir=str(tmp_path),
        chapters=[
            ChapterState(
                index=0,
                title="Ch1",
                content_hash=content_hash,
                render_fingerprint=render,
            )
        ],
    )
    result = converter._resume_state_matches(
        state, [chapter], "source", generation, tmp_path
    )
    assert result == ResumeValidation(reusable=False, reason="source-hash-changed")

    # Provider changed
    state.source_hash = "source"
    state.onnx_provider = "different"
    result = converter._resume_state_matches(
        state, [chapter], "source", generation, tmp_path
    )
    assert result == ResumeValidation(reusable=False, reason="provider-changed")

    # Selection changed
    state.onnx_provider = converter.options.effective_onnx_provider()
    state.source_selection = [0, 1, 2]
    result = converter._resume_state_matches(
        state, [chapter], "source", generation, tmp_path
    )
    assert result == ResumeValidation(
        reusable=False, reason="chapter-selection-changed"
    )


def test_discover_resume_candidate_basic(tmp_path: Path) -> None:
    """Test basic resume candidate discovery."""
    source_file = tmp_path / "book.txt"
    source_file.write_text("content")
    chapters = [Chapter(title="Ch1", content="Hello", index=i) for i in range(10)]
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # No state file => no candidate
    result = discover_resume_candidate(
        source_file=source_file,
        output_dir=output_dir,
        book_title="Book",
        chapters=chapters,
    )
    assert result is None

    # Create a valid state file
    workspace = resolve_conversion_workspace(
        output_dir=output_dir,
        book_title="Book",
        source_file=source_file,
    )
    workspace.work_dir.mkdir(parents=True)
    state = ConversionState(
        version=3,
        source_hash=workspace.source_hash,
        source_selection=[3, 4, 5],
        output_file="Book_chapters_4-6.m4b",
        chapters=[
            ChapterState(
                index=3,
                title="Ch4",
                content_hash="h",
                completed=True,
                audio_file="ch4.wav",
                duration=10.0,
            ),
            ChapterState(index=4, title="Ch5", content_hash="h", completed=False),
            ChapterState(index=5, title="Ch6", content_hash="h", completed=False),
        ],
    )
    state.save(workspace.state_file)

    result = discover_resume_candidate(
        source_file=source_file,
        output_dir=output_dir,
        book_title="Book",
        chapters=chapters,
    )
    assert result is not None
    assert result.selected_positions == [3, 4, 5]
    assert result.state.source_selection == [3, 4, 5]


def test_discover_resume_candidate_source_hash_mismatch(tmp_path: Path) -> None:
    """Discovery returns None when source hash changes."""
    source_file = tmp_path / "book.txt"
    source_file.write_text("content")
    chapters = [Chapter(title="Ch1", content="Hello", index=i) for i in range(5)]
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    workspace = resolve_conversion_workspace(
        output_dir=output_dir,
        book_title="Book",
        source_file=source_file,
    )
    workspace.work_dir.mkdir(parents=True)
    state = ConversionState(
        version=3,
        source_hash="wrong_hash",
        source_selection=[0, 1],
        chapters=[
            ChapterState(index=0, title="Ch1", content_hash="h"),
            ChapterState(index=1, title="Ch2", content_hash="h"),
        ],
    )
    state.save(workspace.state_file)
    result = discover_resume_candidate(
        source_file=source_file,
        output_dir=output_dir,
        book_title="Book",
        chapters=chapters,
    )
    assert result is None


def test_discover_resume_candidate_missing_indices(tmp_path: Path) -> None:
    """Discovery returns None when saved indices are missing from chapters."""
    source_file = tmp_path / "book.txt"
    source_file.write_text("content")
    chapters = [Chapter(title="Ch1", content="Hello", index=i) for i in range(3)]
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    workspace = resolve_conversion_workspace(
        output_dir=output_dir,
        book_title="Book",
        source_file=source_file,
    )
    workspace.work_dir.mkdir(parents=True)
    state = ConversionState(
        version=3,
        source_hash=workspace.source_hash,
        source_selection=[0, 1, 99],  # 99 doesn't exist
        chapters=[
            ChapterState(index=0, title="Ch1", content_hash="h"),
            ChapterState(index=1, title="Ch2", content_hash="h"),
            ChapterState(index=99, title="Ch100", content_hash="h"),
        ],
    )
    state.save(workspace.state_file)
    result = discover_resume_candidate(
        source_file=source_file,
        output_dir=output_dir,
        book_title="Book",
        chapters=chapters,
    )
    assert result is None


def test_discover_resume_candidate_all_complete(tmp_path: Path) -> None:
    """Discovery returns None when all chapters are complete and output exists."""
    source_file = tmp_path / "book.txt"
    source_file.write_text("content")
    chapters = [Chapter(title="Ch1", content="Hello", index=i) for i in range(3)]
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    workspace = resolve_conversion_workspace(
        output_dir=output_dir,
        book_title="Book",
        source_file=source_file,
    )
    workspace.work_dir.mkdir(parents=True)
    output_path = output_dir / "Book.m4b"
    output_path.write_bytes(b"fake audio")
    state = ConversionState(
        version=3,
        source_hash=workspace.source_hash,
        source_selection=[0, 1, 2],
        output_file=str(output_path),
        chapters=[
            ChapterState(
                index=0,
                title="Ch1",
                content_hash="h",
                completed=True,
                audio_file="ch0.wav",
                duration=10.0,
            ),
            ChapterState(
                index=1,
                title="Ch2",
                content_hash="h",
                completed=True,
                audio_file="ch1.wav",
                duration=10.0,
            ),
            ChapterState(
                index=2,
                title="Ch3",
                content_hash="h",
                completed=True,
                audio_file="ch2.wav",
                duration=10.0,
            ),
        ],
    )
    state.save(workspace.state_file)
    result = discover_resume_candidate(
        source_file=source_file,
        output_dir=output_dir,
        book_title="Book",
        chapters=chapters,
    )
    # All complete + output exists => no need to resume
    assert result is None


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
        onnx_provider=options.effective_onnx_provider(),
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


def test_provider_changes_invalidate_resume_fingerprints() -> None:
    cpu = TTSConverter(ConversionOptions(onnx_provider="cpu"))
    nnapi = TTSConverter(ConversionOptions(onnx_provider="nnapi"))
    assert cpu._generation_fingerprint() != nnapi._generation_fingerprint()

    cpu_phonemes = PhonemeConverter(
        PhonemeBook(title="Book", chapters=[]),
        PhonemeConversionOptions(onnx_provider="cpu"),
    )
    nnapi_phonemes = PhonemeConverter(
        PhonemeBook(title="Book", chapters=[]),
        PhonemeConversionOptions(onnx_provider="nnapi"),
    )
    assert (
        cpu_phonemes._generation_fingerprint()
        != nnapi_phonemes._generation_fingerprint()
    )


@pytest.mark.parametrize(
    "policy",
    [
        ProsodyPolicy(method="esola"),
        ProsodyPolicy(method="psola"),
        ProsodyPolicy(strict=True),
        ProsodyPolicy(n_fft=4096),
        ProsodyPolicy(hop_length=512),
        ProsodyPolicy(boundary_blend_ms=10.0),
    ],
)
def test_prosody_settings_invalidate_text_resume_fingerprint(
    policy: ProsodyPolicy,
) -> None:
    base = TTSConverter(ConversionOptions())
    changed = TTSConverter(ConversionOptions(prosody_policy=policy))
    assert base._generation_fingerprint() != changed._generation_fingerprint()


def test_psola_and_td_psola_are_resume_equivalent() -> None:
    psola = TTSConverter(
        ConversionOptions(prosody_policy=ProsodyPolicy(method="psola"))
    )
    td_psola = TTSConverter(
        ConversionOptions(prosody_policy=ProsodyPolicy(method="td_psola"))
    )
    assert psola._generation_fingerprint() == td_psola._generation_fingerprint()


def test_prosody_settings_invalidate_phoneme_resume_fingerprint() -> None:
    book = PhonemeBook(title="Book", chapters=[])
    base = PhonemeConverter(book, PhonemeConversionOptions())
    changed = PhonemeConverter(
        book,
        replace(
            PhonemeConversionOptions(),
            prosody_policy=ProsodyPolicy(method="phase_vocoder"),
        ),
    )
    assert base._generation_fingerprint() != changed._generation_fingerprint()


def test_resolve_conversion_workspace(tmp_path: Path) -> None:
    """Test shared workspace resolver produces correct paths."""
    source = tmp_path / "book.epub"
    source.write_text("epub content")
    workspace = resolve_conversion_workspace(
        output_dir=tmp_path,
        book_title="My Book",
        source_file=source,
    )
    assert workspace.source_hash != ""
    assert workspace.work_dir.name.endswith("_chapters")
    assert workspace.state_file == workspace.work_dir / "state.json"
