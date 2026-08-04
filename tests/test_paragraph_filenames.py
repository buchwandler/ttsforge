"""Filename contract tests for visible paragraph artifacts."""

from ttsforge.paragraph_output import canonical_filename, is_canonical_filename


def test_fixed_width_sequence_controls_lexical_order():
    names = [
        canonical_filename(
            sequence_index=value,
            source_chapter_index=0,
            paragraph_index=1,
            kind="paragraph",
            chapter_title="Book",
        )
        for value in (1, 9, 10, 137)
    ]
    assert names == sorted(names)
    assert names[0].startswith("00000001__c000001__p000001__paragraph__")
    assert is_canonical_filename(names[-1])


def test_title_and_unicode_duplicate_titles_keep_identity_prefix():
    first = canonical_filename(
        sequence_index=1,
        source_chapter_index=6,
        paragraph_index=0,
        kind="title",
        chapter_title="Été / Seven",
    )
    second = canonical_filename(
        sequence_index=2,
        source_chapter_index=7,
        paragraph_index=1,
        kind="paragraph",
        chapter_title="Été / Seven",
    )
    assert "__p000000__title__ETE_SEVEN.wav" == first[first.index("__p") :]
    assert first != second
