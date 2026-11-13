"""Delegation tests for TTSForge's narrow Readio API adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from readio.api import (
    Readio,
    RenderIntent,
    RenderRequest,
    WorkflowEvent,
    WorkflowStageError,
)

import ttsforge.readio_backend as backend_module
from ttsforge.application.errors import WorkflowFailureError
from ttsforge.application.events import ApplicationEvent
from ttsforge.application.models import AudiobookRequest, ProjectPaths
from ttsforge.readio_backend import ReadioBackend, create_readio


def test_create_readio_constructs_the_public_gateway() -> None:
    assert isinstance(create_readio(), Readio)


def test_source_and_discovery_calls_delegate_to_public_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path("book.epub")
    inspection = SimpleNamespace(
        source=source,
        kind="book",
        metadata={
            "title": "Book",
            "authors": ["Writer One", "Writer Two"],
            "language": "en",
        },
        chapters=(
            SimpleNamespace(number=1, title="Opening", source_id="c1", char_count=120),
        ),
    )
    calls: list[tuple[str, object]] = []

    def inspect_source(path: Path) -> object:
        calls.append(("source", path))
        return inspection

    def list_engines() -> list[dict[str, object]]:
        calls.append(("engines", None))
        return [{"id": "piper"}]

    def discover_targets(engine: str, **kwargs: object) -> tuple[str, ...]:
        calls.append(("targets", (engine, kwargs)))
        return ("target",)

    def list_engine_options(engine: str, **kwargs: object) -> tuple[str, ...]:
        calls.append(("options", (engine, kwargs)))
        return ("device",)

    def list_voices(**kwargs: object) -> tuple[str, ...]:
        calls.append(("voices", kwargs))
        return ("voice",)

    def inspect_voice(selector: str, **kwargs: object) -> str:
        calls.append(("voice", (selector, kwargs)))
        return "detail"

    api = backend_module.readio_api
    monkeypatch.setattr(api, "inspect_source", inspect_source)
    monkeypatch.setattr(api, "list_engines", list_engines)
    monkeypatch.setattr(api, "discover_engine_targets", discover_targets)
    monkeypatch.setattr(api, "list_engine_options", list_engine_options)
    monkeypatch.setattr(api, "list_voices", list_voices)
    monkeypatch.setattr(api, "inspect_voice", inspect_voice)

    backend = ReadioBackend(app=cast(Readio, object()))

    view = backend.inspect_source(source)
    assert view.title == "Book"
    assert view.author == "Writer One, Writer Two"
    assert view.language == "en"
    assert view.chapters[0].source_id == "c1"
    assert backend.list_engines() == ({"id": "piper"},)
    assert backend.list_targets(
        engine="piper", language="en-us", offline=True, refresh=True
    ) == ("target",)
    assert backend.list_engine_options("piper", target="en-us-medium") == ("device",)
    assert backend.list_voices(
        engine="piper", target="en-us-medium", language="en-us", offline=True
    ) == ("voice",)
    assert backend.inspect_voice("piper:en-us-medium", language="en-us") == "detail"
    assert calls == [
        ("source", source),
        ("engines", None),
        ("targets", ("piper", {"language": "en-us", "offline": True, "refresh": True})),
        ("options", ("piper", {"target": "en-us-medium"})),
        (
            "voices",
            {
                "engine": "piper",
                "target": "en-us-medium",
                "language": "en-us",
                "offline": True,
                "refresh": False,
            },
        ),
        ("voice", ("piper:en-us-medium", {"language": "en-us"})),
    ]


def test_spacy_model_inventory_maps_public_readio_api_and_normalizes_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = (
        SimpleNamespace(
            language="en-US",
            tier="sm",
            model="en_core_web_sm",
            installed=True,
            spacy_version="3.8.16",
            model_version="3.8.0",
        ),
        SimpleNamespace(
            language="en-US",
            tier="lg",
            model="en_core_web_lg",
            installed=False,
            spacy_version="3.8.16",
            model_version=None,
        ),
    )
    calls: list[str] = []
    api = backend_module.readio_api

    def list_models(language: str) -> tuple[object, ...]:
        calls.append(language)
        return models

    monkeypatch.setattr(api, "list_spacy_models", list_models)
    backend = ReadioBackend(app=cast(Readio, object()))

    assert backend.list_spacy_models("en-US") == (
        backend_module.SpacyModelView(
            language="en-US",
            tier="sm",
            model="en_core_web_sm",
            installed=True,
            spacy_version="3.8.16",
            model_version="3.8.0",
        ),
        backend_module.SpacyModelView(
            language="en-US",
            tier="lg",
            model="en_core_web_lg",
            installed=False,
            spacy_version="3.8.16",
            model_version=None,
        ),
    )
    assert calls == ["en-US"]

    def fail_inventory(language: str) -> tuple[object, ...]:
        raise api.ReadioError(f"inventory unavailable for {language}")

    monkeypatch.setattr(api, "list_spacy_models", fail_inventory)
    with pytest.raises(WorkflowFailureError) as error:
        backend.list_spacy_models("en-US")
    assert error.value.category == "spaCy model inventory failure"
    assert str(error.value) == "inventory unavailable for en-US"


def test_spacy_model_inspection_and_provisioning_use_readio_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = SimpleNamespace(
        language="en",
        tier="trf",
        model="en_core_web_trf",
        installed=False,
        spacy_version="3.8.16",
        model_version=None,
    )
    provisioned = SimpleNamespace(
        language="en",
        tier="trf",
        model="en_core_web_trf",
        installed=True,
        spacy_version="3.8.16",
        model_version="3.8.0",
    )
    calls: list[tuple[str, object]] = []
    api = backend_module.readio_api

    def inspect_model(language: str, tier: str) -> object:
        calls.append(("inspect", (language, tier)))
        return missing

    def ensure_model(language: str, tier: str, *, offline: bool) -> object:
        calls.append(("ensure", (language, tier, offline)))
        return provisioned

    monkeypatch.setattr(api, "inspect_spacy_model", inspect_model)
    monkeypatch.setattr(api, "ensure_spacy_model", ensure_model)
    backend = ReadioBackend(app=cast(Readio, object()))

    inspected = backend.inspect_spacy_model("en", "trf")
    ensured = backend.ensure_spacy_model("en", "trf")

    assert inspected.model == "en_core_web_trf"
    assert not inspected.installed
    assert ensured.installed
    assert ensured.model_version == "3.8.0"
    assert calls == [
        ("inspect", ("en", "trf")),
        ("inspect", ("en", "trf")),
        ("ensure", ("en", "trf", False)),
    ]


def test_offline_spacy_model_failure_never_calls_provisioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = SimpleNamespace(
        language="en",
        tier="trf",
        model="en_core_web_trf",
        installed=False,
        spacy_version="3.8.16",
        model_version=None,
    )
    api = backend_module.readio_api
    monkeypatch.setattr(api, "inspect_spacy_model", lambda language, tier: info)
    monkeypatch.setattr(
        api,
        "ensure_spacy_model",
        lambda *args, **kwargs: pytest.fail("offline mode must not provision"),
    )
    backend = ReadioBackend(app=cast(Readio, object()))

    with pytest.raises(WorkflowFailureError) as error:
        backend.ensure_spacy_model("en", "trf", offline=True)

    assert error.value.code == "spacy_model_missing_offline"
    assert error.value.selector == "en_core_web_trf"
    with pytest.raises(ValueError, match="Only concrete spaCy model tiers"):
        backend.ensure_spacy_model("en", "auto")


def test_profile_operations_use_public_profile_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "narrator.renderprofile.toml"
    profile = object()
    calls: list[tuple[str, object]] = []

    def create_profile(**kwargs: object) -> object:
        calls.append(("create", kwargs))
        return profile

    def load_profile(path: Path) -> object:
        calls.append(("load", path))
        return profile

    def validate_profile(path: Path) -> tuple[str, ...]:
        calls.append(("validate", path))
        return ("valid",)

    api = backend_module.readio_api
    monkeypatch.setattr(api, "create_profile", create_profile)
    monkeypatch.setattr(api, "load_profile", load_profile)
    monkeypatch.setattr(api, "validate_profile", validate_profile)

    backend = ReadioBackend(app=cast(Readio, object()))
    assert (
        backend.create_profile(
            output=output,
            engine="piper",
            target="en-us-medium",
            language="en-us",
            voice="lessac",
            options={"device": "cpu"},
            offline=True,
            refresh=True,
            force=True,
        )
        is profile
    )
    assert backend.load_profile(output) is profile
    assert backend.validate_profile(output) == ("valid",)
    assert calls == [
        (
            "create",
            {
                "output": output,
                "engine": "piper",
                "target": "en-us-medium",
                "language": "en-us",
                "voice": "lessac",
                "options": {"device": "cpu"},
                "offline": True,
                "refresh": True,
                "force": True,
            },
        ),
        ("load", output),
        ("validate", output),
    ]


@pytest.mark.parametrize(
    ("tier", "planning_spacy"),
    [("sm", "on"), ("auto", "auto"), ("off", "off"), (None, "auto")],
)
def test_create_book_intent_maps_setup_settings_to_readio(
    tmp_path: Path, tier: str | None, planning_spacy: str
) -> None:
    backend = ReadioBackend(app=cast(Readio, object()))
    speech_profile = tmp_path / "speech.toml"

    intent = backend.create_book_intent(
        source=tmp_path / "book.epub",
        profile=tmp_path / "voice.toml",
        bundle=tmp_path / "book.ssmd-bundle",
        chapters="all",
        language="en",
        output=tmp_path / "book.m4b",
        bitrate="96k",
        cover=None,
        metadata={},
        spacy=tier,
        speech_profile=speech_profile,
        pause_timing="engaging",
    )

    assert intent.planning.spacy == planning_spacy
    assert intent.preparation.spacy == tier
    assert intent.preparation.speech_profile == speech_profile
    assert intent.projection.pause_timing == "engaging"


@pytest.mark.parametrize("chapters", ["2-4", "all"])
def test_save_setup_persists_profile_and_render_intent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, chapters: str
) -> None:
    paths = ProjectPaths.for_variant(tmp_path / "book.ttsforge", "piper-key")
    assert paths.root == tmp_path / "book.ttsforge"
    assert paths.bundle == paths.root / "book.ssmd-bundle"
    request = AudiobookRequest(
        source=tmp_path / "book.epub",
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        engine_options={"quality": "high"},
        speed=1.1,
        chapters=chapters,
        output=tmp_path / "book.m4b",
        bitrate="128k",
        target_lufs=-19.0,
        title="Book title",
        author="Writer",
        spacy="sm",
        speech_profile=tmp_path / "speech.toml",
        pause_timing="engaging",
        new_variant=True,
    )
    calls: list[tuple[str, object]] = []

    def create_profile(**kwargs: object) -> object:
        calls.append(("profile", kwargs))
        return object()

    def create_book_intent(source: Path, **kwargs: object) -> object:
        intent = object()
        calls.append(("intent", (source, kwargs, intent)))
        return intent

    def save_render_intent(intent: object, path: Path, **kwargs: object) -> Path:
        calls.append(("save", (intent, path, kwargs)))
        return path

    api = backend_module.readio_api
    monkeypatch.setattr(api, "create_profile", create_profile)
    monkeypatch.setattr(api, "create_book_intent", create_book_intent)
    monkeypatch.setattr(api, "save_render_intent", save_render_intent)
    backend = ReadioBackend(app=cast(Readio, object()))

    backend.save_setup(paths, request)

    assert calls[1] == (
        "profile",
        {
            "output": paths.profile,
            "engine": "engine-a",
            "target": "target-a",
            "language": "en-US",
            "voice": "voice-a",
            "options": {"quality": "high", "speed": 1.1},
            "offline": False,
            "refresh": False,
            "force": False,
        },
    )
    intent_call = calls[0]
    assert intent_call[0] == "intent"
    source_arg, intent_kwargs, intent = intent_call[1]
    assert source_arg == request.source
    assert intent_kwargs == {
        "profile": paths.profile,
        "bundle": paths.bundle,
        "chapters": chapters,
        "language": "en-US",
        "output_format": "m4b",
        "output": request.output,
        "bitrate": "128k",
        "cover": None,
        "metadata": {"title": "Book title", "author": "Writer"},
        "spacy": "on",
        "preparation": backend_module.readio_api.PreparationIntent(
            spacy="sm", speech_profile=request.speech_profile
        ),
        "projection": backend_module.readio_api.ProjectionIntent(
            pause_timing="engaging"
        ),
        "target_lufs": -19.0,
    }
    assert calls[2] == ("save", (intent, paths.intent, {"force": True}))


def test_load_setup_recovers_intent_and_default_profile_role(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    intent = SimpleNamespace(
        input=SimpleNamespace(source=tmp_path / "book.epub", chapters="1-3"),
        output=SimpleNamespace(
            path=tmp_path / "saved.m4b",
            bitrate="96k",
            cover=tmp_path / "cover.jpg",
            metadata={"title": "Saved", "author": "Writer"},
        ),
        compose=SimpleNamespace(target_lufs=-20.0),
    )
    role = SimpleNamespace(
        language="en-US",
        binding={
            "renderer": "engine-a",
            "target_id": "target-a",
            "voice": "voice-a",
            "options": {"speed": 1.2, "quality": "high"},
        },
    )
    profile = SimpleNamespace(default_role="narrator", roles={"narrator": role})
    calls: list[tuple[str, object]] = []
    api = backend_module.readio_api
    monkeypatch.setattr(
        api, "load_render_intent", lambda path: calls.append(("intent", path)) or intent
    )
    monkeypatch.setattr(api, "load_profile", lambda path: profile)
    monkeypatch.setattr(
        api, "validate_profile", lambda path: calls.append(("validate", path))
    )
    backend = ReadioBackend(app=cast(Readio, object()))

    request = backend.load_setup(paths)

    assert request.source == tmp_path / "book.epub"
    assert request.chapters == "1-3"
    assert request.output == tmp_path / "saved.m4b"
    assert request.engine == "engine-a"
    assert request.target == "target-a"
    assert request.voice == "voice-a"
    assert request.speed == 1.2
    assert request.engine_options == {"quality": "high"}
    assert request.title == "Saved"
    assert request.author == "Writer"
    assert calls == [("intent", paths.intent), ("validate", paths.profile)]


def test_load_setup_recovers_spacy_profile_and_pause_timing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    speech_profile = tmp_path / "speech.toml"
    intent = SimpleNamespace(
        input=SimpleNamespace(source=tmp_path / "book.epub", chapters="all"),
        output=SimpleNamespace(
            path=tmp_path / "saved.m4b",
            bitrate="96k",
            cover=None,
            metadata={},
        ),
        compose=SimpleNamespace(target_lufs=-18.0),
        preparation=SimpleNamespace(spacy="md", speech_profile=speech_profile),
        projection=SimpleNamespace(pause_timing="natural"),
    )
    role = SimpleNamespace(
        language="en",
        binding={
            "renderer": "engine-a",
            "target_id": "target-a",
            "voice": None,
            "options": {},
        },
    )
    profile = SimpleNamespace(default_role="narrator", roles={"narrator": role})
    api = backend_module.readio_api
    monkeypatch.setattr(api, "load_render_intent", lambda path: intent)
    monkeypatch.setattr(api, "load_profile", lambda path: profile)
    monkeypatch.setattr(api, "validate_profile", lambda path: ())
    backend = ReadioBackend(app=cast(Readio, object()))

    request = backend.load_setup(paths)

    assert request.spacy == "md"
    assert request.speech_profile == speech_profile
    assert request.pause_timing == "natural"
    assert request.chapters == "all"


def test_request_bridge_uses_persisted_intent_and_runtime_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = ProjectPaths.for_variant(tmp_path / "book.ttsforge", "piper-key")
    intent = cast(RenderIntent, object())
    request = AudiobookRequest(
        source=tmp_path / "book.epub",
        rebuild_from="render",
        replace_output=True,
        new_variant=True,
    )
    resolved = cast(RenderRequest, object())
    calls: list[tuple[str, object]] = []
    api = backend_module.readio_api
    monkeypatch.setattr(api, "load_render_intent", lambda path: intent)

    def render_request_from_intent(
        value: RenderIntent, **kwargs: object
    ) -> RenderRequest:
        calls.append(("request", (value, kwargs)))
        return resolved

    monkeypatch.setattr(api, "render_request_from_intent", render_request_from_intent)
    backend = ReadioBackend(app=cast(Readio, object()))

    assert backend.request_from_intent(paths, request) is resolved
    assert calls == [
        (
            "request",
            (
                intent,
                {
                    "source": request.source,
                    "bundle": paths.bundle,
                    "profile": paths.profile,
                    "rebuild_from": "render",
                    "replace_output": True,
                },
            ),
        )
    ]


def test_inspect_and_render_map_public_gateway_results() -> None:
    request = cast(RenderRequest, object())
    step = SimpleNamespace(
        stage="render",
        package="readio",
        action="reuse",
        selector="book",
        reason="Artifact is valid",
        state="ready",
    )
    plan = SimpleNamespace(
        source=Path("book.epub"),
        workspace=Path("book.ssmd-bundle"),
        workspace_mode="bundle",
        output=Path("book.m4b"),
        steps=(step,),
        warnings=("warning",),
        variant="specialist-variant",
    )
    result = SimpleNamespace(
        output=Path("book.m4b"),
        workspace=Path("book.ssmd-bundle"),
        workspace_mode="bundle",
        executed_stages=("compose",),
        reused_stages=("render",),
        warnings=("warning",),
        variant="specialist-variant",
    )
    calls: list[tuple[str, object]] = []

    events: list[ApplicationEvent] = []
    event = WorkflowEvent(
        stage="render",
        kind="stage.progress",
        package="voicerender",
        selector="chapter-2",
        current=2,
        total=3,
        message="Rendering chapter",
        elapsed_seconds=1.5,
        details={"attempt": 1},
    )

    def inspect(value: RenderRequest) -> object:
        calls.append(("inspect", value))
        return plan

    def render(value: RenderRequest, *, on_progress=None) -> object:
        calls.append(("render", (value, on_progress)))
        assert on_progress is not None
        on_progress(event)
        return result

    backend = ReadioBackend(
        app=cast(Readio, SimpleNamespace(inspect=inspect, render=render))
    )

    workflow = backend.inspect(request)
    conversion = backend.render(request, on_progress=events.append)

    assert workflow.steps[0].stage == "render"
    assert workflow.variant == "specialist-variant"
    assert conversion.variant == "specialist-variant"
    assert workflow.steps[0].state == "ready"
    assert workflow.warnings == ("warning",)
    assert conversion.executed_stages == ("compose",)
    assert conversion.reused_stages == ("render",)
    assert calls[0] == ("inspect", request)
    assert calls[1][0] == "render"
    assert calls[1][1][0] is request
    assert callable(calls[1][1][1])
    assert events == [
        ApplicationEvent(
            stage="render",
            kind="stage.progress",
            message="Rendering chapter",
            package="voicerender",
            selector="chapter-2",
            current=2,
            total=3,
            elapsed_seconds=1.5,
            details={"attempt": 1},
        )
    ]


def test_normalize_workflow_error_retains_public_stage_context() -> None:
    error = WorkflowStageError(
        "render",
        "The engine runtime is unavailable.",
        package="voicerender",
        selector="chapter-2",
        code="engine_unavailable",
        cause=RuntimeError("missing runtime"),
        details={"retryable": True},
    )

    normalized = backend_module.normalize_readio_error(error)

    assert isinstance(normalized, WorkflowFailureError)
    assert normalized.category == "render-stage failure"
    assert normalized.stage == "render"
    assert normalized.package == "voicerender"
    assert normalized.selector == "chapter-2"
    assert normalized.code == "engine_unavailable"
    assert normalized.details == {"retryable": True}


def test_render_failure_reports_persisted_setup_paths() -> None:
    profile = Path("book.ttsforge/narrator.renderprofile.toml")
    request = RenderRequest(source=Path("book.epub"), profile=profile)

    def render(value: RenderRequest, *, on_progress=None) -> object:
        raise WorkflowStageError(
            "render",
            "The engine runtime is unavailable.",
            package="voicerender",
            cause=RuntimeError("missing runtime"),
        )

    backend = ReadioBackend(
        app=cast(Readio, SimpleNamespace(inspect=lambda value: None, render=render))
    )

    with pytest.raises(WorkflowFailureError) as raised:
        backend.render(request)

    assert raised.value.category == "render-stage failure"
    assert raised.value.details["saved_setup"] == {
        "project": str(profile.parent),
        "intent": str(profile.parent / "render.readio.toml"),
        "profile": str(profile),
    }
