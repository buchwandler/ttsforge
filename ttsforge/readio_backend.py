"""The single, public-API integration seam between TTSForge and Readio."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast

from readio.api import (
    AUDIOBOOK_EXPORT_FORMAT,
    G2P_FALLBACKS,
    LEXICON_DATA_POLICIES,
    SHORT_SENTENCE_POLICIES,
    SPACY_POLICIES,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_AUDIOBOOK_FORMATS,
    VOICE_LEVEL_MODES,
    AudiobookExportOptions,
    AudiobookExportResult,
    AudiobookInspection,
    AudiobookProjectChapter,
    AudioFormat,
    CatalogListing,
    CompositionOptions,
    DiscoveryOptions,
    EngineInfo,
    ExportOptions,
    LexiconInfo,
    LexiconQuery,
    ModelInfo,
    ModelQuery,
    PreviewRequest,
    PreviewResult,
    ProjectBuildRequest,
    ProjectBuildResult,
    ProjectFormatError,
    ProjectPlanResult,
    ProjectRef,
    ProjectSettings,
    ProjectStatus,
    ProjectSynthesisSettings,
    Readio,
    ReadioError,
    ReadioEvent,
    SynthesisRequest,
    SynthesisResolution,
    VoiceInfo,
    VoiceQuery,
)

from .application.errors import LegacyWorkspaceError, ProjectMigrationRequiredError
from .application.events import ApplicationEvent
from .application.models import (
    AudiobookRequest as AudiobookOptions,
)
from .application.models import (
    BookInspectionView,
    CatalogItemView,
    ChapterView,
    DiscoveryRequest,
    OperationResultView,
    PreviewView,
    ProjectPlanView,
    ProjectStatusView,
    ProjectView,
    SetupOrigins,
    SynthesisView,
)

__all__ = [
    "G2P_FALLBACKS",
    "LEXICON_DATA_POLICIES",
    "SHORT_SENTENCE_POLICIES",
    "SPACY_POLICIES",
    "SUPPORTED_AUDIOBOOK_FORMATS",
    "SUPPORTED_AUDIO_FORMATS",
    "VOICE_LEVEL_MODES",
    "ReadioBackend",
    "ReadioError",
    "create_readio",
]

BuildTarget = Literal["composition", "export"]


def translate_readio_event(event: ReadioEvent) -> ApplicationEvent:
    """Translate one public Readio event into the application event contract."""
    return ApplicationEvent(
        kind=event.kind,
        operation=event.operation,
        stage=event.stage,
        progress_kind=event.progress_kind,
        message=event.message,
        completed=event.completed,
        total=event.total,
        sample_count=event.sample_count,
        sample_rate=event.sample_rate,
        audio_seconds=event.audio_seconds,
        total_audio_seconds=event.total_audio_seconds,
        scope_id=event.scope_id,
        unit_id=event.unit_id,
        segment_id=event.segment_id,
        details=dict(event.details),
    )


def create_readio(
    on_event: Callable[[ApplicationEvent], None] | None = None,
) -> Readio:
    """Construct Readio and adapt its events to the application contract."""
    if on_event is None:
        return Readio()
    return Readio(on_event=lambda event: on_event(translate_readio_event(event)))


def normalize_engine(app: Readio, engine: str) -> str:
    """Normalize an engine alias through Readio's public catalog API."""
    return app.catalog.normalize_engine(engine)


def is_readio_project_migration_required(exc: ProjectFormatError) -> bool:
    """Identify Readio's public v0.3 project migration error message."""
    return "readio project migrate" in str(exc)


def synthesis_request(options: AudiobookOptions) -> SynthesisRequest:
    """Translate the small audiobook UX model to Readio synthesis options."""
    return SynthesisRequest(
        language=options.language,
        model=options.model,
        model_source=options.model_source,
        quality=options.quality,
        voice=options.voice,
        lexicons=options.lexicons,
        clear_lexicons=options.clear_lexicons,
        auto_lexicons=options.auto_lexicons,
        spacy=options.spacy,
        short_sentence=options.short_sentence,
        g2p_fallback=options.g2p_fallback,
        lexicon_data_policy=options.lexicon_data_policy,
        allow_experimental=options.allow_experimental,
        speed=options.speed,
        voice_level=options.voice_level,
        pause_mode=options.pause_mode,
        unit=options.unit,
        offline=options.offline,
        refresh=options.refresh,
        engine=options.engine,
    )


