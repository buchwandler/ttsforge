from ttsforge.ssmd_generator import chapter_to_ssmd


def test_emphasis_repeated_phrases() -> None:
    ssmd = chapter_to_ssmd(
        chapter_title="",
        chapter_text="",
        chapter_markdown="This is *very* good. This is *very* good.",
        source_format="markdown",
        include_title=False,
    )
    assert ssmd.count("*very*") == 2


def test_emphasis_with_punctuation() -> None:
    ssmd = chapter_to_ssmd(
        chapter_title="",
        chapter_text="",
        chapter_markdown="Wait, **now**.",
        source_format="markdown",
        include_title=False,
    )
    assert "**now**" in ssmd


def test_markdown_headings_scene_breaks_and_title_are_preserved() -> None:
    ssmd = chapter_to_ssmd(
        chapter_title="ONE",
        chapter_text="",
        chapter_markdown="## Four years ago\n\nAbove all, *semantic italic*."
        "\n\n---\n\nAfter.",
        source_format="markdown",
    )

    assert ssmd.count("# ONE") == 1
    assert "## Four years ago" in ssmd
    assert "*semantic italic*" in ssmd
    assert "\n...p\n" in ssmd


def test_phonemes_only_transform_visible_markdown_text() -> None:
    ssmd = chapter_to_ssmd(
        chapter_title="",
        chapter_text="",
        chapter_markdown=('## Heading\n\n*one* **one** [one]{ph="existing"} one'),
        source_format="markdown",
        include_title=False,
        phoneme_dict={"one": "wʌn"},
    )

    assert ssmd.count('{ph="wʌn"}') == 3
    assert '[one]{ph="existing"}' in ssmd
    assert "## Heading" in ssmd
