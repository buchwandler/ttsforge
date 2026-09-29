"""CLI contract tests for Readio-backed audiobook workflows."""

from __future__ import annotations

import json
import re
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

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
from typer.testing import CliRunner

from ttsforge.audiobook import ConversionPreflight, ProjectSetup
from ttsforge.chapter_selection import parse_chapter_selection
from ttsforge.ui.interaction import InteractionMode

cli_module = import_module("ttsforge.cli.app")


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
        "pykokoro",
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
                parent_id=None,
                level=0,
                char_count=12 * number,
                markdown=f"# Chapter {number}",
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

        self.catalog_calls: list[tuple[str, object, DiscoveryOptions | None]] = []
        capabilities = EngineCapabilities(
            id="pykokoro",
            supports_named_voices=True,
            supports_lexicons=True,
            supports_model_sources=True,
            supports_qualities=True,
            supports_voice_level_calibration=True,
        )
        self.engine_rows = (
            EngineInfo(
                id="pykokoro",
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
                voices=("af_sarah", "am_adam"),
                default_voice="af_sarah",
                qualities=("fp32", "q8"),
                g2p_backend="kokorog2p",
                lexicons=("crane",),
                frontend="kokoro",
                status="ready",
                experimental=False,
                runtime_available=True,
                redistribution_allowed=True,
                backend="pykokoro",
            ),
        )
        self.voice_rows = (
            VoiceInfo(
                selector="af_sarah",
                id="af_sarah",
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
                engine="pykokoro",
            ),
            VoiceInfo(
                selector="am_adam",
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
                engine="pykokoro",
            ),
        )
        self.lexicon_rows = (
            LexiconInfo(
                selector="crane",
                engine="pykokoro",
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

    def inspect(self, source: Path) -> AudiobookInspection:
        self.calls.append("inspect")
        return self.inspection

    def resolve_synthesis(self, project, request):  # type: ignore[no-untyped-def]
        self.calls.append("resolve_synthesis")
        saved = self.settings.synthesis

        def value(name, default):  # type: ignore[no-untyped-def]
            requested = getattr(request, name, None) if request is not None else None
            if requested is not None:
                return requested
            persisted = getattr(saved, name, None) if saved is not None else None
            return default if persisted is None else persisted

        return SynthesisResolution(
            engine=value("engine", "pykokoro"),
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
    project = ProjectRef(tmp_path / "book.readio", "id", "book", "audiobook", "epub")
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
        "preflight",
        "resolve_synthesis",
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
        "wrong-model",
        "1",
        "",
        "wrong-voice",
        "1",
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
    assert "Unknown selection 'wrong-model'" in result.output
    assert "Unknown selection 'wrong-voice'" in result.output
    assert "Runnable Readio engines" in result.output
    assert result.output.index("Runnable Readio engines") < result.output.index(
        "Engine [pykokoro]"
    )
    assert result.output.count("Chapters to include") == 2
    assert "Create this audiobook?" in result.output
    assert "2-3" in result.output
    assert "Model" in result.output
    assert "Available models for en-us / pykokoro" in result.output
    assert result.output.index("Available models") < result.output.index("Model [v1.0]")
    assert result.output.index(
        "Available voices for en-us / pykokoro"
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
    assert converter.catalog_calls[0][1] == ("en-us", "pykokoro")
    assert converter.catalog_calls[1][1] == ("en-us", "pykokoro", "v1.0")
    assert converter.catalog_calls[2][1] == ("en-us", "pykokoro", "v1.0")
    assert all(call[2].offline and call[2].refresh for call in converter.catalog_calls)
    assert all(call[2].preference == "github" for call in converter.catalog_calls)
    assert "resolve_synthesis" in converter.calls
    assert converter.calls.index("preflight") < converter.calls.index(
        "build_and_export"
    )
    assert converter.build_synthesis is converter.preflight_synthesis


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
    args[args.index("pykokoro")] = "piper"
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
    assert converter.calls.count("resolve_synthesis") == 2
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
    assert (
        converter.calls.index("save_project_settings")
        < converter.calls.index("preflight")
        < converter.calls.index("build_and_export")
    )

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
    assert (
        retry_calls.index("save_project_settings")
        < retry_calls.index("preflight")
        < retry_calls.index("build_and_export")
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
    assert "Model [" in reconfigured.output
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
