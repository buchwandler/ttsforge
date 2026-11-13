from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ttsforge.application import (
    AudiobookApplicationService,
    AudiobookRequest,
    BlockedWorkflowError,
    BookChapterView,
    BookInspectionView,
    ConversionResultView,
    InputOverrides,
    InputValidationError,
    LegacyWorkspaceError,
    OperationConflictError,
    ProjectPaths,
    ProjectScopeConflictError,
    WorkflowPlanView,
    WorkflowStepView,
    blocked_workflow_steps,
    require_runnable_workflow,
)


def _inspection(source: Path) -> BookInspectionView:
    return BookInspectionView(
        source=source,
        kind="book",
        title="A title",
        author="An author",
        language="en-US",
        chapters=(
            BookChapterView(number=1, title="Opening", source_id="c1"),
            BookChapterView(number=2, title="Arrival", source_id="c2"),
            BookChapterView(number=3, title="Conflict", source_id="c3"),
            BookChapterView(number=4, title="Ending", source_id="c4"),
        ),
    )


def _saved_request(source: Path) -> AudiobookRequest:
    return AudiobookRequest(
        source=source,
        language="de-DE",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
        chapters="2-4",
        output=Path("saved.m4b"),
        engine_options={"quality": "high"},
        speed=1.1,
        bitrate="128k",
        target_lufs=-19.0,
        title="Saved title",
        author="Saved author",
    )


class _FakeBackend:
    def __init__(self) -> None:
        self.saved: AudiobookRequest | None = None
        self.calls: list[tuple[object, ...]] = []
        self.fail_render = False

    def inspect_source(self, source: Path) -> BookInspectionView:
        self.calls.append(("inspect_source", source))
        return _inspection(source)

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        self.calls.append(("load_setup", paths.root))
        assert self.saved is not None
        return self.saved

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None:
        self.calls.append(("save_setup", paths.root, request))
        paths.intent.touch()
        paths.profile.touch()
        self.saved = request

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object:
        self.calls.append(("request_from_intent", paths.root, request))
        return (paths, request)

    def inspect(self, request: object) -> WorkflowPlanView:
        self.calls.append(("preflight", request))
        paths, selected = request  # type: ignore[misc]
        return WorkflowPlanView(
            source=selected.source,
            workspace=paths.bundle,
            workspace_mode="bundle",
            output=selected.output,
            steps=(),
        )

    def render(self, request: object, *, on_progress=None) -> ConversionResultView:
        self.calls.append(("render", request, on_progress))
        if self.fail_render:
            self.fail_render = False
            raise RuntimeError("temporary renderer failure")
        paths, selected = request  # type: ignore[misc]
        assert selected.output is not None
        return ConversionResultView(
            output=selected.output,
            workspace=paths.bundle,
            workspace_mode="bundle",
            executed_stages=("render",),
            reused_stages=(),
        )


