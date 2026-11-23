"""Contract checks for the Readio 0.6.8 public API used by TTSForge."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from inspect import signature

import readio.api as readio_api


def test_required_public_api_symbols_are_available() -> None:
    required = {
        "Readio",
        "ReadioError",
        "EngineInfo",
        "TargetInfo",
        "VoiceInfo",
        "EngineOptionInfo",
        "ErrorInfo",
        "WorkflowBlocker",
        "StageExecutionRecord",
        "ExecutionReport",
        "PreparationIntent",
        "ProjectionIntent",
        "SpacyModelInfo",
        "ensure_spacy_model",
        "inspect_spacy_model",
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
        "describe_error",
        "inspect_voice",
        "inspect_source",
        "load_profile",
        "load_render_intent",
        "render_request_from_intent",
        "save_render_intent",
        "validate_profile",
    }
    missing = sorted(name for name in required if not hasattr(readio_api, name))
    assert not missing, (
        "The installed Readio does not provide TTSForge's required public API: "
        f"{', '.join(missing)}. Install Readio >=0.6.8,<0.7."
    )


def test_setup_intents_and_spacy_model_are_public_contracts() -> None:
    preparation_fields = {field.name for field in fields(readio_api.PreparationIntent)}
    projection_fields = {field.name for field in fields(readio_api.ProjectionIntent)}
    model_fields = {field.name for field in fields(readio_api.SpacyModelInfo)}
    intent_parameters = set(signature(readio_api.create_book_intent).parameters)

    assert {"spacy", "speech_profile"} <= preparation_fields
    assert {"pause_timing"} <= projection_fields
    assert {
        "language",
        "tier",
        "model",
        "installed",
        "spacy_version",
        "model_version",
    } <= model_fields
    assert {"preparation", "projection"} <= intent_parameters


def test_normalized_catalog_dtos_and_workflow_results_are_public_contracts() -> None:
    expected_fields = {
        "EngineInfo": {"id", "version", "installed", "runnable", "features", "reason"},
        "TargetInfo": {
            "id",
            "languages",
            "status",
            "runtime_available",
            "default_voice",
            "voice_count",
            "qualities",
            "voice_mode",
            "sample_rate",
            "features",
            "reference_only",
        },
        "VoiceInfo": {
            "id",
            "language",
            "locale",
            "language_label",
            "gender",
            "default",
            "runtime_available",
        },
        "EngineOptionInfo": {
            "name",
            "value_type",
            "required",
            "default",
            "choices",
            "minimum",
            "maximum",
            "description",
            "identity_affecting",
            "runtime_only",
        },
        "WorkflowBlocker": {
            "code",
            "message",
            "owner",
            "recoverable",
            "suggested_action",
        },
        "StageExecutionRecord": {
            "stage",
            "package",
            "action",
            "state_before",
            "state_after",
            "elapsed_seconds",
            "reason_code",
        },
        "ExecutionReport": {
            "stages",
            "specialist_versions",
            "elapsed_seconds",
        },
    }
    for name, expected in expected_fields.items():
        model = getattr(readio_api, name)
        assert is_dataclass(model)
        assert expected <= {field.name for field in fields(model)}

    step_fields = {field.name for field in fields(readio_api.WorkflowStep)}
    plan_fields = {field.name for field in fields(readio_api.WorkflowPlan)}
    assert {"reason_code", "force", "blockers"} <= step_fields
    assert "executable" in dir(readio_api.WorkflowPlan)
    assert {"source", "workspace", "output", "steps", "warnings"} <= plan_fields


def test_readio_gateway_exposes_normalized_catalog_and_capability_methods() -> None:
    app = readio_api.Readio()
    for name in (
        "inspect_source",
        "request_from_intent",
        "inspect_intent",
        "inspect",
        "render",
        "list_engines",
        "list_targets",
        "list_voices",
        "list_engine_options",
        "capabilities",
        "synthesis_capabilities",
        "export_capabilities",
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
    ):
        assert callable(getattr(readio_api, name))