def project_settings(
    options: AudiobookOptions,
    resolution: SynthesisResolution,
) -> ProjectSettings:
    """Materialize frontend choices as durable Readio project settings."""
    lexicons: tuple[str, ...] | None
    clear_lexicons: bool
    auto_lexicons: bool
    if options.auto_lexicons:
        lexicons = None
        clear_lexicons = False
        auto_lexicons = True
    elif options.clear_lexicons:
        lexicons = ()
        clear_lexicons = True
        auto_lexicons = False
    elif options.lexicons is not None:
        lexicons = options.lexicons
        clear_lexicons = False
        auto_lexicons = False
    elif resolution.lexicons is not None:
        lexicons = resolution.lexicons
        clear_lexicons = False
        auto_lexicons = False
    else:
        lexicons = ()
        clear_lexicons = True
        auto_lexicons = False

    synthesis = ProjectSynthesisSettings(
        language=resolution.language,
        engine=resolution.engine,
        model=resolution.model,
        model_source=resolution.model_source,
        quality=resolution.quality,
        voice=resolution.voice,
        speed=resolution.speed,
        spacy=resolution.spacy,
        short_sentence=resolution.short_sentence,
        lexicons=lexicons,
        clear_lexicons=clear_lexicons,
        auto_lexicons=auto_lexicons,
        g2p_fallback=resolution.g2p_fallback,
        lexicon_data_policy=resolution.lexicon_data_policy,
        allow_experimental=resolution.allow_experimental,
        voice_level=resolution.voice_level,
        pause_mode=resolution.pause_mode,
        unit=resolution.unit,
        offline=options.offline,
    )
    if options.format.lower() == AUDIOBOOK_EXPORT_FORMAT:
        return ProjectSettings(
            synthesis=synthesis,
            composition=composition_options(options),
            audiobook_export=AudiobookExportOptions(
                format=AUDIOBOOK_EXPORT_FORMAT,
                output=options.output,
                title=options.title,
                author=options.author,
                cover=options.cover,
                bitrate=options.bitrate,
                force=False,
            ),
        )
    return ProjectSettings(
        synthesis=synthesis,
        composition=composition_options(options),
        export=ExportOptions(
            format=cast(AudioFormat, options.format.lower()),
            output=options.output,
            bitrate=options.bitrate,
            force=False,
        ),
    )


def apply_project_settings(
    options: AudiobookOptions,
    settings: ProjectSettings,
) -> AudiobookOptions:
    """Apply durable Readio settings without changing invocation-only flags."""
    updates: dict[str, Any] = {}
    synthesis = settings.synthesis
    if synthesis is not None:
        for name in (
            "language",
            "engine",
            "model",
            "model_source",
            "quality",
            "voice",
            "speed",
            "spacy",
            "short_sentence",
            "g2p_fallback",
            "lexicon_data_policy",
            "voice_level",
            "pause_mode",
            "unit",
            "offline",
            "allow_experimental",
        ):
            value = getattr(synthesis, name)
            if value is not None:
                updates[name] = value
        if synthesis.auto_lexicons is True:
            updates.update(lexicons=None, clear_lexicons=False, auto_lexicons=True)
        elif synthesis.clear_lexicons is True:
            updates.update(lexicons=(), clear_lexicons=True, auto_lexicons=False)
        elif synthesis.lexicons is not None:
            updates.update(
                lexicons=synthesis.lexicons,
                clear_lexicons=False,
                auto_lexicons=False,
            )
    if settings.composition is not None:
        updates["target_lufs"] = settings.composition.target_lufs
    if settings.audiobook_export is not None:
        export = settings.audiobook_export
        updates.update(
            format=export.format,
            output=export.output,
            title=export.title,
            author=export.author,
            cover=export.cover,
            bitrate=export.bitrate,
        )
    elif settings.export is not None:
        export = settings.export
        updates.update(
            format=export.format,
            output=export.output,
            bitrate=export.bitrate,
        )
    return replace(options, **updates)


