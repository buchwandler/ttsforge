from __future__ import annotations

import pytest

from ttsforge.input_reader import InputReader
from ttsforge.ssmd_support import SSMDValidationError


def test_direct_ssmd_header_title_and_complete_source_are_preserved(tmp_path) -> None:
    source = "---\ntitle: Portable review\n---\nBody...s\n"
    path = tmp_path / "fallback-name.ssmd"
    path.write_text(source, encoding="utf-8")

    reader = InputReader(path)

    assert reader.get_metadata().title == "Portable review"
    chapter = reader.get_chapters()[0]
    assert chapter.title == "Portable review"
    assert chapter.text == source
    assert chapter.is_ssmd is True


def test_direct_ssmd_malformed_header_fails_before_backend(tmp_path) -> None:
    path = tmp_path / "broken.ssmd"
    path.write_text("---\ntitle: [broken\n---\nBody\n", encoding="utf-8")

    with pytest.raises(SSMDValidationError) as raised:
        InputReader(path).get_metadata()

    assert "header.yaml_invalid" in str(raised.value)


def test_direct_ssmd_without_title_uses_filename_stem(tmp_path) -> None:
    path = tmp_path / "fallback-name.ssmd"
    path.write_text("Body only.\n", encoding="utf-8")

    assert InputReader(path).get_metadata().title == "fallback-name"
