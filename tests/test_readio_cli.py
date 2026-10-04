"""CLI contract tests for Readio-backed audiobook workflows."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from importlib import import_module
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from readio.api import (
    AudiobookChapter,
    AudiobookExportResult,
    AudiobookInspection,
    AudiobookProjectChapter,
    DiscoveryOptions,
    EngineCapabilities,
    EngineInfo,
    LexiconInfo,
    ModelInfo,
    PreviewResult,
    ProjectRef,
    ProjectSettings,
    ProjectStatus,
    SynthesisResolution,
    VoiceInfo,
)
from rich.console import Console
from typer.testing import CliRunner

from ttsforge.application.models import (
    BookInspectionView,
    ChapterView,
    OperationResultView,
    SetupOrigins,
    SynthesisView,
)
from ttsforge.application.models import (
    ProjectView as ApplicationProjectView,
)
from ttsforge.audiobook import ConversionPreflight, ProjectSetup
from ttsforge.chapter_selection import parse_chapter_selection
from ttsforge.options import AudiobookOptions
from ttsforge.readio_backend import (
    apply_project_settings,
    has_synthesis_setup,
    project_setting_sources,
    project_settings,
    synthesis_request,
)
from ttsforge.synthesis_setup import SetupSources
from ttsforge.ui.catalog import engine_item
from ttsforge.ui.interaction import InteractionMode

cli_module = import_module("ttsforge.cli.app")
synthesis_ui = import_module("ttsforge.ui.synthesis")


runner = CliRunner()


def _plain_output(output: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)


def _set_mode(
    monkeypatch,
    *,
    interactive: bool,
    json_mode: bool = False,
    confirm: bool | None = None,
) -> None:
    mode = InteractionMode(
        interactive=interactive,
        json=json_mode,
        live_progress=interactive,
        confirm=interactive if confirm is None else confirm,
    )
    monkeypatch.setattr(cli_module, "resolve_interaction_mode", lambda **kwargs: mode)


def _pinned_setup_args() -> list[str]:
    return [
        "--language",
        "en-us",
        "--engine",
        "kokoro",
        "--model",
        "v1.0",
        "--model-source",
        "github",
        "--quality",
        "fp32",
        "--voice",
        "af_sarah",
        "--speed",
        "1.0",
        "--spacy",
        "lg",
        "--short-sentence",
        "phrase",
        "--lexicon",
        "crane",
        "--g2p-fallback",
        "espeak",
        "--lexicon-data-policy",
        "auto",
        "--voice-level",
        "off",
        "--pause-mode",
        "auto",
        "--unit",
        "sentence",
    ]


def _inspection(source: Path) -> AudiobookInspection:
    return AudiobookInspection(
        source=source,
        metadata={"title": "A title", "authors": ["An author"]},
        chapters=tuple(
            AudiobookChapter(
                number=number,
                source_id=f"chapter-{number}",
                title=f"Chapter {number}",
                href=f"chapter-{number}.xhtml",
                source_parent_id=None,
                parent_id=None,
                level=0,
                char_count=12 * number,
            )
            for number in range(1, 4)
        ),
    )


class _FakeConverter:
    def __init__(self, source: Path, project: ProjectRef) -> None:
        self.inspection = _inspection(source)
        self.project = project
        self.options = None
        self.existing_project: ProjectRef | None = None
        self.existing_chapters = (2, 3)
        self.setup: ProjectSetup | None = None
        self.calls: list[str] = []
        self.settings = ProjectSettings()
        self.build_synthesis = None
        self.preflight_synthesis = None
        self.fail_build: Exception | None = None
        self.build_count = 0

        self.resolve_settings_flags: list[bool] = []
        self.resolution_requests: list[object] = []
        self.catalog_calls: list[tuple[str, object, DiscoveryOptions | None]] = []
        capabilities = EngineCapabilities(
            id="kokoro",
            supports_named_voices=True,
            supports_lexicons=True,
            supports_model_sources=True,
            supports_qualities=True,
            supports_voice_level_calibration=True,
        )
        self.engine_rows = (
            EngineInfo(
                id="kokoro",
                version="1.0",
                registered=True,
                installed=True,
                runnable=True,
                capabilities=capabilities,
                missing_dependency=None,
            ),
            EngineInfo(
                id="piper",
                version="2.0",
                registered=True,
                installed=True,
                runnable=True,
                capabilities=EngineCapabilities(id="piper"),
                missing_dependency=None,
            ),
        )
        self.model_rows = (
            ModelInfo(
                id="v1.0",
                source="github",
                languages=("en-us",),
                voices=("af_sarah", "am_adam", "af_bella", "af_heart"),
                default_voice="af_heart",
                qualities=("fp32", "q8"),
                g2p_backend="kokorog2p",
                lexicons=("crane",),
                frontend="kokoro",
                status="ready",
                experimental=False,
                runtime_available=True,
                redistribution_allowed=True,
                engine="kokoro",
            ),
        )
        self.voice_rows = (
            VoiceInfo(
                ref="kokoro:v1.0/af_sarah",
                id="af_sarah",
                gender="female",
                language="en",
                locale="en-us",
                language_label="American English",
                model="v1.0",
                source="github",
                default=False,
                status="ready",
                experimental=False,
                runtime_available=True,
                engine="kokoro",
            ),
            VoiceInfo(
                ref="kokoro:v1.0/am_adam",
                id="am_adam",
                gender="male",
                language="en",
                locale="en-us",
                language_label="American English",
                model="v1.0",
                source="github",
                default=False,
                status="ready",
                experimental=False,
                runtime_available=True,
                engine="kokoro",
            ),
            VoiceInfo(
                ref="kokoro:v1.0/af_bella",
                id="af_bella",
                gender="female",
                language="en",
                locale="en-us",
                language_label="American English",
                model="v1.0",
                source="github",
                default=False,
                status="ready",
                experimental=False,
                runtime_available=True,
                engine="kokoro",
            ),
            VoiceInfo(
                ref="kokoro:v1.0/af_heart",
                id="af_heart",
                gender="female",
                language="en",
                locale="en-us",
                language_label="American English",
                model="v1.0",
                source="github",
                default=True,
                status="ready",
                experimental=False,
                runtime_available=True,
                engine="kokoro",
            ),
        )
        self.lexicon_rows = (
            LexiconInfo(
                selector="crane",
                engine="kokoro",
                language="en",
                locale="en-us",
                asset_id="crane",
                data_backend="kokorog2p",
                default=True,
                installed=True,
                models=("v1.0",),
                model_support="supported",
                display_name="Crane",
                phoneme_encoding="ipa",
                data_version="1",
            ),
        )

    @staticmethod
    def normalize_engine(engine: str) -> str:
        return "kokoro" if engine == "pykokoro" else engine

    def inspect(self, source: Path) -> AudiobookInspection:
        self.calls.append("inspect")
        return self.inspection

    def inspect_book(self, source: Path) -> BookInspectionView:
        inspection = self.inspect(source)
        return BookInspectionView(
            source=inspection.source,
            metadata=inspection.metadata,
            chapters=tuple(
                ChapterView(
                    number=chapter.number,
                    title=chapter.title,
                    source_id=chapter.source_id,
                    parent_id=chapter.parent_id,
                    level=chapter.level,
                    char_count=chapter.char_count,
                )
                for chapter in inspection.chapters
            ),
        )

    def _application_project(
        self, project: ProjectRef, chapter_numbers: tuple[int, ...]
    ) -> ApplicationProjectView:
        return ApplicationProjectView(
            path=project.root,
            project_id=project.project_id,
            name=project.name,
            kind=project.kind,
            source_format=project.source_format,
            chapters=tuple(
                ChapterView(
                    number=number,
                    title=f"Chapter {number}",
                    scope_id=f"chapter-{number:04d}",
                )
                for number in chapter_numbers
            ),
        )

    def open_project(self, project: ApplicationProjectView) -> ApplicationProjectView:
        self.create_or_open_project(
            AudiobookOptions(source=self.inspection.source, project=project.path),
            inspection=self.inspection,
            existing_project=self.project,
            project_checked=True,
        )
        return self._application_project(self.project, self.setup.selected_chapters)

    def create_project(
        self,
        inspection: BookInspectionView,
        path: Path,
        chapter_numbers: tuple[int, ...],
    ) -> ApplicationProjectView:
        self.project = replace(self.project, root=path)
        options = AudiobookOptions(
            source=inspection.source,
            project=path,
            chapters=",".join(str(number) for number in chapter_numbers),
        )
        self.create_or_open_project(
            options, inspection=self.inspection, project_checked=True
        )
        return self._application_project(self.project, self.setup.selected_chapters)

    def load_setup(
        self, project: ApplicationProjectView, request: AudiobookOptions
    ) -> tuple[AudiobookOptions, SetupOrigins, bool]:
        settings = self.project_settings(project.path)
        return (
            apply_project_settings(request, settings),
            SetupOrigins(project=project_setting_sources(settings)),
            has_synthesis_setup(settings),
        )

    def save_synthesis_setup(
        self,
        project: ApplicationProjectView,
        request: AudiobookOptions,
        synthesis: SynthesisView,
    ) -> AudiobookOptions:
        resolution = SynthesisResolution(
            engine=synthesis.engine,
            language=synthesis.language,
            voice=synthesis.voice,
            model=synthesis.model,
            model_source=synthesis.model_source,
            quality=synthesis.quality,
            speed=synthesis.speed,
            unit=synthesis.unit,
            pause_mode=synthesis.pause_mode,
            voice_level=synthesis.voice_level,
            spacy=synthesis.spacy,
            short_sentence=synthesis.short_sentence,
            lexicons=synthesis.lexicons,
            g2p_fallback=synthesis.g2p_fallback,
            lexicon_data_policy=synthesis.lexicon_data_policy,
            allow_experimental=synthesis.allow_experimental,
        )
        settings = project_settings(request, resolution)
        persisted = self.save_project_settings(project.path, settings)
        self.options = apply_project_settings(request, persisted)
        return self.options

    def build(
        self, project: ApplicationProjectView, request: AudiobookOptions
    ) -> OperationResultView:
        result = self.build_and_export(project.path, request)
        return OperationResultView(
            operation="build",
            project=project,
            output=result.output_path,
            details=result.to_dict(),
        )

    def resolve_synthesis(self, project, request, *, use_saved_settings=True):  # type: ignore[no-untyped-def]
        service_project = isinstance(project, ApplicationProjectView)
        received_request = request
        if service_project:
            request = synthesis_request(request)
            project = self.project
        self.calls.append("resolve_synthesis")
        self.resolve_settings_flags.append(use_saved_settings)
        self.resolution_requests.append(received_request)
        saved = self.settings.synthesis if use_saved_settings else None

        def value(name, default):  # type: ignore[no-untyped-def]
            requested = getattr(request, name, None) if request is not None else None
            if requested is not None:
                return requested
            persisted = getattr(saved, name, None) if saved is not None else None
            return default if persisted is None else persisted

        resolution = SynthesisResolution(
            engine=value("engine", "kokoro"),
            language=value("language", "en-us"),
            voice=value("voice", "af_sarah"),
            model=value("model", "v1.0"),
            model_source=value("model_source", "github"),
            quality=value("quality", "fp32"),
            speed=value("speed", 1.0),
            unit=value("unit", "sentence"),
            pause_mode=value("pause_mode", "auto"),
            voice_level=value("voice_level", "off"),
            spacy=value("spacy", "auto"),
            short_sentence=value("short_sentence", "phrase"),
            lexicons=value("lexicons", None),
            g2p_fallback=value("g2p_fallback", "espeak"),
            lexicon_data_policy=value("lexicon_data_policy", "auto"),
            allow_experimental=value("allow_experimental", False),
        )
        if not service_project:
            return resolution
        return SynthesisView(
            engine=resolution.engine,
            language=resolution.language,
            voice=resolution.voice,
            model=resolution.model,
            speed=resolution.speed,
            unit=resolution.unit,
            pause_mode=resolution.pause_mode,
            model_source=resolution.model_source,
            quality=resolution.quality,
            spacy=resolution.spacy,
            short_sentence=resolution.short_sentence,
            lexicons=resolution.lexicons,
            g2p_fallback=resolution.g2p_fallback,
            lexicon_data_policy=resolution.lexicon_data_policy,
            voice_level=resolution.voice_level,
            allow_experimental=resolution.allow_experimental,
        )

    def project_settings(self, project):  # type: ignore[no-untyped-def]
        self.calls.append("project_settings")
        return self.settings

    def save_project_settings(self, project, settings):  # type: ignore[no-untyped-def]
        self.calls.append("save_project_settings")
        self.settings = settings
        return settings

    def engines(self):  # type: ignore[no-untyped-def]
        self.calls.append("engines")
        return self.engine_rows

    def models(self, *, language, engine, discovery):  # type: ignore[no-untyped-def]
        self.catalog_calls.append(("models", (language, engine), discovery))
        return SimpleNamespace(items=self.model_rows)

    def voices(self, *, language, engine, model, discovery):  # type: ignore[no-untyped-def]
        self.catalog_calls.append(("voices", (language, engine, model), discovery))
        return SimpleNamespace(items=self.voice_rows)

    def lexicons(self, *, language, engine, model, discovery):  # type: ignore[no-untyped-def]
        self.catalog_calls.append(("lexicons", (language, engine, model), discovery))
        return SimpleNamespace(items=self.lexicon_rows)

    def find_project(self, options):  # type: ignore[no-untyped-def]
        self.calls.append("find_project")
        if isinstance(options, Path):
            if self.existing_project is None:
                return None
            return self._application_project(
                self.existing_project, self.existing_chapters
            )
        return self.existing_project

    def create_or_open_project(
        self, options, *, inspection, existing_project=None, project_checked=False
    ):  # type: ignore[no-untyped-def]
        self.calls.append("create_or_open_project")
        self.options = options
        if existing_project is None:
            numbers = tuple(
                index + 1
                for index in parse_chapter_selection(
                    options.chapters, len(self.inspection.chapters)
                )
            )
            created = True
        else:
            numbers = self.existing_chapters
            created = False
        self.existing_project = self.project
        self.setup = ProjectSetup(
            project=self.project,
            created=created,
            chapters=tuple(
                AudiobookProjectChapter(
                    number=number,
                    scope_id=f"chapter-{number:04d}",
                    title=f"Chapter {number}",
                    level=0,
                )
                for number in numbers
            ),
        )
        return self.setup

    def preflight(self, setup, inspection, options, *, synthesis=None):  # type: ignore[no-untyped-def]
        self.calls.append("preflight")
        self.preflight_synthesis = synthesis
        self.options = options
        resolution = self.resolve_synthesis(setup.project, synthesis)
        return ConversionPreflight(
            source=options.source,
            title="A title",
            author="An author",
            project=self.project,
            project_created=setup.created,
            available_chapters=len(inspection.chapters),
            chapters=setup.chapters,
            output=options.output,
            format=options.format,
            synthesis_request=synthesis,
            synthesis=resolution,
            bitrate=options.bitrate,
            target_lufs=options.target_lufs,
            offline=options.offline,
            refresh=options.refresh,
        )

    def build_and_export(self, project, options):  # type: ignore[no-untyped-def]
        self.calls.append("build_and_export")
        self.build_synthesis = None
        self.build_count += 1
        if self.fail_build is not None:
            raise self.fail_build
        return AudiobookExportResult(
            project=self.project,
            output_path=options.output or self.project.root.with_suffix(".m4b"),
            format=options.format,
            output_sha256="digest",
            export_id="export-1",
            chapter_count=len(self.setup.chapters) if self.setup else 0,
        )

    def status(self, project: Path) -> ProjectStatus:
        return ProjectStatus(self.project, stages=(), issues=(), next_actions=())

    def preview(self, project, options, *, selection):  # type: ignore[no-untyped-def]
        return PreviewResult(
            project=self.project,
            profile_id="profile",
            plan_ids=(),
            reused=0,
            rendered=1,
            activated=False,
            sample_rate=24000,
            frames=24000,
            items=1,
        )


@pytest.mark.parametrize(
    ("selection", "expected_voice"),
    (
        ("4", "af_heart"),
        ("af_heart", "af_heart"),
        ("kokoro:v1.0/af_heart", "af_heart"),
        ("kokoro:v1.0:af_heart", "af_heart"),
    ),
)
def test_guided_voice_selection_normalizes_catalog_identity(
    tmp_path: Path, monkeypatch, selection: str, expected_voice: str
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    baseline = converter.resolve_synthesis(project, None)
    prompt_defaults: list[object] = []

    def prompt(_message: str, **kwargs: object) -> str:
        prompt_defaults.append(kwargs.get("default"))
        return selection

    monkeypatch.setattr(synthesis_ui.typer, "prompt", prompt)
    options = synthesis_ui._choose_voice(
        converter,
        AudiobookOptions(source=source, model="v1.0"),
        SetupSources(),
        baseline,
        converter.model_rows[0],
        "en-us",
        "kokoro",
        DiscoveryOptions(),
        Console(file=StringIO(), width=40, force_terminal=False, color_system=None),
    )

    assert prompt_defaults == ["af_sarah"]
    assert converter.model_rows[0].default_voice == "af_heart"
    assert options.voice == expected_voice


def test_guided_voice_selection_preserves_text_when_catalog_is_empty(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.voice_rows = ()
    baseline = converter.resolve_synthesis(project, None)
    monkeypatch.setattr(
        synthesis_ui.typer,
        "prompt",
        lambda _message, **kwargs: "custom-provider-voice",
    )
    options = synthesis_ui._choose_voice(
        converter,
        AudiobookOptions(source=source, model="v1.0"),
        SetupSources(),
        baseline,
        converter.model_rows[0],
        "en-us",
        "kokoro",
        DiscoveryOptions(),
        Console(file=StringIO(), width=40, force_terminal=False, color_system=None),
    )

    assert options.voice == "custom-provider-voice"


def test_model_catalog_does_not_use_incompatible_baseline_as_enter_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "book.epub"
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.model_rows = tuple(
        replace(
            converter.model_rows[0],
            id=f"piper-{suffix}",
            source="piper",
            engine="piper",
        )
        for suffix in ("a", "b")
    )
    baseline = converter.resolve_synthesis(project, None)
    prompts: list[tuple[str, object, bool]] = []
    answers = iter(("", "2"))

    def prompt(message: str, **kwargs: object) -> str:
        prompts.append(
            (message, kwargs.get("default"), bool(kwargs.get("show_default")))
        )
        return next(answers)

    monkeypatch.setattr(synthesis_ui.typer, "prompt", prompt)
    output = StringIO()
    options, model = synthesis_ui._choose_model(
        converter,
        AudiobookOptions(source=source),
        SetupSources(),
        baseline,
        "en-us",
        "piper",
        DiscoveryOptions(),
        Console(file=output, width=100, force_terminal=False, color_system=None),
        target_bound=True,
    )

    assert options.model == "piper-b"
    assert model is not None and model.id == "piper-b"
    assert prompts == [
        ("Voice bundle", "", False),
        ("Voice bundle", "", False),
    ]
    assert "A selection is required." in output.getvalue()


def test_voice_default_uses_compatible_model_voice_not_old_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "book.epub"
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.voice_rows = tuple(
        replace(
            voice,
            ref=f"pocket:pocket-b/{name}",
            id=name,
            model="pocket-b",
            source="pocket",
            engine="pocket",
        )
        for voice, name in zip(
            converter.voice_rows[:2], ("alba", "marius"), strict=True
        )
    )
    model_info = replace(converter.model_rows[0], default_voice="alba")
    baseline = converter.resolve_synthesis(project, None)
    defaults: list[object] = []

    def prompt(_message: str, **kwargs: object) -> str:
        defaults.append(kwargs.get("default"))
        return ""

    monkeypatch.setattr(synthesis_ui.typer, "prompt", prompt)
    options = synthesis_ui._choose_voice(
        converter,
        AudiobookOptions(source=source, engine="pocket", model="pocket-b"),
        SetupSources(),
        baseline,
        model_info,
        "en-us",
        "pocket",
        DiscoveryOptions(),
        Console(file=StringIO(), width=100, force_terminal=False, color_system=None),
    )

    assert baseline.voice == "af_sarah"
    assert defaults == ["alba"]
    assert options.voice == "alba"


@pytest.mark.parametrize("pin_engine", (False, True))
def test_piper_interactive_setup_selects_bundle_before_singleton_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin_engine: bool
) -> None:
    source = tmp_path / "book.epub"
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    piper = converter.engine_rows[1]
    converter.engine_rows = (
        converter.engine_rows[0],
        replace(
            piper,
            capabilities=EngineCapabilities(
                id="piper", voice_binding_scope="target", supports_qualities=True
            ),
        ),
    )

    piper_features = engine_item(converter.engine_rows[1]).details
    assert any("voice bundles" in feature for feature in piper_features)
    assert all("voices" not in feature for feature in piper_features)
    converter.model_rows = tuple(
        replace(
            converter.model_rows[0],
            id=f"piper-{suffix}",
            source="piper",
            languages=("en-us",),
            voices=(f"piper-{suffix}",),
            default_voice=f"piper-{suffix}",
            qualities=("int8", "fp32"),
            g2p_backend=None,
            lexicons=(),
            frontend="piper",
            engine="piper",
        )
        for suffix in ("a", "b")
    )
    converter.voice_rows = (
        replace(
            converter.voice_rows[0],
            ref="piper:piper-b",
            id="piper-b",
            model="piper-b",
            source="piper",
            engine="piper",
        ),
    )
    prompts: list[str] = []
    policy_prompts: list[str] = []

    cli_fields = {"language", "speed"}
    if pin_engine:
        cli_fields.add("engine")

    def prompt(message: str, **kwargs: object) -> str:
        prompts.append(message)
        if message == "Engine" and not pin_engine:
            return "2"
        if message == "Voice bundle":
            return "2"
        raise AssertionError(f"Unexpected input prompt: {message}")

    def choose_policy(
        message: str, default: str, choices: tuple[str, ...], console: Console
    ) -> str:
        policy_prompts.append(message)
        return default

    monkeypatch.setattr(synthesis_ui.typer, "prompt", prompt)
    monkeypatch.setattr(
        synthesis_ui,
        "_choice",
        choose_policy,
    )
    output = StringIO()
    result = synthesis_ui.configure_synthesis_interactively(
        converter=converter,
        project=project,
        options=AudiobookOptions(
            source=source,
            language="en-us",
            engine="piper" if pin_engine else None,
            speed=1.0,
        ),
        sources=SetupSources(
            cli=frozenset(cli_fields),
            project=frozenset(
                {
                    "model_source",
                    "spacy",
                    "short_sentence",
                    "lexicons",
                    "g2p_fallback",
                    "lexicon_data_policy",
                    "pause_mode",
                    "unit",
                }
            ),
        ),
        console=Console(
            file=output, width=100, force_terminal=False, color_system=None
        ),
    )

    assert result.engine == "piper"
    assert result.model == "piper-b"
    assert result.voice == "piper-b"
    assert prompts == (["Voice bundle"] if pin_engine else ["Engine", "Voice bundle"])
    assert policy_prompts == ["Quality"]
    assert "Available voice bundles for en-us / piper" in output.getvalue()
    assert "Using voice piper-b." in output.getvalue()
    assert len(converter.resolution_requests) == 1
    baseline_request = converter.resolution_requests[0]
    assert isinstance(baseline_request, AudiobookOptions)
    assert baseline_request.engine is None
    assert baseline_request.model is None
    assert baseline_request.voice is None
    assert converter.resolve_settings_flags == [False]


@pytest.mark.parametrize(
    ("speed", "pin_speed", "expected_speed"),
    ((None, False, 1.0), (1.2, True, 1.2)),
)
def test_pocket_interactive_setup_selects_bundle_then_voice_and_defaults_speed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    speed: float | None,
    pin_speed: bool,
    expected_speed: float,
) -> None:
    source = tmp_path / "book.epub"
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    pocket = converter.engine_rows[1]
    converter.engine_rows = (
        converter.engine_rows[0],
        replace(
            pocket,
            id="pocket",
            capabilities=EngineCapabilities(
                id="pocket", supports_named_voices=True, supports_qualities=True
            ),
        ),
    )
    converter.model_rows = tuple(
        replace(
            converter.model_rows[0],
            id=f"pocket-{suffix}",
            source="pocket",
            languages=("en-us",),
            voices=("alba", "marius"),
            default_voice="alba",
            qualities=("int8", "fp32"),
            g2p_backend=None,
            lexicons=(),
            frontend="pocket",
            engine="pocket",
        )
        for suffix in ("a", "b")
    )
    converter.voice_rows = tuple(
        replace(
            voice,
            ref=f"pocket:pocket-b/{name}",
            id=name,
            model="pocket-b",
            source="pocket",
            engine="pocket",
        )
        for voice, name in zip(
            converter.voice_rows[:2], ("alba", "marius"), strict=True
        )
    )
    selections: list[str] = []
    steps: list[str] = []
    workflow_steps: list[str] = []
    cli_fields = {"language"}
    if pin_speed:
        cli_fields.add("speed")

    def prompt(message: str, **kwargs: object) -> str:
        selections.append(message)
        workflow_steps.append(message)
        if message in {"Engine", "Model", "Voice"}:
            return "2"
        raise AssertionError(f"Unexpected input prompt: {message}")

    def choose_policy(
        message: str, default: str, choices: tuple[str, ...], console: Console
    ) -> str:
        steps.append(message)
        workflow_steps.append(message)
        return default

    monkeypatch.setattr(synthesis_ui.typer, "prompt", prompt)
    monkeypatch.setattr(
        synthesis_ui,
        "_choice",
        choose_policy,
    )
    output = StringIO()
    result = synthesis_ui.configure_synthesis_interactively(
        converter=converter,
        project=project,
        options=AudiobookOptions(source=source, language="en-us", speed=speed),
        sources=SetupSources(
            cli=frozenset(cli_fields),
            project=frozenset(
                {
                    "model_source",
                    "spacy",
                    "short_sentence",
                    "lexicons",
                    "g2p_fallback",
                    "lexicon_data_policy",
                    "pause_mode",
                    "unit",
                }
            ),
        ),
        console=Console(
            file=output, width=100, force_terminal=False, color_system=None
        ),
    )

    assert result.engine == "pocket"
    assert result.model == "pocket-b"
    assert result.voice == "marius"
    assert result.speed == expected_speed
    assert selections == ["Engine", "Model", "Voice"]
    assert steps == ["Quality"]
    assert workflow_steps == ["Engine", "Model", "Quality", "Voice"]
    assert "Available models for en-us / pocket" in output.getvalue()
    assert "Available voices for en-us / pocket / pocket-b" in output.getvalue()
    assert len(converter.resolution_requests) == 1
    baseline_request = converter.resolution_requests[0]
    assert isinstance(baseline_request, AudiobookOptions)
    assert baseline_request.engine is None
    assert baseline_request.model is None
    assert baseline_request.voice is None
    assert converter.resolve_settings_flags == [False]


def test_guided_catalog_lists_wrap_at_narrow_width(tmp_path: Path) -> None:
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(tmp_path / "book.epub", project)
    output = StringIO()
    console = Console(file=output, width=40, force_terminal=False, color_system=None)

    synthesis_ui._show_engines(converter.engine_rows, console)
    synthesis_ui._show_models(converter.model_rows, "en-us", "kokoro", console)
    synthesis_ui._show_voices(converter.voice_rows, "en-us", "kokoro", "v1.0", console)
    synthesis_ui._show_lexicons(converter.lexicon_rows, console)

    rendered = output.getvalue()
    assert all(
        heading in rendered
        for heading in (
            "Runnable Readio engines",
            "Available models",
            "Available voices",
            "Available lexicons",
        )
    )
    assert all(
        value in rendered
        for value in (
            "kokoro",
            "v1.0",
            "af_heart",
            "kokoro:v1.0/af_heart",
            "Crane",
            "selector: crane",
        )
    )
    assert rendered.index("af_heart") < rendered.index("ref: kokoro:v1.0/af_heart")
    assert not any(border in rendered for border in ("┏", "┓", "┃", "┡", "└"))


def test_help_exposes_only_the_audiobook_frontend_commands() -> None:
    result = runner.invoke(cli_module.app, ["--help"])
    help_text = _plain_output(result.output)

    assert result.exit_code == 0, help_text
    assert "convert" in help_text
    assert "list" in help_text
    assert "status" in help_text
    assert "phonemes" not in help_text
    assert "download" not in help_text

    assert "engines" in help_text
    assert "formats" in help_text
    assert "doctor" in help_text
    assert "config" in help_text
    assert "ssmd" in help_text
    convert_help = _plain_output(
        runner.invoke(cli_module.app, ["convert", "--help"]).output
    )
    assert "--yes" in convert_help
    assert "--non-interactive" in convert_help
    assert "--reconfigure" in convert_help
    assert "--model" in convert_help
    assert "--model-source" in convert_help
    assert "--quality" in convert_help

    assert "--spacy" in convert_help
    assert "--lexicon" in convert_help
    assert "--g2p-fallback" in convert_help
    assert "--pause-mode" in convert_help
    assert "--unit" in convert_help


def test_list_and_info_use_the_public_inspection_result(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    listed = runner.invoke(cli_module.app, ["list", str(source)])
    described = runner.invoke(cli_module.app, ["info", str(source), "--json"])

    assert listed.exit_code == 0, listed.output
    assert "Chapter 1" in listed.output
    assert described.exit_code == 0, described.output
    assert json.loads(described.output)["metadata"]["title"] == "A title"


def test_convert_initializes_readio_project_and_keeps_json_stdout_clean(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.ssmdbook", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=False, json_mode=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--chapters",
            "1",
            "--model",
            "kokoro-v1",
            "--model-source",
            "github",
            "--quality",
            "fp32",
            "--lexicon",
            "crane",
            "--g2p-fallback",
            "goruut",
            "--lexicon-data-policy",
            "installed-only",
            "--spacy",
            "lg",
            "--short-sentence",
            "randomized-phrase",
            "--allow-experimental",
            "--voice-level",
            "calibrated",
            "--pause-mode",
            "manual",
            "--unit",
            "paragraph",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["project"] == str(project.root)
    assert payload["created"] is True
    assert payload["settings_source"] == "new"
    assert payload["settings_saved"] is True
    assert payload["selected_chapters"] == [1]
    assert payload["format"] == "m4b"
    assert payload["output"] == str(project.root.with_suffix(".m4b"))
    assert payload["result"]["chapter_count"] == 1
    assert payload["synthesis"]["model"] == "kokoro-v1"
    assert payload["synthesis"]["model_source"] == "github"
    assert payload["synthesis"]["quality"] == "fp32"
    assert payload["synthesis"]["lexicons"] == ["crane"]
    assert payload["synthesis"]["g2p_fallback"] == "goruut"
    assert payload["synthesis"]["lexicon_data_policy"] == "installed-only"
    assert payload["synthesis"]["spacy"] == "lg"
    assert payload["synthesis"]["short_sentence"] == "randomized-phrase"
    assert payload["synthesis"]["allow_experimental"] is True
    assert payload["synthesis"]["voice_level"] == "calibrated"
    assert payload["synthesis"]["pause_mode"] == "manual"
    assert payload["synthesis"]["unit"] == "paragraph"
    assert converter.options.chapters == "1"
    assert converter.build_synthesis is converter.preflight_synthesis
    assert converter.calls == [
        "inspect",
        "find_project",
        "create_or_open_project",
        "project_settings",
        "resolve_synthesis",
        "save_project_settings",
        "build_and_export",
    ]
    assert result.stderr == ""


def test_interactive_new_project_prompts_retries_and_preflights_before_build(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    answers = [
        "typo",
        "2-3",
        "",
        "1",
        "",
        "wrong-voice",
        "kokoro:v1.0/af_sarah",
        "",
        "lg",
        "",
        "1",
        "",
        "",
        "",
        "tts",
        "paragraph",
        "y",
    ]
    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--offline",
            "--refresh",
            "--model-source",
            "github",
        ],
        input="\n".join(answers) + "\n",
    )

    assert result.exit_code == 0, result.output
    assert "3 chapters detected" in result.output
    assert "Invalid chapter number: typo" in result.output
    assert "Using model v1.0." in result.output
    assert "Unknown selection 'wrong-voice'" in result.output
    assert "Runnable Readio engines" in result.output
    assert result.output.index("Runnable Readio engines") < result.output.index(
        "Engine [kokoro]"
    )
    assert result.output.count("Chapters to include") == 2
    assert "Create this audiobook?" in result.output
    assert "2-3" in result.output
    assert result.output.index(
        "Available voices for en-us / kokoro"
    ) < result.output.index("Voice [af_sarah]")
    assert "v1.0" in result.output
    assert "Short sentences" in result.output
    assert "Lexicons" in result.output
    assert "G2P fallback" in result.output
    assert "Lexicon data" in result.output
    assert "Voice level" in result.output
    assert "Synthesis unit" in result.output
    assert converter.options.chapters == "2-3"
    assert converter.options.language == "en-us"
    assert converter.options.model == "v1.0"
    assert converter.options.voice == "af_sarah"
    assert converter.options.spacy == "lg"
    assert converter.options.short_sentence == "phrase"
    assert converter.options.lexicons == ("crane",)
    assert converter.options.pause_mode == "tts"
    assert converter.options.unit == "paragraph"
    assert converter.catalog_calls[0][1] == ("en-us", "kokoro")
    assert converter.catalog_calls[1][1] == ("en-us", "kokoro", "v1.0")
    assert converter.catalog_calls[2][1] == ("en-us", "kokoro", "v1.0")
    assert all(call[2].offline and call[2].refresh for call in converter.catalog_calls)
    assert all(call[2].preference == "github" for call in converter.catalog_calls)
    assert "resolve_synthesis" in converter.calls
    assert converter.calls.index("save_project_settings") < converter.calls.index(
        "build_and_export"
    )
    assert "Audiobook Setup" in result.output
    assert converter.build_synthesis is converter.preflight_synthesis
    assert converter.resolve_settings_flags == [False, False]
    resolution_positions = [
        index
        for index, call in enumerate(converter.calls)
        if call == "resolve_synthesis"
    ]
    save_position = converter.calls.index("save_project_settings")
    assert len(resolution_positions) == 2
    assert resolution_positions[-1] < save_position
    assert "Model [" not in result.output
    assert "Using model v1.0." in result.output


def test_failed_final_resolution_does_not_persist_invalid_explicit_speed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    original_resolve = converter.resolve_synthesis
    observed: list[tuple[str | None, float | None, bool]] = []

    def reject_pocket_speed(project_ref, request, *, use_saved_settings=True):  # type: ignore[no-untyped-def]
        if not use_saved_settings and request.engine == "pocket":
            observed.append((request.engine, request.speed, use_saved_settings))
            raise ValueError("Pocket does not support speed 1.2")
        return original_resolve(
            project_ref, request, use_saved_settings=use_saved_settings
        )

    converter.resolve_synthesis = reject_pocket_speed  # type: ignore[method-assign]
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )
    _set_mode(monkeypatch, interactive=False)

    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--non-interactive",
            "--engine",
            "pocket",
            "--speed",
            "1.2",
        ],
    )

    assert result.exit_code == 1
    assert "Pocket does not support speed 1.2" in result.output
    assert observed == [("pocket", 1.2, False)]
    assert converter.settings.synthesis is None
    assert "save_project_settings" not in converter.calls
    assert "build_and_export" not in converter.calls


def test_interactive_explicit_chapters_skip_chapter_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1", *_pinned_setup_args()],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" not in result.output
    assert "Create this audiobook?" in result.output
    assert converter.options.chapters == "1"


def test_yes_keeps_chapter_prompt_but_skips_final_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True, confirm=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    pinned = _pinned_setup_args()
    pinned.remove("--language")
    pinned.remove("en-us")
    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--yes", *pinned],
        input="2\nen-gb\n",
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" in result.output
    assert "Create this audiobook?" not in result.output
    assert converter.options.chapters == "2"
    assert "Language [en-us]" in result.output
    assert converter.options.language == "en-gb"
    assert "resolve_synthesis" in converter.calls


def test_capability_gates_skip_irrelevant_prompts_but_keep_explicit_pins(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    _set_mode(monkeypatch, interactive=True, confirm=False)

    args = _pinned_setup_args()
    args[args.index("kokoro")] = "piper"
    for option in (
        "--lexicon",
        "--g2p-fallback",
        "--lexicon-data-policy",
        "--voice-level",
    ):
        index = args.index(option)
        del args[index : index + 2]
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )
    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--yes", "--chapters", "all", *args],
        input="goruut\ninstalled-only\n",
    )
    assert result.exit_code == 0, result.output
    assert "Lexicons [" not in result.output
    assert "Voice level [" not in result.output
    assert "G2P fallback (none/espeak/goruut) [espeak]" in result.output
    assert "Lexicon data (auto/installed-only) [auto]" in result.output
    assert [call[0] for call in converter.catalog_calls] == ["models"]

    args.extend(("--voice-level", "calibrated"))
    pinned_converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: pinned_converter
    )
    pinned_result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--yes", "--chapters", "all", *args],
        input="goruut\ninstalled-only\n",
    )
    assert pinned_result.exit_code == 0, pinned_result.output
    assert "Voice level [" not in pinned_result.output
    assert pinned_converter.options.voice_level == "calibrated"
    assert pinned_converter.settings.synthesis is not None
    assert pinned_converter.settings.synthesis.voice_level == "calibrated"


def test_non_interactive_uses_all_without_prompting(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app, ["convert", str(source), "--non-interactive"]
    )

    assert result.exit_code == 0, result.output
    assert "Chapters to include" not in result.output
    assert "Create this audiobook?" not in result.output
    assert converter.options.chapters == "all"
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (1, 2, 3)
    assert converter.calls.count("resolve_synthesis") == 1
    assert "save_project_settings" in converter.calls
    assert converter.catalog_calls == []


def test_existing_project_shows_persisted_scope_without_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.existing_project = project
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app, ["convert", str(source), *_pinned_setup_args()], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "2-3" in result.output
    assert "Chapters to include" not in result.output
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (2, 3)
    assert "save_project_settings" in converter.calls
    assert converter.settings.synthesis is not None


def test_existing_project_rejects_conflicting_chapters(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.existing_project = project
    _set_mode(monkeypatch, interactive=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "1"],
    )

    assert result.exit_code == 1
    assert "Existing project uses chapters 2-3" in result.output
    assert "--fresh" in result.output
    assert "preflight" not in converter.calls
    assert "build_and_export" not in converter.calls


def test_declining_confirmation_does_not_start_build(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=True)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--chapters",
            "1",
            *_pinned_setup_args(),
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert "Cancelled before synthesis" in result.output
    assert "build_and_export" not in converter.calls
    assert "save_project_settings" in converter.calls
    assert converter.settings.synthesis is not None


def test_status_and_preview_are_project_service_workflows(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    status = runner.invoke(cli_module.app, ["status", str(project.root), "--json"])
    preview = runner.invoke(cli_module.app, ["preview", str(source), "--json"])

    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["project"]["root"] == str(project.root)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["result"]["items"] == 1


def test_convert_maps_new_synthesis_cli_flags_to_readio_request(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    _set_mode(monkeypatch, interactive=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    result = runner.invoke(
        cli_module.app,
        [
            "convert",
            str(source),
            "--non-interactive",
            "--lexicon",
            "crane",
            "--lexicon",
            "custom",
            "--g2p-fallback",
            "goruut",
            "--lexicon-data-policy",
            "installed-only",
            "--spacy",
            "lg",
            "--short-sentence",
            "randomized-phrase",
            "--allow-experimental",
            "--voice-level",
            "calibrated",
            "--pause-mode",
            "manual",
            "--synthesis-unit",
            "paragraph",
        ],
    )

    assert result.exit_code == 0, result.output
    assert converter.options is not None
    assert converter.options.lexicons == ("crane", "custom")
    assert converter.options.spacy == "lg"
    assert converter.options.short_sentence == "randomized-phrase"
    assert converter.settings.synthesis is not None
    assert converter.settings.synthesis.lexicons == ("crane", "custom")
    assert converter.settings.synthesis.g2p_fallback == "goruut"
    assert converter.settings.synthesis.lexicon_data_policy == "installed-only"
    assert converter.settings.synthesis.allow_experimental is True
    assert converter.settings.synthesis.voice_level == "calibrated"
    assert converter.settings.synthesis.pause_mode == "manual"
    assert converter.settings.synthesis.unit == "paragraph"


def test_convert_rejects_conflicting_lexicon_modes_before_project_work(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )
    conflicts = (
        ("--lexicon", "crane", "--no-lexicons"),
        ("--lexicon", "crane", "--auto-lexicons"),
        ("--no-lexicons", "--auto-lexicons"),
    )
    for flags in conflicts:
        result = runner.invoke(cli_module.app, ["convert", str(source), *flags])
        assert result.exit_code != 0
        assert "Invalid value:" in result.output
    assert converter.calls == []


def test_convert_no_lexicons_and_auto_lexicons_flags_map_to_request(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    _set_mode(monkeypatch, interactive=False)

    for flag, clear, automatic in (
        ("--no-lexicons", True, False),
        ("--auto-lexicons", False, True),
    ):
        converter = _FakeConverter(source, project)
        monkeypatch.setattr(
            cli_module,
            "_converter",
            lambda json_mode, progress=None, *, converter=converter: converter,
        )
        result = runner.invoke(
            cli_module.app,
            ["convert", str(source), "--non-interactive", flag],
        )
        assert result.exit_code == 0, result.output
        assert converter.settings.synthesis is not None
        assert converter.settings.synthesis.clear_lexicons is clear
        assert converter.settings.synthesis.auto_lexicons is automatic
        assert (
            converter.settings.synthesis.lexicons is None
            if automatic
            else converter.settings.synthesis.lexicons == ()
        )


def test_failed_synthesis_saves_setup_for_prompt_free_retry(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    converter.fail_build = ValueError("simulated synthesis failure")
    _set_mode(monkeypatch, interactive=True, confirm=False)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )

    failed = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--chapters", "2-3", "--yes"],
        input="\n" * 14,
    )

    assert failed.exit_code == 1, failed.output
    assert "simulated synthesis failure" in failed.output
    assert converter.settings.synthesis is not None
    assert converter.build_count == 1
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (2, 3)
    assert converter.calls.index("save_project_settings") < converter.calls.index(
        "build_and_export"
    )
    assert "Audiobook Setup" in failed.output

    converter.fail_build = None
    call_start = len(converter.calls)
    retried = runner.invoke(cli_module.app, ["convert", str(source), "--yes"])
    retry_calls = converter.calls[call_start:]

    assert retried.exit_code == 0, retried.output
    assert "Using saved audiobook setup" in retried.output
    assert "Language [" not in retried.output
    assert "Engine [" not in retried.output
    assert "Model [" not in retried.output
    assert "Voice (" not in retried.output
    assert converter.setup is not None
    assert converter.setup.selected_chapters == (2, 3)
    assert retry_calls.index("save_project_settings") < retry_calls.index(
        "build_and_export"
    )
    assert converter.build_count == 2


def test_saved_setup_accepts_one_cli_pin_and_reconfigure_uses_it_as_default(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )
    _set_mode(monkeypatch, interactive=False)

    initial = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--non-interactive", "--voice", "af_sarah"],
    )
    assert initial.exit_code == 0, initial.output
    assert converter.settings.synthesis is not None
    original_language = converter.settings.synthesis.language

    _set_mode(monkeypatch, interactive=True, confirm=False)
    pinned = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--voice", "am_adam", "--yes"],
    )
    assert pinned.exit_code == 0, pinned.output
    assert "Updating saved audiobook setup" in pinned.output
    assert "Language [" not in pinned.output
    assert "Engine [" not in pinned.output
    assert "Model [" not in pinned.output
    assert converter.settings.synthesis is not None
    assert converter.settings.synthesis.voice == "am_adam"
    assert converter.settings.synthesis.language == original_language

    reconfigured = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--reconfigure", "--yes"],
        input="\n" * 14,
    )
    assert reconfigured.exit_code == 0, reconfigured.output
    assert "Updating saved audiobook setup" in reconfigured.output
    assert "Language [" in reconfigured.output
    assert "Engine [" in reconfigured.output
    assert "Using model v1.0." in reconfigured.output
    assert "Voice [am_adam]" in reconfigured.output
    assert "am_adam" in reconfigured.output
    assert converter.settings.synthesis is not None
    assert converter.settings.synthesis.voice == "am_adam"


def test_non_interactive_resume_uses_saved_project_without_prompts(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "book.epub"
    source.touch()
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
    converter = _FakeConverter(source, project)
    monkeypatch.setattr(
        cli_module, "_converter", lambda json_mode, progress=None: converter
    )
    _set_mode(monkeypatch, interactive=False)

    first = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--non-interactive"],
    )
    assert first.exit_code == 0, first.output
    call_start = len(converter.calls)

    resumed = runner.invoke(
        cli_module.app,
        ["convert", str(source), "--non-interactive"],
    )
    resume_calls = converter.calls[call_start:]

    assert resumed.exit_code == 0, resumed.output
    assert "Using saved audiobook setup" in resumed.output
    assert "Language [" not in resumed.output
    assert "Engine [" not in resumed.output
    assert "Model [" not in resumed.output
    assert "create_or_open_project" in resume_calls
    assert resume_calls.index("save_project_settings") < resume_calls.index(
        "build_and_export"
    )
