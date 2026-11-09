from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import WorkflowStageError
from rich.console import Console
from typer.testing import CliRunner

from ttsforge.application.errors import InputValidationError, WorkflowFailureError
from ttsforge.application.models import (
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ConversionResultView,
    InputOverrides,
    ProjectPaths,
    SetupOrigins,
    SetupPreparation,
    SpacyModelView,
    WorkflowPlanView,
)
from ttsforge.application.service import AudiobookApplicationService
from ttsforge.cli import app
from ttsforge.cli.interaction import InteractionMode

cli_app = import_module("ttsforge.cli.app")


class _Backend:
    def __init__(self) -> None:
        self.saved: dict[Path, AudiobookRequest] = {}
        self.calls: list[tuple[object, ...]] = []
        self.render_error: Exception | None = None
        self.render_request: tuple[ProjectPaths, AudiobookRequest] | None = None
        self.spacy_installed = True

    def inspect_source(self, source: Path) -> BookInspectionView:
        self.calls.append(("source", source))
        return BookInspectionView(
            source=source.resolve(),
            kind="book",
            title="Book title",
            author="Writer",
            language="en-US",
            chapters=(BookChapterView(1, "Opening", "c1", 100),),
        )

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        self.calls.append(("load", paths.root))
        return self.saved[paths.root]

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None:
        self.calls.append(("save", paths.root, request))
        paths.intent.touch()
        paths.profile.touch()
        self.saved[paths.root] = request

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object:
        self.calls.append(("request", paths.root, request))
        self.render_request = (paths, request)
        return paths, request

    def inspect(self, request: object) -> WorkflowPlanView:
        self.calls.append(("inspect", request))
        paths, selected = request  # type: ignore[misc]
        return WorkflowPlanView(
            source=selected.source,
            workspace=paths.bundle,
            workspace_mode="bundle",
            output=selected.output,
            steps=(),
        )

    def render(self, request: object, *, on_progress=None) -> ConversionResultView:
        self.calls.append(("render", request))
        if self.render_error is not None:
            raise self.render_error
        paths, selected = request  # type: ignore[misc]
        assert selected.output is not None
        return ConversionResultView(
            output=selected.output,
            workspace=paths.bundle,
            workspace_mode="bundle",
            executed_stages=("render", "compose", "export"),
            reused_stages=("convert", "compile"),
        )

    def list_engines(self) -> tuple[object, ...]:
        self.calls.append(("engines",))
        return ({"id": "engine-a", "name": "Engine A"},)

    def list_targets(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append(("targets", kwargs))
        return ({"id": "target-a", "engine": "engine-a", "language": "en-US"},)

    def list_voices(self, **kwargs: object) -> tuple[object, ...]:
        self.calls.append(("voices", kwargs))
        return ({"id": "voice-a", "engine": "engine-a", "language": "en-US"},)

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView:
        self.calls.append(("spacy_inspect", language, tier))
        return SpacyModelView(
            language=language,
            tier=tier,
            model=f"en_core_web_{tier}",
            installed=self.spacy_installed,
            spacy_version="3.8.16",
            model_version="3.8.0" if self.spacy_installed else None,
        )

    def ensure_spacy_model(
        self, language: str, tier: str, *, offline: bool = False
    ) -> SpacyModelView:
        self.calls.append(("spacy_ensure", language, tier, offline))
        if offline and not self.spacy_installed:
            raise InputValidationError("spaCy model is missing in offline mode.")
        self.spacy_installed = True
        return SpacyModelView(
            language=language,
            tier=tier,
            model=f"en_core_web_{tier}",
            installed=True,
            spacy_version="3.8.16",
            model_version="3.8.0",
        )


def _invoke(
    monkeypatch,
    backend: _Backend,
    args: list[str],
    *,
    mode: InteractionMode | None = None,
):
    service = AudiobookApplicationService(backend)
    mode = mode or InteractionMode(
        interactive=False,
        json=True,
        live_progress=False,
        confirm=False,
    )
    monkeypatch.setattr(cli_app, "_service", lambda: (backend, service))
    monkeypatch.setattr(cli_app, "resolve_interaction_mode", lambda **kwargs: mode)
    return CliRunner().invoke(app, args, color=False, env={"FORCE_COLOR": ""})


def _setup_prompt(text: str, **kwargs: object) -> str:
    if text == "spaCy model":
        return str(kwargs["default"])
    if text == "Speech replacement profile (optional)":
        return ""
    if text.startswith("Pause timing"):
        return str(kwargs["default"])
    return "1"


def _language_prompt(text: str, **kwargs: object) -> str:
    return "de" if text == "Language" else _setup_prompt(text, **kwargs)


def test_convert_persists_setup_before_preflight_and_uses_m4b(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--spacy",
            "off",
            "--speech-profile",
            str(tmp_path / "speech.toml"),
            "--pause-timing",
            "natural",
            "--replace-output",
            "--rebuild-from",
            "render",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["result"]["output"] == str(tmp_path / "book.m4b")
    assert payload["request"]["replace_output"] is True
    assert payload["request"]["rebuild_from"] == "render"
    assert payload["request"]["spacy"] == "off"
    assert payload["request"]["speech_profile"] == str(tmp_path / "speech.toml")
    assert payload["request"]["pause_timing"] == "natural"
    assert payload["spacy_model"] is None
    assert [call[0] for call in backend.calls[-4:]] == [
        "save",
        "request",
        "inspect",
        "render",
    ]


def test_concrete_spacy_model_is_provisioned_before_preflight(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()
    backend.spacy_installed = False

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--spacy",
            "trf",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["spacy_model"]["model"] == "en_core_web_trf"
    assert payload["spacy_model"]["model_version"] == "3.8.0"
    names = [call[0] for call in backend.calls]
    assert names.index("save") < names.index("spacy_inspect")
    assert names.index("spacy_inspect") < names.index("spacy_ensure")
    assert names.index("spacy_ensure") < names.index("inspect")


def test_offline_missing_spacy_model_fails_before_preflight(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()
    backend.spacy_installed = False

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--spacy",
            "trf",
            "--offline",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "spaCy model is missing in offline mode" in result.output
    names = [call[0] for call in backend.calls]
    assert "save" in names
    assert "spacy_ensure" in names
    assert "inspect" not in names
    assert "render" not in names


def test_auto_spacy_does_not_inspect_or_provision_a_model(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--spacy",
            "auto",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["request"]["spacy"] == "auto"
    assert payload["spacy_model"] is None
    assert not any(call[0].startswith("spacy_") for call in backend.calls)


def test_setup_summary_shows_persisted_settings_and_resolved_spacy(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()
    console_output = StringIO()
    monkeypatch.setattr(
        cli_app,
        "_output",
        Console(file=console_output, width=160, highlight=False, markup=False),
    )
    mode = InteractionMode(
        interactive=False,
        json=False,
        live_progress=False,
        confirm=False,
    )

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--spacy",
            "sm",
            "--speech-profile",
            str(tmp_path / "speech.toml"),
            "--pause-timing",
            "engaging",
            "--yes",
        ],
        mode=mode,
    )

    assert result.exit_code == 0, result.output
    output = console_output.getvalue()
    assert "en_core_web_sm 3.8.0" in output
    assert str(tmp_path / "speech.toml") in output
    assert "engaging" in output


def test_retry_reuses_saved_settings_without_repeating_setup_questions(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    speech_profile = tmp_path / "speech.toml"
    backend = _Backend()
    backend.render_error = WorkflowFailureError(
        "temporary renderer failure", category="render-stage failure"
    )
    mode = InteractionMode(
        interactive=True,
        json=False,
        live_progress=False,
        confirm=False,
    )
    first = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--voice",
            "voice-a",
            "--spacy",
            "md",
            "--speech-profile",
            str(speech_profile),
            "--pause-timing",
            "natural",
            "--yes",
        ],
        mode=mode,
    )

    assert first.exit_code == 1
    assert backend.saved
    saved = next(iter(backend.saved.values()))
    assert saved.spacy == "md"
    assert saved.speech_profile == speech_profile
    assert saved.pause_timing == "natural"
    backend.render_error = None
    monkeypatch.setattr(
        cli_app.typer,
        "prompt",
        lambda *args, **kwargs: pytest.fail("retry must reuse saved setup"),
    )

    retry = _invoke(
        monkeypatch,
        backend,
        ["convert", str(source), "--yes"],
        mode=mode,
    )

    assert retry.exit_code == 0, retry.output
    assert backend.render_request is not None
    request = backend.render_request[1]
    assert request.spacy == "md"
    assert request.speech_profile == speech_profile
    assert request.pause_timing == "natural"
    assert sum(call[0] == "load" for call in backend.calls) == 1


def test_output_replacement_and_stage_rebuild_are_separate_controls(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--replace-output",
            "--rebuild-from",
            "render",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert backend.render_request is not None
    request = backend.render_request[1]
    assert request.replace_output is True
    assert request.rebuild_from == "render"


def test_discovery_commands_return_normalized_json(monkeypatch) -> None:
    backend = _Backend()

    targets_result = _invoke(
        monkeypatch,
        backend,
        ["targets", "--engine", "engine-a", "--language", "en-US", "--json"],
    )
    voices_result = _invoke(
        monkeypatch,
        backend,
        ["voices", "--engine", "engine-a", "--target", "target-a", "--json"],
    )

    assert targets_result.exit_code == 0, targets_result.output
    assert json.loads(targets_result.output)[0]["id"] == "target-a"
    assert voices_result.exit_code == 0, voices_result.output
    assert json.loads(voices_result.output)[0]["id"] == "voice-a"


def test_list_and_info_use_source_inspection_without_creating_a_project(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    listed = _invoke(monkeypatch, backend, ["list", str(source), "--json"])
    info = _invoke(monkeypatch, backend, ["info", str(source), "--json"])

    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["chapters"][0]["title"] == "Opening"
    assert info.exit_code == 0, info.output
    payload = json.loads(info.output)
    assert payload["title"] == "Book title"
    assert payload["project"] == str(tmp_path / "book.ttsforge")
    assert payload["saved_setup"] is None
    assert not (tmp_path / "book.ttsforge").exists()


def test_legacy_project_is_rejected_without_mutation(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    legacy = tmp_path / "old.ssmdbook"
    legacy.mkdir()
    marker = legacy / "project.toml"
    marker.write_text("old state", encoding="utf-8")
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--project",
            str(legacy),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "TTSForge/Readio 0.4 project" in result.output
    assert marker.read_text(encoding="utf-8") == "old state"
    assert backend.calls == []


def test_engines_lists_public_discovery_results_as_json(monkeypatch) -> None:
    backend = _Backend()

    result = _invoke(monkeypatch, backend, ["engines", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["id"] == "engine-a"


def test_status_uses_saved_setup_and_readonly_workflow_inspection(
    monkeypatch, tmp_path: Path
) -> None:
    backend = _Backend()
    paths = ProjectPaths.for_root(tmp_path / "book.ttsforge")
    paths.root.mkdir()
    paths.intent.touch()
    paths.profile.touch()
    backend.saved[paths.root] = AudiobookRequest(
        source=tmp_path / "book.epub",
        language="en-US",
        engine="engine-a",
        target="target-a",
        output=tmp_path / "book.m4b",
    )

    result = _invoke(
        monkeypatch,
        backend,
        ["status", "--project", str(paths.root), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["source"] == str(tmp_path / "book.epub")
    assert [call[0] for call in backend.calls] == [
        "load",
        "request",
        "inspect",
    ]


def test_unknown_rebuild_stage_is_rejected_before_setup(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()

    result = _invoke(
        monkeypatch,
        backend,
        ["convert", str(source), "--rebuild-from", "unknown", "--json"],
    )

    assert result.exit_code == 2
    assert "Choose --rebuild-from" in result.output
    assert backend.calls == []


def test_cli_displays_structured_readio_stage_errors(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    backend = _Backend()
    backend.render_error = WorkflowStageError(
        "render",
        "The engine runtime is unavailable.",
        package="voicerender",
        selector="chapter-2",
        code="engine_unavailable",
        cause=RuntimeError("missing runtime"),
        details={"retryable": True},
    )

    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en-US",
            "--engine",
            "engine-a",
            "--target",
            "target-a",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "Error (render-stage failure)" in result.output
    assert "Stage: render" in result.output
    assert "Package: voicerender" in result.output
    assert "Selector: chapter-2" in result.output
    assert "Code: engine_unavailable" in result.output


def test_interactive_setup_confirms_derived_language_and_filters_discovery(
    monkeypatch, tmp_path: Path
) -> None:
    backend = _Backend()
    preparation = AudiobookApplicationService(backend).prepare_setup(
        AudiobookRequest(source=tmp_path / "book.epub"), InputOverrides()
    )
    preparation = replace(
        preparation,
        request=replace(
            preparation.request,
            engine="saved-engine",
            target="saved-target",
            voice="saved-voice",
            engine_options={"quality": "old"},
            speed=1.2,
        ),
        origins=SetupOrigins(
            project=frozenset({"engine", "target", "voice", "engine_options", "speed"}),
            derived=frozenset({"language"}),
        ),
    )
    prompts: list[tuple[str, object]] = []

    def prompt(text: str, **kwargs: object) -> str:
        prompts.append((text, kwargs))
        if text == "Language":
            return "de"
        return _setup_prompt(text, **kwargs)

    monkeypatch.setattr(cli_app.typer, "prompt", prompt)

    selected = cli_app._complete_interactive_setup(backend, preparation)

    assert selected.language == "de"
    assert selected.engine == "engine-a"
    assert selected.target == "target-a"
    assert selected.voice == "voice-a"
    assert selected.engine_options == {}
    assert selected.speed is None
    assert selected.spacy == "sm"
    assert selected.speech_profile is None
    assert selected.pause_timing == "engaging"
    assert prompts[1] == ("spaCy model", {"default": "sm"})
    assert prompts[-1] == (
        "Pause timing (fixed/natural/engaging)",
        {"default": "engaging"},
    )
    assert prompts[0] == ("Language", {"default": "en-US"})
    target_call = next(call[1] for call in backend.calls if call[0] == "targets")
    assert target_call["language"] == "de"
    voice_call = next(call[1] for call in backend.calls if call[0] == "voices")
    assert voice_call["language"] == "de"


@pytest.mark.parametrize("origin", ["explicit", "project"])
def test_explicit_and_saved_language_suppress_interactive_prompt(
    monkeypatch, tmp_path: Path, origin: str
) -> None:
    backend = _Backend()
    source = tmp_path / "book.epub"
    request = AudiobookRequest(
        source=source,
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
    )
    origins = SetupOrigins(
        explicit=frozenset({"language"}) if origin == "explicit" else frozenset(),
        project=(
            frozenset({"language", "engine", "target", "voice"})
            if origin == "project"
            else frozenset({"engine", "target", "voice"})
        ),
    )
    preparation = SetupPreparation(
        paths=ProjectPaths.for_source(source),
        inspection=backend.inspect_source(source),
        request=request,
        origins=origins,
        reused=origin == "project",
    )

    def unexpected_prompt(text: str, **kwargs: object) -> str:
        if text == "Language":
            pytest.fail("explicit and saved language must not prompt")
        return _setup_prompt(text, **kwargs)

    monkeypatch.setattr(cli_app.typer, "prompt", unexpected_prompt)

    selected = cli_app._complete_interactive_setup(backend, preparation)

    assert selected.language == "en-US"


def test_explicit_voice_is_rejected_when_language_filter_invalidates_it(
    monkeypatch, tmp_path: Path
) -> None:
    backend = _Backend()
    backend.list_voices = lambda **kwargs: ()
    source = tmp_path / "book.epub"
    request = AudiobookRequest(
        source=source,
        language="en-US",
        engine="engine-a",
        target="target-a",
        voice="voice-a",
    )
    preparation = SetupPreparation(
        paths=ProjectPaths.for_source(source),
        inspection=backend.inspect_source(source),
        request=request,
        origins=SetupOrigins(
            explicit=frozenset({"engine", "target", "voice"}),
            derived=frozenset({"language"}),
        ),
        reused=False,
    )
    monkeypatch.setattr(
        cli_app.typer,
        "prompt",
        _language_prompt,
    )

    with pytest.raises(InputValidationError, match="Voice 'voice-a' is not available"):
        cli_app._complete_interactive_setup(backend, preparation)


def test_catalog_lists_curated_human_metadata_and_default_voice(monkeypatch) -> None:
    backend = _Backend()
    backend.list_targets = lambda **kwargs: (
        SimpleNamespace(
            id="target-a",
            languages=("en", "de"),
            status="ready",
            runtime_available=True,
            default_voice="af_heart",
            voices=("af_heart", "af_bella"),
            speakers=(),
            voice_details=(
                SimpleNamespace(
                    language="en", locale="en-US", language_label="English"
                ),
                SimpleNamespace(language="de", locale="de-DE", language_label="German"),
            ),
            qualities=("fp32",),
            sample_rate=24000,
            capabilities=frozenset({"named_voices", "lexicons"}),
            metadata={
                "voice_mode": "static",
                "private_target_payload": "hidden-target-data",
            },
        ),
    )
    backend.list_voices = lambda **kwargs: (
        SimpleNamespace(
            selector="kokoro:target-a/af_heart",
            voice="af_heart",
            languages=("en",),
            gender="female",
            locale="en-US",
            installed=True,
            metadata={
                "voice": {"language_label": "American English"},
                "private_voice_payload": "hidden-voice-data",
            },
        ),
    )

    targets = _invoke(
        monkeypatch,
        backend,
        ["targets", "--engine", "kokoro", "--language", "en"],
    )
    voices = _invoke(
        monkeypatch,
        backend,
        ["voices", "--engine", "kokoro", "--target", "target-a", "--language", "en"],
    )

    assert targets.exit_code == 0, targets.output
    assert "English/German" in targets.output
    assert "2 voices" in targets.output
    assert "fp32" in targets.output and "24 kHz" in targets.output
    assert "private_target_payload" not in targets.output
    assert voices.exit_code == 0, voices.output
    assert "af_heart" in voices.output and "[default]" in voices.output
    assert "female" in voices.output and "en-US" in voices.output
    assert "American English" in voices.output
    assert "private_voice_payload" not in voices.output


def test_reference_only_target_is_hidden_interactively_and_rejected_noninteractive(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    reference_target = {
        "id": "reference-only",
        "languages": ("en",),
        "voices": (),
        "speakers": (),
        "capabilities": frozenset({"reference_voice"}),
        "metadata": {"supports_reference_enrollment": True},
    }
    normal_target = {
        "id": "target-a",
        "languages": ("en",),
        "voices": ("voice-a",),
        "capabilities": frozenset({"named_voices"}),
    }
    backend = _Backend()
    backend.list_targets = lambda **kwargs: (reference_target, normal_target)
    source = tmp_path / "book.epub"
    request = AudiobookRequest(
        source=source,
        language="en",
        engine="engine-a",
        voice="voice-a",
    )
    preparation = SetupPreparation(
        paths=ProjectPaths.for_source(source),
        inspection=backend.inspect_source(source),
        request=request,
        origins=SetupOrigins(project=frozenset({"language", "engine", "voice"})),
        reused=True,
    )
    monkeypatch.setattr(cli_app.typer, "prompt", _setup_prompt)

    selected = cli_app._complete_interactive_setup(backend, preparation)
    output = capsys.readouterr().out

    assert selected.target == "target-a"
    assert "target-a" in output
    assert "reference-only" not in output

    source.touch()
    result = _invoke(
        monkeypatch,
        backend,
        [
            "convert",
            str(source),
            "--language",
            "en",
            "--engine",
            "engine-a",
            "--target",
            "reference-only",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "requires reference audio" in result.output
    assert not any(call[0] == "save" for call in backend.calls)


def test_catalog_selection_accepts_numeric_and_identifier_values(monkeypatch) -> None:
    choices = (
        cli_app.engine_choice_view({"id": "kokoro", "installed": True}),
        cli_app.engine_choice_view({"id": "piper", "installed": True}),
    )
    answers = iter(("2", "kokoro"))
    monkeypatch.setattr(cli_app.typer, "prompt", lambda *args, **kwargs: next(answers))

    assert cli_app._choose_catalog_value("Engines", choices) == "piper"
    assert cli_app._choose_catalog_value("Engines", choices) == "kokoro"
