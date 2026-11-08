from __future__ import annotations

import ttsforge


def test_removed_readio_04_audiobook_facade_is_not_public() -> None:
    assert "AudiobookConverter" not in ttsforge.__all__
    assert "ProjectSetup" not in ttsforge.__all__
    assert not hasattr(ttsforge, "AudiobookConverter")
    assert not hasattr(ttsforge, "ProjectSetup")
