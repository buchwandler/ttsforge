from __future__ import annotations

from readio.api import ReadioEvent

from ttsforge.application.events import ApplicationEvent
from ttsforge.readio_backend import translate_readio_event


def test_readio_event_translation_preserves_progress_and_serializable_details() -> None:
    event = ReadioEvent(
        kind="progress",
        operation="projects.build",
        stage="synthesis",
        progress_kind="segment.completed",
        message="Rendered segment",
        completed=2,
        total=3,
        sample_count=48000,
        sample_rate=24000,
        audio_seconds=2.0,
        total_audio_seconds=6.0,
        scope_id="chapter-1",
        unit_id="unit-2",
        segment_id="segment-4",
        details={"reused": 1, "missing": 2},
    )

    translated = translate_readio_event(event)

    assert isinstance(translated, ApplicationEvent)
    assert translated.to_dict() == {
        "kind": "progress",
        "operation": "projects.build",
        "stage": "synthesis",
        "progress_kind": "segment.completed",
        "message": "Rendered segment",
        "completed": 2,
        "total": 3,
        "sample_count": 48000,
        "sample_rate": 24000,
        "audio_seconds": 2.0,
        "total_audio_seconds": 6.0,
        "scope_id": "chapter-1",
        "unit_id": "unit-2",
        "segment_id": "segment-4",
        "details": {"reused": 1, "missing": 2},
    }