SYNTHESIS_SETUP_FIELDS = frozenset(
    {
        "language",
        "engine",
        "model",
        "model_source",
        "quality",
        "voice",
        "speed",
        "spacy",
        "short_sentence",
        "lexicons",
        "g2p_fallback",
        "lexicon_data_policy",
        "allow_experimental",
        "voice_level",
        "pause_mode",
        "unit",
        "offline",
    }
)


def has_synthesis_setup(settings: ProjectSettings) -> bool:
    """Whether saved settings contain a resolved, resumable synthesis profile."""
    synthesis = settings.synthesis
    if synthesis is None:
        return False
    return all(
        getattr(synthesis, field) is not None
        for field in (
            "language",
            "engine",
            "model",
            "voice",
            "speed",
            "unit",
            "pause_mode",
        )
    )


def project_setting_sources(settings: ProjectSettings) -> frozenset[str]:
    """Return frontend field names represented by public Readio settings."""
    fields: set[str] = set()
    synthesis = settings.synthesis
    if synthesis is not None:
        if has_synthesis_setup(settings):
            fields.update(SYNTHESIS_SETUP_FIELDS)
        else:
            for name in SYNTHESIS_SETUP_FIELDS - {"lexicons"}:
                if getattr(synthesis, name) is not None:
                    fields.add(name)
            if (
                synthesis.lexicons is not None
                or synthesis.clear_lexicons is not None
                or synthesis.auto_lexicons is not None
            ):
                fields.add("lexicons")
    if (
        settings.composition is not None
        and settings.composition.target_lufs is not None
    ):
        fields.add("target_lufs")
    if settings.audiobook_export is not None:
        fields.update({"format", "output", "bitrate", "title", "author", "cover"})
    elif settings.export is not None:
        fields.update({"format", "output", "bitrate"})
    return frozenset(fields)


def composition_options(options: AudiobookOptions) -> CompositionOptions:
    """Map composition preferences without implementing audio processing."""
    return CompositionOptions(target_lufs=options.target_lufs)


def generic_export_options(options: AudiobookOptions) -> ExportOptions:
    """Create Readio's generic audio export request."""
    if options.format == AUDIOBOOK_EXPORT_FORMAT:
        raise ValueError("M4B uses audiobook_export_options(), not generic export.")
    return ExportOptions(
        format=cast(AudioFormat, options.format),
        output=options.output,
        bitrate=options.bitrate,
        force=options.force,
    )


def audiobook_export_options(options: AudiobookOptions) -> AudiobookExportOptions:
    """Create Readio's distinct M4B/audiobook export request."""
    return AudiobookExportOptions(
        format=AUDIOBOOK_EXPORT_FORMAT,
        output=options.output,
        title=options.title,
        author=options.author,
        cover=options.cover,
        bitrate=options.bitrate,
        force=options.force,
    )


def project_build_request(
    options: AudiobookOptions,
    *,
    target: BuildTarget,
    synthesis: SynthesisRequest | None = None,
) -> ProjectBuildRequest:
    """Build the public project request for composition or generic export."""
    resolved_synthesis = synthesis or synthesis_request(options)
    if target == "composition":
        return ProjectBuildRequest(
            target=target,
            selection="all",
            synthesis=resolved_synthesis,
            composition=composition_options(options),
        )
    return ProjectBuildRequest(
        target=target,
        selection="all",
        synthesis=resolved_synthesis,
        composition=composition_options(options),
        export=generic_export_options(options),
    )


