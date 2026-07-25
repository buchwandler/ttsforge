from ttsforge.input_reader import InputReader
from ttsforge.text_postprocessing import TextPostprocessOptions, postprocess_extracted_text


def test_strips_epub_chapter_marker_with_leading_whitespace() -> None:
    text = " <<CHAPTER: Test Chapter>>\n\nThis is the content."
    result = postprocess_extracted_text(text)
    assert result == "This is the content."


def test_replaces_literal_ellipsis_without_touching_ssmd_breaks() -> None:
    text = "Wait... Then pause...c Next...s Here...p Done...500ms End..."
    result = postprocess_extracted_text(text)
    expected = "Wait\u2026 Then pause...c Next...s Here...p Done...500ms End\u2026"
    assert result == expected
def test_direct_ssmd_input_is_not_postprocessed(tmp_path) -> None:
    content = "One step. In front.\n***\nWait..."
    ssmd_file = tmp_path / "chapter.ssmd"
    ssmd_file.write_text(content, encoding="utf-8")

    reader = InputReader(
        ssmd_file,
        postprocess_options=TextPostprocessOptions(),
    )

    chapters = reader.get_chapters()
    assert chapters[0].is_ssmd is True
    assert chapters[0].text == content
