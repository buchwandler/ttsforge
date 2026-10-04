from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ttsforge.application import (
    AudiobookOptions,
    AudiobookRequest,
    CatalogItemView,
    ChapterView,
    ConversionResultView,
    InputOverrides,
    ProjectMigrationRequiredError,
    ProjectView,
    SetupConflictError,
    SetupOrigins,
)
from ttsforge.application.setup import merge_saved_setup
from ttsforge.options import AudiobookOptions as CompatibilityAudiobookOptions


def test_audiobook_request_keeps_the_public_options_compatibility_name() -> None:
    request = AudiobookOptions(source=Path("book.epub"), language="en-us")

    assert AudiobookOptions is AudiobookRequest
    assert CompatibilityAudiobookOptions is AudiobookRequest
    assert request.source == Path("book.epub")
    assert request.language == "en-us"


def test_input_overrides_and_setup_origins_are_frontend_neutral() -> None:
    overrides = InputOverrides(frozenset({"engine"}))
    origins = SetupOrigins(explicit=overrides.fields, project=frozenset({"voice"}))

    assert overrides.includes("engine")
    assert not overrides.includes("voice")
    assert not origins.needs_input("engine")
    assert not origins.needs_input("voice")
    assert origins.needs_input("voice", reconfigure=True)
    assert origins.needs_input("model")


def test_application_views_and_stable_errors_have_no_readio_dto_requirement() -> None:
    project = ProjectView(
        path=Path("book.readio"),
        project_id="project-id",
        name="Book",
        kind="audiobook",
        source_format="epub",
        chapters=(ChapterView(number=1, title="Opening"),),
    )
    result = ConversionResultView(
        project=project, output=Path("book.m4b"), chapters=(1,)
    )
    item = CatalogItemView(id="af_sarah", label="Sarah", engine="kokoro")

    assert result.project.chapters[0].title == "Opening"
    assert result.chapters == (1,)
    assert item.engine == "kokoro"
    assert issubclass(ProjectMigrationRequiredError, ValueError)


def test_noninteractive_saved_setup_conflict_uses_stable_application_error() -> None:
    cli_request = AudiobookRequest(source=Path("book.epub"), engine="piper")
    saved_request = replace(
        cli_request,
        engine="kokoro",
        model="v1.0",
        quality="q8",
        voice="af_sarah",
    )

    with pytest.raises(
        SetupConflictError, match=r"--engine.*--model.*--quality.*--voice"
    ):
        merge_saved_setup(
            cli_request,
            saved_request,
            InputOverrides(frozenset({"engine"})),
            interactive=False,
        )
