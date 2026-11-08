from __future__ import annotations

import readio.api as readio_api


def test_public_readio_progress_contract_is_workflow_event() -> None:
    event = readio_api.WorkflowEvent(
        stage="render",
        kind="stage.progress",
        package="voicerender",
        selector="chapter-1",
        current=2,
        total=4,
        message="Rendering",
        elapsed_seconds=1.0,
        details={"attempt": 1},
    )

    assert event.stage == "render"
    assert event.kind == "stage.progress"
    assert event.package == "voicerender"
    assert event.selector == "chapter-1"
    assert event.current == 2
    assert event.total == 4
    assert event.details == {"attempt": 1}
    assert not hasattr(readio_api, "ReadioEvent")
