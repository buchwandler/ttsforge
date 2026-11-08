from __future__ import annotations

from pathlib import Path

from ttsforge.application.service import AudiobookApplicationService as Service
from ttsforge.audiobook import (
    AudiobookApplicationService,
    AudiobookOptions,
    AudiobookRequest,
    ProjectPaths,
)


def test_public_audiobook_module_exports_current_application_contracts() -> None:
    source = Path("The Book.epub")

    assert AudiobookApplicationService is Service
    assert AudiobookOptions is AudiobookRequest
    assert ProjectPaths.for_source(source).root == Path("The Book.ttsforge")
