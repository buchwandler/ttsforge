from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ttsforge.application import (
    AudiobookApplicationService,
    AudiobookRequest,
    BlockedWorkflowError,
    BookChapterView,
    BookInspectionView,
    CatalogApplicationService,
    ConversionCoordinator,
    ConversionResultView,
    InputOverrides,
    InputValidationError,
    SpacyModelView,
    WorkflowPlanView,
    WorkflowStepView,
)


class FakeBackend:
    def __init__(self, *, kind: str = "book", blocked: bool = False) -> None:
        self.calls: list[str] = []
        self.kind = kind
        self.blocked = blocked
        self.spacy_installed = False

    def inspect_source(self, source: Path) -> BookInspectionView:
        self.calls.append("inspect_source")
        return BookInspectionView(
            source=source,
            kind=self.kind,
            title="Book",
            author="Author",
            language="en-US",
            chapters=(BookChapterView(1, "Chapter One"),),
        )

    def load_setup(self, paths: object) -> AudiobookRequest:
        raise AssertionError("no saved setup expected")

    def save_setup(self, paths: object, request: AudiobookRequest) -> None:
        self.calls.append("save_setup")

    def request_from_intent(self, paths: object, request: AudiobookRequest) -> object:
        self.calls.append("request_from_intent")
        return request

    def inspect(self, request: object) -> WorkflowPlanView:
        self.calls.append("preflight")
        steps = (
            (
                WorkflowStepView(
                    stage="export",
                    package="audioexport",
                    action="blocked",
                    selector=None,
                    reason="Exporter missing",
                    state="error",
                ),
            )
            if self.blocked
            else ()
        )
        return WorkflowPlanView(
            source=Path("book.epub"),
            workspace=None,
            workspace_mode="none",
            output=Path("book.m4b"),
            steps=steps,
        )

    def render(self, request: object, *, on_progress=None) -> ConversionResultView:
        self.calls.append("render")
        return ConversionResultView(
            output=Path("book.m4b"),
            workspace=None,
            workspace_mode="none",
            executed_stages=("render",),
            reused_stages=(),
        )

    def list_engines(self) -> tuple[object, ...]:
        return ({"id": "kokoro"},)

    def list_targets(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append("targets")
        return (
            SimpleNamespace(
                id="target-a",
                languages=("en-US",),
                default_voice="voice-a",
                voices=("voice-a",),
                capabilities=("named_voices",),
            ),
        )

    def list_engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[object, ...]:
        return ()

    def list_voices(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append("voices")
        return (SimpleNamespace(id="voice-a", language="en-US"),)

    def list_spacy_models(self, language: str) -> tuple[SpacyModelView, ...]:
        return (self.inspect_spacy_model(language, "lg"),)

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView:
        self.calls.append("spacy_inspect")
        return SpacyModelView(
            language, tier, "en_core_web_lg", self.spacy_installed, "3.8", None
        )

    def ensure_spacy_model(
        self, language: str, tier: str, *, offline: bool = False
    ) -> SpacyModelView:
        self.calls.append("spacy_ensure")
        if offline and not self.spacy_installed:
            raise InputValidationError("spaCy model is missing in offline mode.")
        self.spacy_installed = True
        return SpacyModelView(language, tier, "en_core_web_lg", True, "3.8", "3.8.0")

    def inspect_voice(self, selector: str, *, language: str | None = None) -> object:
        return SimpleNamespace(id=selector, language=language)


class RecordingApplicationService(AudiobookApplicationService):
    def __init__(self, backend: FakeBackend) -> None:
        super().__init__(backend)
        self.interactive_modes: list[bool] = []

    def prepare_setup(self, request, overrides, *, interactive=True):
        self.interactive_modes.append(interactive)
        return super().prepare_setup(request, overrides, interactive=interactive)


def _request(
    source: Path, *, spacy: str = "lg", new_variant: bool = False
) -> AudiobookRequest:
    return AudiobookRequest(
        source=source,
        language="en-US",
        engine="kokoro",
        target="target-a",
        voice="voice-a",
        spacy=spacy,
        new_variant=new_variant,
    )


def _coordinator(backend: FakeBackend):
    audiobook = RecordingApplicationService(backend)
    catalog = CatalogApplicationService(backend)
    return ConversionCoordinator(audiobook, catalog), audiobook


def test_prepare_uses_noninteractive_setup_and_orders_shared_finalization(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    coordinator, audiobook = _coordinator(backend)

    prepared = coordinator.prepare(_request(tmp_path / "book.epub"), InputOverrides())

    assert audiobook.interactive_modes == [False]
    assert backend.calls.index("targets") < backend.calls.index("save_setup")
    assert backend.calls.index("voices") < backend.calls.index("save_setup")
    assert backend.calls.index("save_setup") < backend.calls.index("spacy_inspect")
    assert backend.calls.index("spacy_inspect") < backend.calls.index("spacy_ensure")
    assert backend.calls.index("spacy_ensure") < backend.calls.index("preflight")
    assert prepared.spacy_model is not None and prepared.spacy_model.installed


def test_off_and_auto_spacy_do_not_inspect_or_provision_models(tmp_path: Path) -> None:
    for tier in ("off", "auto"):
        backend = FakeBackend()
        coordinator, _ = _coordinator(backend)

        prepared = coordinator.prepare(
            _request(tmp_path / f"{tier}.epub", spacy=tier), InputOverrides()
        )

        assert prepared.spacy_model is None
        assert "spacy_inspect" not in backend.calls
        assert "spacy_ensure" not in backend.calls


def test_reference_only_target_is_rejected_before_setup_is_saved(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    backend.list_targets = lambda **kwargs: (
        SimpleNamespace(
            id="target-a",
            languages=("en-US",),
            voices=(),
            capabilities=("reference_voice",),
            metadata={"supports_reference_enrollment": True},
        ),
    )
    coordinator, _ = _coordinator(backend)

    with pytest.raises(InputValidationError, match="requires reference audio"):
        coordinator.prepare(_request(tmp_path / "book.epub"), InputOverrides())

    assert "save_setup" not in backend.calls


def test_non_book_source_is_rejected_before_catalog_or_setup_work(
    tmp_path: Path,
) -> None:
    backend = FakeBackend(kind="directory")
    coordinator, _ = _coordinator(backend)

    with pytest.raises(InputValidationError, match="requires a book source"):
        coordinator.prepare(_request(tmp_path / "folder"), InputOverrides())

    assert backend.calls == ["inspect_source"]


def test_blocked_preflight_prevents_execution(tmp_path: Path) -> None:
    backend = FakeBackend(blocked=True)
    coordinator, _ = _coordinator(backend)

    with pytest.raises(BlockedWorkflowError):
        coordinator.prepare(
            _request(tmp_path / "book.epub", spacy="off"), InputOverrides()
        )

    assert "preflight" in backend.calls
    assert "render" not in backend.calls