class ReadioBackend:
    """Translate frontend-neutral operations to the public Readio API."""

    def __init__(self, app: Readio) -> None:
        self._app = app

    @staticmethod
    def _project_view(
        project: ProjectRef, chapters: tuple[ChapterView, ...] = ()
    ) -> ProjectView:
        return ProjectView(
            path=project.root,
            project_id=project.project_id,
            name=project.name,
            kind=project.kind,
            source_format=project.source_format,
            chapters=chapters,
        )

    @staticmethod
    def _chapter_views(
        chapters: tuple[AudiobookProjectChapter, ...],
    ) -> tuple[ChapterView, ...]:
        return tuple(
            ChapterView(
                number=chapter.number,
                title=chapter.title,
                scope_id=chapter.scope_id,
            )
            for chapter in chapters
        )

    def inspect_book(self, source: Path) -> BookInspectionView:
        inspection = self._app.audiobooks.inspect(source)
        chapters = tuple(
            ChapterView(
                number=chapter.number,
                title=chapter.title,
                source_id=chapter.source_id,
                parent_id=chapter.parent_id,
                level=chapter.level,
                char_count=chapter.char_count,
            )
            for chapter in inspection.chapters
        )
        return BookInspectionView(
            source=inspection.source,
            metadata=dict(inspection.metadata),
            chapters=chapters,
        )

    def find_project(self, path: Path) -> ProjectView | None:
        try:
            project = self._app.projects.find(path)
        except ProjectFormatError as exc:
            if is_readio_project_migration_required(exc):
                raise ProjectMigrationRequiredError(
                    "This Readio project uses the v0.3 schema and must be migrated "
                    "before TTSForge can open it.\nRun:\n"
                    f'    readio project migrate "{path}"\n'
                    "TTSForge will not migrate or overwrite it automatically."
                ) from exc
            raise LegacyWorkspaceError(
                "This directory is not a Readio project and cannot resume a legacy "
                "TTSForge workspace. Start a separate project with --fresh."
            ) from exc
        if project is None and path.exists():
            raise LegacyWorkspaceError(
                f"The existing directory is not a Readio project: {path}. "
                "Legacy TTSForge workspaces cannot be resumed; use --fresh "
                "to create a separate Readio project."
            )
        return self._project_view(project) if project is not None else None

    def open_project(self, project: ProjectView) -> ProjectView:
        opened = self._app.projects.open(project.path)
        description = self._app.audiobooks.describe_project(opened)
        return self._project_view(opened, self._chapter_views(description.chapters))

    def create_project(
        self,
        inspection: BookInspectionView,
        path: Path,
        chapter_numbers: tuple[int, ...],
    ) -> ProjectView:
        chapter_selection = ",".join(str(number) for number in chapter_numbers)
        created = self._app.audiobooks.create_project_result(
            inspection.source,
            chapters=chapter_selection,
            output=path,
        )
        return self._project_view(
            created.project, self._chapter_views(created.chapters)
        )

    def resolve_synthesis(
        self,
        project: ProjectView,
        request: AudiobookOptions,
        *,
        use_saved_settings: bool,
    ) -> SynthesisView:
        request = self._canonical_request(request)
        resolved = self._app.projects.resolve_synthesis(
            project.path,
            synthesis_request(request),
            use_saved_settings=use_saved_settings,
        )
        return SynthesisView(
            engine=resolved.engine,
            language=resolved.language,
            voice=resolved.voice,
            model=resolved.model,
            model_source=resolved.model_source,
            quality=resolved.quality,
            speed=resolved.speed,
            unit=resolved.unit,
            pause_mode=resolved.pause_mode,
            spacy=resolved.spacy,
            short_sentence=resolved.short_sentence,
            lexicons=resolved.lexicons,
            g2p_fallback=resolved.g2p_fallback,
            lexicon_data_policy=resolved.lexicon_data_policy,
            voice_level=resolved.voice_level,
            allow_experimental=resolved.allow_experimental,
        )

    def save_synthesis_setup(
        self,
        project: ProjectView,
        request: AudiobookOptions,
        synthesis: SynthesisView,
    ) -> AudiobookOptions:
        resolved = SynthesisResolution(
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
        settings = project_settings(request, resolved)
        self._app.projects.configure(project.path, settings)
        return apply_project_settings(request, settings)

    def load_setup(
        self, project: ProjectView, request: AudiobookOptions
    ) -> tuple[AudiobookOptions, SetupOrigins, bool]:
        settings = self._app.projects.settings(project.path)
        return (
            apply_project_settings(request, settings),
            SetupOrigins(project=project_setting_sources(settings)),
            has_synthesis_setup(settings),
        )

    def build(
        self, project: ProjectView, request: AudiobookOptions
    ) -> OperationResultView:
        output_format = request.format.lower()
        if output_format in SUPPORTED_AUDIOBOOK_FORMATS:
            if output_format != AUDIOBOOK_EXPORT_FORMAT:
                raise ValueError(f"Unsupported audiobook format: {output_format}")
            self._app.projects.build(project.path)
            export_options = None
            if request.force:
                saved = self._app.projects.settings(project.path).audiobook_export
                if saved is None:
                    raise ValueError(
                        "No saved audiobook export settings are available."
                    )
                export_options = replace(saved, force=True)
            result = self._app.audiobooks.export(project.path, export_options)
        else:
            if output_format not in SUPPORTED_AUDIO_FORMATS:
                supported = (*SUPPORTED_AUDIO_FORMATS, *SUPPORTED_AUDIOBOOK_FORMATS)
                raise ValueError(
                    f"Unsupported audio format {output_format!r}; "
                    f"choose from {', '.join(supported)}."
                )
            if request.force:
                saved = self._app.projects.settings(project.path).export
                if saved is None:
                    raise ValueError("No saved export settings are available.")
                build_request = ProjectBuildRequest(
                    target="export",
                    selection="all",
                    export=replace(saved, force=True),
                )
                result = self._app.projects.build(project.path, build_request)
            else:
                result = self._app.projects.build(project.path)
        return OperationResultView(
            operation="build",
            project=project,
            output=result.output_path,
            details=result.to_dict(),
        )

    def preview(
        self, project: ProjectView, request: AudiobookOptions, selection: str
    ) -> PreviewView:
        request = self._canonical_request(request)
        result = self._app.projects.preview(
            project.path,
            PreviewRequest(
                selection=selection,
                synthesis=synthesis_request(request),
                composition=composition_options(request),
            ),
        )
        return PreviewView(
            project=project,
            items=result.items,
            frames=result.frames,
            sample_rate=result.sample_rate,
        )

    def status(self, project: ProjectView | Path) -> ProjectStatusView:
        result = self._app.projects.status(
            project.path if isinstance(project, ProjectView) else project
        )
        view = self._project_view(result.project)
        return ProjectStatusView(
            project=view,
            status="ready" if not result.issues else "needs_attention",
            details=result.to_dict(),
        )

    def plan(self, project: ProjectView | Path) -> ProjectPlanView:
        result = self._app.projects.plan(
            project.path if isinstance(project, ProjectView) else project
        )
        return ProjectPlanView(
            project=self._project_view(result.project),
            details=result.to_dict(),
        )

    def catalog_choices(
        self, kind: str, query: Mapping[str, object]
    ) -> tuple[CatalogItemView, ...]:
        if kind == "engines":
            return tuple(
                CatalogItemView(item.id, item.id, engine=item.id)
                for item in self._app.catalog.engines()
            )
        discovery = DiscoveryOptions(
            offline=bool(query.get("offline", False)),
            refresh=bool(query.get("refresh", False)),
        )
        language = _string_query(query, "language")
        engine = _string_query(query, "engine")
        if engine is not None:
            engine = normalize_engine(self._app, engine)
        if kind == "models":
            listing: CatalogListing[ModelInfo] = self._app.catalog.models_listing(
                ModelQuery(language=language, engine=engine), discovery=discovery
            )
            return tuple(
                CatalogItemView(
                    item.id,
                    item.id,
                    engine=item.engine,
                    language=language,
                )
                for item in listing.items
            )
        model = _string_query(query, "model")
        if kind == "voices":
            listing: CatalogListing[VoiceInfo] = self._app.catalog.voices_listing(
                VoiceQuery(language=language, engine=engine, model=model),
                discovery=discovery,
            )
            return tuple(
                CatalogItemView(
                    item.id,
                    item.id,
                    engine=item.engine,
                    language=item.locale,
                )
                for item in listing.items
            )
        if kind == "lexicons":
            listing: CatalogListing[LexiconInfo] = self._app.catalog.lexicons_listing(
                LexiconQuery(language=language, engine=engine, model=model),
                discovery=discovery,
            )
            return tuple(
                CatalogItemView(
                    item.selector,
                    item.display_name or item.selector,
                    engine=item.engine,
                    language=item.locale,
                )
                for item in listing.items
            )
        raise ValueError(f"Unknown catalog choice kind: {kind}")

    def _canonical_request(self, request: AudiobookOptions) -> AudiobookOptions:
        if request.engine is None:
            return request
        return replace(request, engine=normalize_engine(self._app, request.engine))

    def normalize_engine(self, engine: str) -> str:
        return normalize_engine(self._app, engine)

    def inspect(self, source: Path) -> AudiobookInspection:
        return self._app.audiobooks.inspect(source)

    def resolve_synthesis_raw(
        self,
        project: ProjectRef | Path,
        request: SynthesisRequest | AudiobookOptions | None,
        *,
        use_saved_settings: bool = True,
    ) -> SynthesisResolution:
        if isinstance(request, AudiobookOptions):
            request = synthesis_request(request)
        if request is not None and request.engine is not None:
            request = replace(request, engine=self.normalize_engine(request.engine))
        if use_saved_settings:
            return self._app.projects.resolve_synthesis(project, request)
        return self._app.projects.resolve_synthesis(
            project, request, use_saved_settings=False
        )

    def project_settings(self, project: ProjectRef | Path) -> ProjectSettings:
        return self._app.projects.settings(project)

    def configure_project(
        self, project: ProjectRef | Path, settings: ProjectSettings
    ) -> ProjectSettings:
        return self._app.projects.configure(project, settings)

    def engines(self) -> tuple[EngineInfo, ...]:
        return cast(tuple[EngineInfo, ...], self._app.catalog.engines())

    @staticmethod
    def _discovery_options(
        discovery: DiscoveryRequest | DiscoveryOptions,
    ) -> DiscoveryOptions:
        if isinstance(discovery, DiscoveryOptions):
            return discovery
        return DiscoveryOptions(
            offline=discovery.offline,
            refresh=discovery.refresh,
            preference=discovery.preference,
        )

    def models_listing(
        self,
        *,
        language: str | None,
        engine: str | None,
        discovery: DiscoveryRequest | DiscoveryOptions,
        status: str | None = None,
    ) -> CatalogListing[ModelInfo]:
        return self._app.catalog.models_listing(
            ModelQuery(
                language=language,
                engine=self.normalize_engine(engine) if engine is not None else None,
                status=status,
            ),
            discovery=self._discovery_options(discovery),
        )

    def voices_listing(
        self,
        *,
        language: str | None,
        engine: str | None,
        model: str | None,
        discovery: DiscoveryRequest | DiscoveryOptions,
        gender: str | None = None,
    ) -> CatalogListing[VoiceInfo]:
        return self._app.catalog.voices_listing(
            VoiceQuery(
                language=language,
                engine=self.normalize_engine(engine) if engine is not None else None,
                model=model,
                gender=gender,
            ),
            discovery=self._discovery_options(discovery),
        )

    def lexicons_listing(
        self,
        *,
        language: str | None,
        engine: str | None,
        model: str | None,
        discovery: DiscoveryRequest | DiscoveryOptions,
    ) -> CatalogListing[LexiconInfo]:
        return self._app.catalog.lexicons_listing(
            LexiconQuery(
                language=language,
                engine=self.normalize_engine(engine) if engine is not None else None,
                model=model,
            ),
            discovery=self._discovery_options(discovery),
        )

    def audio_formats(self) -> tuple[Any, ...]:
        return self._app.catalog.audio_formats()

    def diagnostics(self) -> Any:
        return self._app.diagnostics.run()

    def configuration_path(self) -> Path:
        return self._app.configuration.path()

    def configuration_load(self, path: Path | None = None) -> Any:
        return self._app.configuration.load(path)

    def configuration_set_value(
        self, key: str, value: object, *, path: Path | None = None
    ) -> None:
        self._app.configuration.set_value(key, value, path=path)

    def configuration_initialize(self, *, overwrite: bool = False) -> Any:
        return self._app.configuration.initialize(overwrite=overwrite)

    def configuration_language_profiles(self) -> Any:
        return self._app.configuration.language_profiles()

    def configuration_resolve_language_profile(self, language: str) -> Any:
        return self._app.configuration.resolve_language_profile(language)

    def ssmd_check(self, source: Path, *, roundtrip: bool = False) -> Any:
        return self._app.ssmd.check(source, roundtrip=roundtrip)

    def ssmd_validate(self, source: Path, *, roundtrip: bool = False) -> Any:
        return self._app.ssmd.validate(source, roundtrip=roundtrip)

    def ssmd_analyze(self, source: Path) -> Any:
        return self._app.ssmd.analyze(source)

    def ssmd_roundtrip_check(self, source: Path) -> Any:
        return self._app.ssmd.roundtrip_check(source)

    def ssmd_materialize_bindings(
        self,
        source: Path,
        bindings: Mapping[str, str],
        *,
        provider: str | None = None,
        output: Path | None = None,
        in_place: bool = False,
    ) -> Any:
        return self._app.ssmd.materialize_bindings(
            source, bindings, provider=provider, output=output, in_place=in_place
        )

    def find_project_ref(self, path: Path) -> ProjectRef | None:
        try:
            existing = self._app.projects.find(path)
        except ProjectFormatError as exc:
            if is_readio_project_migration_required(exc):
                raise ProjectMigrationRequiredError(
                    "This Readio project uses the v0.3 schema and must be migrated "
                    "before TTSForge can open it.\nRun:\n"
                    f'    readio project migrate "{path}"\n'
                    "TTSForge will not migrate or overwrite it automatically."
                ) from exc
            raise LegacyWorkspaceError(
                "This directory is not a Readio project and cannot resume a legacy "
                "TTSForge workspace. Start a separate project with --fresh."
            ) from exc
        if existing is None and path.exists():
            raise LegacyWorkspaceError(
                f"The existing directory is not a Readio project: {path}. "
                "Legacy TTSForge workspaces cannot be resumed; use --fresh "
                "to create a separate Readio project."
            )
        return existing

    def open_project_ref(self, project: ProjectRef | Path) -> ProjectRef:
        path = project.root if isinstance(project, ProjectRef) else project
        return self._app.projects.open(path)

    def describe_project(self, project: ProjectRef | Path) -> object:
        return self._app.audiobooks.describe_project(project)

    def create_project_result(
        self, source: Path, *, chapters: str, output: Path
    ) -> object:
        return self._app.audiobooks.create_project_result(
            source, chapters=chapters, output=output
        )

    def status_raw(self, project: ProjectRef | Path) -> ProjectStatus:
        return self._app.projects.status(project)

    def plan_raw(self, project: ProjectRef | Path) -> ProjectPlanResult:
        return self._app.projects.plan(project)

    def build_and_export(
        self, project: ProjectRef | Path, options: AudiobookOptions
    ) -> AudiobookExportResult | ProjectBuildResult:
        output_format = options.format.lower()
        if output_format in SUPPORTED_AUDIOBOOK_FORMATS:
            if output_format != AUDIOBOOK_EXPORT_FORMAT:
                raise ValueError(f"Unsupported audiobook format: {output_format}")
            self._app.projects.build(project)
            export_options = None
            if options.force:
                saved = self.project_settings(project).audiobook_export
                if saved is None:
                    raise ValueError(
                        "No saved audiobook export settings are available."
                    )
                export_options = replace(saved, force=True)
            return self._app.audiobooks.export(project, export_options)
        if output_format not in SUPPORTED_AUDIO_FORMATS:
            supported = (*SUPPORTED_AUDIO_FORMATS, *SUPPORTED_AUDIOBOOK_FORMATS)
            raise ValueError(
                f"Unsupported audio format {output_format!r}; "
                f"choose from {', '.join(supported)}."
            )
        if options.force:
            saved = self.project_settings(project).export
            if saved is None:
                raise ValueError("No saved export settings are available.")
            request = ProjectBuildRequest(
                target="export", selection="all", export=replace(saved, force=True)
            )
            return self._app.projects.build(project, request)
        return self._app.projects.build(project)

    def preview_raw(
        self, project: ProjectRef | Path, options: AudiobookOptions, selection: str
    ) -> PreviewResult:
        options = self._canonical_request(options)
        return self._app.projects.preview(
            project,
            PreviewRequest(
                selection=selection,
                synthesis=synthesis_request(options),
                composition=composition_options(options),
            ),
        )


def _string_query(query: Mapping[str, object], name: str) -> str | None:
    value = query.get(name)
    return value if isinstance(value, str) else None