def test_prepare_setup_uses_source_defaults_and_ttsforge_paths(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"

    preparation = service.prepare_setup(
        AudiobookRequest(source=source), InputOverrides()
    )

    assert preparation.paths.root == tmp_path / "book.ttsforge"
    assert preparation.paths.intent.name == "render.readio.toml"
    assert preparation.paths.profile.name == "narrator.renderprofile.toml"
    assert preparation.paths.bundle.name == "book.ssmd-bundle"
    assert preparation.request.chapters == "all"
    assert "chapters" in preparation.origins.derived
    assert preparation.origins.should_confirm_derived("chapters")
    assert preparation.request.output == tmp_path / "book.m4b"
    assert preparation.request.language == "en-US"
    assert preparation.request.title == "A title"
    assert preparation.origins.needs_input("engine")
    assert preparation.request.spacy == "sm"
    assert preparation.request.pause_timing == "engaging"
    assert preparation.origins.needs_input("spacy")
    assert preparation.origins.needs_input("pause_timing")
    assert preparation.origins.should_confirm_derived("language")
    assert not preparation.origins.needs_input("language")


def test_noninteractive_new_project_uses_explicit_product_defaults(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)

    preparation = service.prepare_setup(
        AudiobookRequest(source=tmp_path / "book.epub"),
        InputOverrides(),
        interactive=False,
    )

    assert preparation.request.spacy == "sm"
    assert preparation.request.pause_timing == "engaging"


def test_legacy_saved_setup_keeps_spacy_and_defaults_pause_to_fixed(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)

    preparation = service.prepare_setup(
        AudiobookRequest(source=source), InputOverrides()
    )

    assert preparation.reused
    assert preparation.request.spacy is None
    assert preparation.request.pause_timing == "fixed"
    assert not preparation.origins.needs_input("spacy")
    assert not preparation.origins.needs_input("speech_profile")
    assert not preparation.origins.needs_input("pause_timing")


@pytest.mark.parametrize(
    ("changes", "initial_rebuild", "expected"),
    [
        ({"spacy": "sm"}, "render", "convert"),
        ({"speech_profile": Path("speech.toml")}, None, "convert"),
        ({"pause_timing": "natural"}, "export", "render_plan"),
        ({"spacy": "md", "pause_timing": "engaging"}, "render", "convert"),
    ],
)
def test_specialist_setting_changes_select_earliest_rebuild(
    tmp_path: Path,
    changes: dict[str, object],
    initial_rebuild: str | None,
    expected: str,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)
    request = AudiobookRequest(
        source=source,
        rebuild_from=initial_rebuild,
        **changes,
    )

    preparation = service.prepare_setup(
        request,
        InputOverrides(frozenset(changes)),
        interactive=False,
    )

    assert preparation.request.rebuild_from == expected


def test_language_change_rebuilds_from_convert(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = replace(
        _saved_request(source),
        engine=None,
        target=None,
        voice=None,
        engine_options={},
        speed=None,
    )

    preparation = service.prepare_setup(
        AudiobookRequest(source=source, language="fr-FR"),
        InputOverrides(frozenset({"language"})),
        interactive=False,
    )

    assert preparation.request.language == "fr-FR"
    assert preparation.request.rebuild_from == "convert"


def test_saved_setup_precedence_and_dependent_choice_invalidation(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    project = tmp_path / "custom.ttsforge"
    paths = ProjectPaths.for_root(project)
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)
    explicit_output = tmp_path / "explicit.m4b"
    request = AudiobookRequest(
        source=source,
        project=project,
        engine="engine-b",
        output=explicit_output,
    )

    preparation = service.prepare_setup(
        request,
        InputOverrides(frozenset({"engine", "output"})),
    )

    assert preparation.reused
    assert preparation.request.engine == "engine-b"
    assert preparation.request.language == "de-DE"
    assert preparation.request.output == explicit_output
    assert preparation.request.chapters == "2-4"
    assert preparation.request.target is None
    assert preparation.request.voice is None
    assert preparation.request.engine_options == {}
    assert preparation.request.speed is None
    assert not preparation.origins.needs_input("chapters")
    assert "chapters" in preparation.origins.project
    assert not preparation.origins.should_confirm_derived("chapters")
    assert preparation.origins.needs_input("target")
    assert preparation.request.pause_timing == "fixed"
    assert preparation.request.spacy is None
    assert not preparation.origins.needs_input("spacy")
    assert not preparation.origins.needs_input("speech_profile")


def test_setup_is_persisted_before_preflight_and_render(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    request = AudiobookRequest(
        source=source,
        language="en-US",
        engine="engine-a",
        target="target-a",
    )
    preparation = service.prepare_setup(request, InputOverrides())

    resolved = service.save_setup(preparation)
    preflight = service.preflight(resolved)
    result = service.render(resolved)

    assert preflight.workflow.source == source
    assert preflight.workflow.workspace == preparation.paths.bundle
    assert result.output == tmp_path / "book.m4b"
    assert [call[0] for call in backend.calls[-4:]] == [
        "save_setup",
        "request_from_intent",
        "preflight",
        "render",
    ]


def test_status_inspects_saved_state_without_rewriting_it(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)

    status = service.status(paths)

    assert status.source == source
    assert [call[0] for call in backend.calls] == [
        "load_setup",
        "request_from_intent",
        "preflight",
    ]


def test_fresh_setup_uses_a_separate_project_directory(tmp_path: Path) -> None:
    old_root = tmp_path / "book.ttsforge"
    old_root.mkdir()
    (old_root / "user-data.txt").write_text("keep", encoding="utf-8")
    service = AudiobookApplicationService(_FakeBackend())

    preparation = service.prepare_setup(
        AudiobookRequest(source=tmp_path / "book.epub", fresh=True),
        InputOverrides(),
    )

    assert preparation.paths.root == tmp_path / "book.fresh.ttsforge"
    assert (old_root / "user-data.txt").read_text(encoding="utf-8") == "keep"


def test_legacy_workspace_is_rejected_without_mutation(tmp_path: Path) -> None:
    legacy = tmp_path / "book.ssmdbook"
    legacy.mkdir()
    marker = legacy / "project.toml"
    marker.write_text("legacy", encoding="utf-8")
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)

    with pytest.raises(LegacyWorkspaceError, match="TTSForge/Readio 0.4 project"):
        service.prepare_setup(
            AudiobookRequest(source=tmp_path / "book.epub", project=legacy),
            InputOverrides(),
        )

    assert marker.read_text(encoding="utf-8") == "legacy"
    assert backend.calls == []

    with pytest.raises(LegacyWorkspaceError, match="TTSForge/Readio 0.4 project"):
        service.status(ProjectPaths.for_root(legacy))
    assert marker.read_text(encoding="utf-8") == "legacy"
    assert backend.calls == []


def test_partial_saved_setup_is_rejected(tmp_path: Path) -> None:
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    service = AudiobookApplicationService(_FakeBackend())

    with pytest.raises(OperationConflictError, match="intent and profile"):
        service.prepare_setup(
            AudiobookRequest(source=tmp_path / "book.epub"), InputOverrides()
        )


def test_failed_render_keeps_saved_setup_for_retry(tmp_path: Path) -> None:
    backend = _FakeBackend()
    backend.fail_render = True
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    original = AudiobookRequest(
        source=source,
        language="en-US",
        engine="engine-a",
        target="target-a",
        spacy="lg",
        speech_profile=tmp_path / "speech.toml",
        pause_timing="natural",
    )
    preparation = service.prepare_setup(original, InputOverrides())
    resolved = service.save_setup(preparation)

    with pytest.raises(RuntimeError, match="temporary renderer failure"):
        service.render(resolved)

    assert preparation.paths.intent.is_file()
    assert preparation.paths.profile.is_file()
    retry = service.prepare_setup(AudiobookRequest(source=source), InputOverrides())

    assert retry.reused
    assert retry.request.language == "en-US"
    assert retry.request.engine == "engine-a"
    assert retry.request.target == "target-a"
    assert retry.request.spacy == "lg"
    assert retry.request.speech_profile == tmp_path / "speech.toml"
    assert retry.request.pause_timing == "natural"
    assert not retry.origins.needs_input("engine")
    assert not retry.origins.needs_input("target")
    result = service.render(service.save_setup(retry))

    assert result.output == tmp_path / "book.m4b"


def test_saved_default_voice_is_not_prompted_again(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = replace(_saved_request(source), voice=None)

    preparation = service.prepare_setup(
        AudiobookRequest(source=source), InputOverrides()
    )

    assert preparation.request.voice is None
    assert "voice" in preparation.origins.project
    assert not preparation.origins.needs_input("voice")


def test_non_m4b_output_is_rejected_before_project_persistence(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    preparation = service.prepare_setup(
        AudiobookRequest(
            source=source,
            language="en-US",
            engine="engine-a",
            target="target-a",
            output=tmp_path / "book.mp3",
        ),
        InputOverrides(),
    )

    with pytest.raises(InputValidationError, match=".m4b extension"):
        service.save_setup(preparation)

    assert not preparation.paths.root.exists()
    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_explicit_chapter_selection_is_normalized_and_marked_explicit(
    tmp_path: Path,
) -> None:
    service = AudiobookApplicationService(_FakeBackend())
    source = tmp_path / "book.epub"

    preparation = service.prepare_setup(
        AudiobookRequest(source=source, chapters="3,1,2"),
        InputOverrides(frozenset({"chapters"})),
    )

    assert preparation.request.chapters == "1-3"
    assert "chapters" in preparation.origins.explicit
    assert not preparation.origins.should_confirm_derived("chapters")


def test_invalid_explicit_chapters_fail_during_setup_preparation(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)

    with pytest.raises(InputValidationError, match="Chapter 9 exceeds"):
        service.prepare_setup(
            AudiobookRequest(source=tmp_path / "book.epub", chapters="9"),
            InputOverrides(frozenset({"chapters"})),
        )

    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_explicit_chapter_scope_conflict_does_not_overwrite_saved_project(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)

    with pytest.raises(ProjectScopeConflictError, match="--fresh.*--project"):
        service.prepare_setup(
            AudiobookRequest(source=source, chapters="all"),
            InputOverrides(frozenset({"chapters"})),
        )

    assert backend.saved.chapters == "2-4"
    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_equivalent_explicit_chapter_scope_is_accepted(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved = _saved_request(source)

    preparation = service.prepare_setup(
        AudiobookRequest(source=source, chapters="4,2,3"),
        InputOverrides(frozenset({"chapters"})),
    )

    assert preparation.request.chapters == "2-4"
    assert preparation.reused


def test_blocked_workflow_steps_preserve_stage_reasons_and_public_fields() -> None:
    compose = WorkflowStepView(
        stage="compose",
        package="audiocompose",
        action="blocked",
        selector="selected-voice",
        reason="Selected composition work failed.",
        state="error",
    )
    export = WorkflowStepView(
        stage="export",
        package="audioexport",
        action="blocked",
        selector=None,
        reason="Composition output is unavailable.",
        state="error",
    )
    plan = WorkflowPlanView(
        source=Path("book.epub"),
        workspace=None,
        workspace_mode="none",
        output=Path("book.m4b"),
        steps=(
            WorkflowStepView(
                stage="render",
                package="voicerender",
                action="reuse",
                selector=None,
                reason="Already complete.",
                state="complete",
            ),
            compose,
            export,
        ),
    )

    blocked = blocked_workflow_steps(plan)
    with pytest.raises(BlockedWorkflowError) as error_info:
        require_runnable_workflow(plan)
    error = error_info.value

    assert blocked == (compose, export)
    assert str(error) == (
        "Workflow is blocked: compose: Selected composition work failed.; "
        "export: Composition output is unavailable."
    )
    assert error.code == "workflow_blocked"
    assert error.details["blocked_steps"] == [
        {
            "stage": "compose",
            "action": "blocked",
            "state": "error",
            "reason": "Selected composition work failed.",
            "package": "audiocompose",
            "selector": "selected-voice",
        },
        {
            "stage": "export",
            "action": "blocked",
            "state": "error",
            "reason": "Composition output is unavailable.",
            "package": "audioexport",
            "selector": None,
        },
    ]
