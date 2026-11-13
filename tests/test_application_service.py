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
from ttsforge.application.service import _configuration_variant_key


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


def _prepare_saved_variant_project(
    backend: _FakeBackend, source: Path, tmp_path: Path
) -> AudiobookRequest:
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    saved = replace(
        _saved_request(source),
        spacy="off",
        speech_profile=Path("speech.toml"),
        pause_timing="engaging",
    )
    backend.saved = saved
    return saved


def test_new_variant_requires_an_existing_base_setup(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"

    with pytest.raises(
        InputValidationError, match="requires an existing TTSForge project"
    ):
        service.prepare_setup(
            AudiobookRequest(source=source, new_variant=True), InputOverrides()
        )

    assert not ProjectPaths.for_source(source).root.exists()
    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_new_variant_inherits_shared_setup_and_clears_saved_synthesis_choices(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    saved = _prepare_saved_variant_project(backend, source, tmp_path)

    preparation = service.prepare_setup(
        AudiobookRequest(source=source, new_variant=True), InputOverrides()
    )

    request = preparation.request
    assert preparation.reused
    assert request.new_variant
    assert request.chapters == saved.chapters
    assert request.language == saved.language
    assert request.spacy == saved.spacy
    assert request.speech_profile == saved.speech_profile
    assert request.pause_timing == saved.pause_timing
    assert request.output == saved.output
    assert request.title == saved.title
    assert request.author == saved.author
    assert request.engine is None
    assert request.target is None
    assert request.voice is None
    assert request.engine_options == {}
    assert request.speed is None
    assert all(
        preparation.origins.needs_input(name) for name in ("engine", "target", "voice")
    )
    assert all(
        not preparation.origins.needs_input(name)
        for name in ("chapters", "language", "spacy", "speech_profile", "pause_timing")
    )
    assert backend.saved == saved


def test_noninteractive_new_variant_requires_engine_and_target(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    _prepare_saved_variant_project(backend, source, tmp_path)

    with pytest.raises(
        InputValidationError,
        match=(
            r"--new-variant in non-interactive mode requires explicit "
            r"--engine and --target"
        ),
    ):
        service.prepare_setup(
            AudiobookRequest(source=source, new_variant=True),
            InputOverrides(),
            interactive=False,
        )


def test_noninteractive_new_variant_preserves_explicit_synthesis_choices(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    _prepare_saved_variant_project(backend, source, tmp_path)
    request = AudiobookRequest(
        source=source,
        new_variant=True,
        engine="engine-b",
        target="target-b",
        voice="voice-b",
        engine_options={"quality": "medium"},
        speed=1.2,
    )

    preparation = service.prepare_setup(
        request,
        InputOverrides(
            frozenset({"engine", "target", "voice", "engine_options", "speed"})
        ),
        interactive=False,
    )

    assert preparation.request.engine == "engine-b"
    assert preparation.request.target == "target-b"
    assert preparation.request.voice == "voice-b"
    assert preparation.request.engine_options == {"quality": "medium"}
    assert preparation.request.speed == 1.2


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("chapters", "1-2"),
        ("language", "fr-FR"),
        ("spacy", "md"),
        ("speech_profile", Path("other.toml")),
        ("pause_timing", "natural"),
    ],
)
def test_new_variant_rejects_shared_preparation_changes(
    tmp_path: Path, field_name: str, value: object
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    _prepare_saved_variant_project(backend, source, tmp_path)
    request = AudiobookRequest(source=source, new_variant=True, **{field_name: value})

    with pytest.raises(ProjectScopeConflictError, match="--new-variant cannot change"):
        service.prepare_setup(request, InputOverrides(frozenset({field_name})))


def test_new_variant_accepts_unchanged_shared_preparation_overrides(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    saved = _prepare_saved_variant_project(backend, source, tmp_path)
    request = AudiobookRequest(
        source=source,
        new_variant=True,
        chapters="4,2,3",
        language=saved.language,
        spacy=saved.spacy,
        speech_profile=saved.speech_profile,
        pause_timing=saved.pause_timing,
    )
    fields = frozenset(
        {"chapters", "language", "spacy", "speech_profile", "pause_timing"}
    )

    preparation = service.prepare_setup(request, InputOverrides(fields))

    assert preparation.request.chapters == "2-4"
    assert preparation.request.language == saved.language
    assert preparation.request.spacy == saved.spacy
    assert preparation.request.speech_profile == saved.speech_profile
    assert preparation.request.pause_timing == saved.pause_timing


def _prepare_resolvable_variant(
    backend: _FakeBackend,
    service: AudiobookApplicationService,
    source: Path,
    output: Path | None = None,
):
    request = AudiobookRequest(
        source=source,
        new_variant=True,
        engine="engine-b",
        target="target-b",
        voice="voice-b",
        output=output,
    )
    fields = {"engine", "target", "voice"}
    if output is not None:
        fields.add("output")
    preparation = service.prepare_setup(
        request, InputOverrides(frozenset(fields)), interactive=False
    )
    return preparation


def test_variant_key_is_deterministic_sanitized_and_bounded() -> None:
    request = AudiobookRequest(
        source=Path("book.epub"),
        engine="piper/" + "e" * 80,
        target="../en_US\\" + "t" * 80,
        voice="voice/../one",
        engine_options={"b": 2, "a": 1},
        speed=1.1,
    )
    reordered = replace(request, engine_options={"a": 1, "b": 2})

    key = _configuration_variant_key(request)

    assert key == _configuration_variant_key(reordered)
    assert len(key) <= 64
    assert "/" not in key
    assert "\\" not in key
    assert ".." not in key
    digest = key.rsplit("-", 1)[-1]
    assert len(digest) == 8
    assert all(character in "0123456789abcdef" for character in digest)


def test_new_variant_saves_separate_setup_and_keeps_base_files_unchanged(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    base_request = _prepare_saved_variant_project(backend, source, tmp_path)
    base_output = tmp_path / "Platform Decay - Martha Wells.m4b"
    base_request = replace(base_request, output=base_output)
    backend.saved = base_request
    base_paths = ProjectPaths.for_source(source)
    base_paths.intent.write_bytes(b"base intent")
    base_paths.profile.write_bytes(b"base profile")
    base_intent = base_paths.intent.read_bytes()
    base_profile = base_paths.profile.read_bytes()
    preparation = service.prepare_setup(
        AudiobookRequest(source=source, new_variant=True), InputOverrides()
    )
    selected = replace(
        preparation.request,
        engine="engine-b",
        target="target-b",
        voice="voice-b",
    )

    resolved = service.save_setup(preparation, selected)

    variant_paths = resolved.preparation.paths
    assert variant_paths.root == base_paths.root
    assert variant_paths.bundle == base_paths.bundle
    assert variant_paths.variant_key is not None
    assert variant_paths.intent == (
        base_paths.root / "variants" / variant_paths.variant_key / "render.readio.toml"
    )
    assert variant_paths.profile == (
        base_paths.root
        / "variants"
        / variant_paths.variant_key
        / "narrator.renderprofile.toml"
    )
    assert variant_paths.intent.is_file()
    assert variant_paths.profile.is_file()
    assert resolved.request.output == tmp_path / (
        f"Platform Decay - Martha Wells [{variant_paths.variant_key}].m4b"
    )
    assert resolved.request.output != base_output
    assert not resolved.request.replace_output
    assert base_paths.intent.read_bytes() == base_intent
    assert base_paths.profile.read_bytes() == base_profile


@pytest.mark.parametrize("output_kind", ["base", "project"])
def test_new_variant_rejects_base_or_project_output_paths(
    tmp_path: Path, output_kind: str
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    saved = _prepare_saved_variant_project(backend, source, tmp_path)
    paths = ProjectPaths.for_source(source)
    output = saved.output if output_kind == "base" else paths.root / "other.m4b"
    preparation = _prepare_resolvable_variant(backend, service, source, output=output)

    message = (
        "must differ from the base audiobook output"
        if output_kind == "base"
        else "cannot be inside the TTSForge project"
    )
    with pytest.raises(InputValidationError, match=message):
        service.save_setup(preparation)
    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_new_variant_rejects_source_as_explicit_output(tmp_path: Path) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.m4b"
    _prepare_saved_variant_project(backend, source, tmp_path)
    preparation = _prepare_resolvable_variant(backend, service, source, output=source)

    with pytest.raises(InputValidationError, match="cannot be the source file"):
        service.save_setup(preparation)
    assert not any(call[0] == "save_setup" for call in backend.calls)


def test_variant_inventory_reports_valid_incomplete_and_malformed_setups(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    service = AudiobookApplicationService(backend)
    source = tmp_path / "book.epub"
    saved = _prepare_saved_variant_project(backend, source, tmp_path)
    paths = ProjectPaths.for_source(source)
    variants_root = paths.root / "variants"

    valid_paths = ProjectPaths.for_variant(paths.root, "valid")
    valid_paths.setup_root.mkdir(parents=True)
    valid_paths.intent.touch()
    valid_paths.profile.touch()
    incomplete = variants_root / "incomplete"
    incomplete.mkdir()
    (incomplete / "render.readio.toml").touch()
    malformed_paths = ProjectPaths.for_variant(paths.root, "malformed")
    malformed_paths.setup_root.mkdir()
    malformed_paths.intent.touch()
    malformed_paths.profile.touch()
    backend.load_setup = lambda variant_paths: (
        (_ for _ in ()).throw(ValueError("bad intent"))
        if variant_paths.variant_key == "malformed"
        else saved
    )

    variants = service.list_variants(paths, source=source)

    assert [variant.variant_key for variant in variants] == [
        "incomplete",
        "malformed",
        "valid",
    ]
    assert "Incomplete setup" in (variants[0].error or "")
    assert "bad intent" in (variants[1].error or "")
    assert variants[2].error is None
    assert variants[2].output == saved.output
    assert variants[2].engine == saved.engine
    assert variants[2].target == saved.target
    assert variants[2].voice == saved.voice
