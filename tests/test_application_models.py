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
    ProjectVariantView,
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

    assert request.new_variant is False
    assert request.language == "en-us"


def test_project_paths_follow_ttsforge_layout() -> None:
    paths = ProjectPaths.for_source(Path("book.epub"))

    assert paths.root == Path("book.ttsforge")
    assert paths.intent == Path("book.ttsforge/render.readio.toml")
    assert paths.profile == Path("book.ttsforge/narrator.renderprofile.toml")
    assert paths.bundle == Path("book.ttsforge/book.ssmd-bundle")

    variant_paths = ProjectPaths.for_variant(paths.root, "piper-key")

    assert paths.setup_root == paths.root
    assert variant_paths.root == paths.root
    assert variant_paths.bundle == paths.bundle
    assert variant_paths.intent == paths.root / "variants/piper-key/render.readio.toml"
    assert variant_paths.profile == (
        paths.root / "variants/piper-key/narrator.renderprofile.toml"
    )
    assert variant_paths.setup_root == paths.root / "variants/piper-key"
    assert variant_paths.variant_key == "piper-key"


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

    variant_plan = replace(plan, variant="specialist-variant")
    variant_result = replace(result, variant="specialist-variant")
    variant = ProjectVariantView(
        variant_key="piper-key",
        output=Path("variant.m4b"),
        engine="piper",
        target="target",
        voice="lessac",
    )
    item = CatalogItemView(id="voice-1", label="Narrator", engine="engine-a")

    assert inspection.chapters[0].title == "Opening"
    assert plan.steps[0].state == "ready"
    assert result.reused_stages == ("render",)
    assert item.engine == "engine-a"

    assert variant_plan.variant == "specialist-variant"
    assert variant_result.variant == "specialist-variant"
    assert variant.variant_key == "piper-key"
    assert variant.output == Path("variant.m4b")


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
