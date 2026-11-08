"""Contract checks for the Readio 0.6 public API used by TTSForge."""

from __future__ import annotations

from dataclasses import fields, is_dataclass

import readio.api as readio_api


def test_required_public_api_symbols_are_available() -> None:
    required = {
        "Readio",
        "ReadioError",
        "RebuildStage",
        "RenderIntent",
        "RenderRequest",
        "RenderResult",
        "WorkflowEvent",
        "WorkflowPlan",
        "SourceChapter",
        "SourceInspection",
        "PlanningOptions",
        "VoiceRenderOptions",
        "CompositionOptions",
        "ExportOptions",
        "create_book_intent",
        "create_profile",
        "discover_engine_targets",
        "inspect_source",
        "inspect_voice",
        "list_engine_options",
        "list_engines",
        "list_voices",
        "load_profile",
        "load_render_intent",
        "render_request_from_intent",
        "save_render_intent",
        "validate_profile",
    }
    missing = sorted(name for name in required if not hasattr(readio_api, name))
    assert not missing, (
        "The installed Readio does not provide TTSForge's required public API: "
        f"{', '.join(missing)}. Install Readio >=0.6.1,<0.7."
    )


def test_workflow_types_expose_the_normalized_contract() -> None:
    request_fields = {field.name for field in fields(readio_api.RenderRequest)}
    event_fields = {field.name for field in fields(readio_api.WorkflowEvent)}
    source_fields = {field.name for field in fields(readio_api.SourceInspection)}
    chapter_fields = {field.name for field in fields(readio_api.SourceChapter)}

    assert {
        "source",
        "profile",
        "chapters",
        "language",
        "bundle",
        "output",
        "rebuild_from",
        "replace_output",
        "planning",
        "voice_render",
        "composition",
        "export",
    } <= request_fields
    assert {
        "stage",
        "kind",
        "package",
        "selector",
        "current",
        "total",
        "message",
        "elapsed_seconds",
        "details",
    } <= event_fields
    assert {"source", "kind", "metadata", "chapters"} <= source_fields
    assert {
        "number",
        "title",
        "source_id",
        "parent_id",
        "level",
        "char_count",
    } <= chapter_fields
    assert all(
        is_dataclass(getattr(readio_api, name))
        for name in (
            "RenderRequest",
            "WorkflowEvent",
            "SourceInspection",
            "SourceChapter",
        )
    )


def test_readio_gateway_exposes_unified_source_and_workflow_operations() -> None:
    app = readio_api.Readio()
    for name in (
        "inspect_source",
        "request_from_intent",
        "inspect_intent",
        "inspect",
        "render",
    ):
        assert callable(getattr(app, name))


def test_book_intent_and_profile_helpers_are_public_callables() -> None:
    for name in (
        "create_book_intent",
        "load_render_intent",
        "save_render_intent",
        "render_request_from_intent",
        "create_profile",
        "load_profile",
        "validate_profile",
        "list_engines",
        "discover_engine_targets",
        "list_engine_options",
        "list_voices",
        "inspect_voice",
    ):
        assert callable(getattr(readio_api, name))
