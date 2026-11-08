from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ttsforge.application import (
    AudiobookOptions,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    CatalogItemView,
    ConversionResultView,
    InputOverrides,
    ProjectPaths,
    SetupConflictError,
    SetupOrigins,
    WorkflowPlanView,
    WorkflowStepView,
)
from ttsforge.application.setup import merge_saved_setup
from ttsforge.options import AudiobookOptions as CompatibilityAudiobookOptions


def test_audiobook_request_keeps_the_public_options_compatibility_name() -> None:
    request = AudiobookOptions(source=Path("book.epub"), language="en-us")

    assert AudiobookOptions is AudiobookRequest
    assert CompatibilityAudiobookOptions is AudiobookRequest
    assert request.source == Path("book.epub")
    assert request.language == "en-us"


def test_project_paths_follow_ttsforge_layout() -> None:
    paths = ProjectPaths.for_source(Path("book.epub"))

    assert paths.root == Path("book.ttsforge")
    assert paths.intent == Path("book.ttsforge/render.readio.toml")
    assert paths.profile == Path("book.ttsforge/narrator.renderprofile.toml")
    assert paths.bundle == Path("book.ttsforge/book.ssmd-bundle")


def test_input_overrides_and_setup_origins_are_frontend_neutral() -> None:
    overrides = InputOverrides(frozenset({"engine"}))
    origins = SetupOrigins(explicit=overrides.fields, project=frozenset({"voice"}))

    assert overrides.includes("engine")
    assert not overrides.includes("voice")
    assert not origins.needs_input("engine")
    assert not origins.needs_input("voice")
    assert origins.needs_input("target")


def test_application_views_have_no_readio_dto_requirement() -> None:
    inspection = BookInspectionView(
        source=Path("book.epub"),
        kind="book",
        title="Book",
        author="Author",
        language="en-US",
        chapters=(BookChapterView(number=1, title="Opening", source_id="c1"),),
    )
    plan = WorkflowPlanView(
        source=inspection.source,
        workspace=Path("book.ttsforge/book.ssmd-bundle"),
        workspace_mode="bundle",
        output=Path("book.m4b"),
        steps=(
            WorkflowStepView(
                stage="render",
                package="ttsforge",
                action="reuse",
                selector="book",
                reason="Already present",
                state="ready",
            ),
        ),
    )
    result = ConversionResultView(
        output=Path("book.m4b"),
        workspace=plan.workspace,
        workspace_mode=plan.workspace_mode,
        executed_stages=(),
        reused_stages=("render",),
    )
    item = CatalogItemView(id="voice-1", label="Narrator", engine="engine-a")

    assert inspection.chapters[0].title == "Opening"
    assert plan.steps[0].state == "ready"
    assert result.reused_stages == ("render",)
    assert item.engine == "engine-a"


def test_noninteractive_saved_setup_conflict_reports_dependent_values() -> None:
    request = AudiobookRequest(source=Path("book.epub"), engine="engine-b")
    saved = replace(
        request,
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        engine_options={"quality": "high"},
        speed=1.0,
    )

    with pytest.raises(SetupConflictError, match=r"--engine.*--target.*--voice"):
        merge_saved_setup(
            request,
            saved,
            InputOverrides(frozenset({"engine"})),
            interactive=False,
        )
