"""The single public-API integration seam between TTSForge and Readio."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import readio.api as readio_api

from .application.errors import WorkflowFailureError
from .application.events import ApplicationEvent
from .application.models import (
    AudiobookCapabilitiesView,
    AudiobookMetadata,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ConversionResultView,
    EngineModelView,
    ExecutionSummaryView,
    PreviewAudio,
    ProjectPaths,
    SpacyModelView,
    StageExecutionView,
    WorkflowBlockerView,
    WorkflowPlanView,
    WorkflowStepView,
)

__all__ = ["ReadioBackend", "ReadioError", "create_readio"]

ReadioError = readio_api.ReadioError


def _workflow_failure(
    error: readio_api.ReadioError,
    *,
    category: str,
) -> WorkflowFailureError:
    info = readio_api.describe_error(error)
    category = {
        "output_exists": "output collision",
        "stage_failed": "render-stage failure",
        "unsafe_workflow_state": "workflow preflight failure",
        "workflow_replan_failed": "workflow preflight failure",
        "catalog_operation_failed": "runtime/backend unavailable",
        "cancellation_requested": "cancelled",
        "invalid_request": "configuration / setup invalid",
    }.get(info.code) or ("render-stage failure" if info.stage is not None else category)
    return WorkflowFailureError(
        info.message,
        category=category,
        stage=info.stage,
        package=info.package,
        selector=info.selector,
        code=info.code,
        details=info.details,
        recoverable=info.recoverable,
        suggested_action=info.suggested_action,
    )


def normalize_readio_error(
    error: Exception,
    *,
    category: str = "runtime/backend unavailable",
) -> WorkflowFailureError | None:
    """Translate a public Readio error to TTSForge's structured error view."""
    if not isinstance(error, readio_api.ReadioError):
        return None
    return _workflow_failure(error, category=category)


def _application_event(event: readio_api.WorkflowEvent) -> ApplicationEvent:
    return ApplicationEvent(
        stage=_value(event.stage),
        kind=event.kind,
        message=event.message,
        package=event.package,
        selector=event.selector,
        current=event.current,
        total=event.total,
        elapsed_seconds=event.elapsed_seconds,
        details=dict(event.details),
    )


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _metadata_text(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if key == "author" and value is None:
        value = metadata.get("authors")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if key == "author" and isinstance(value, (list, tuple)):
        authors = [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
        return ", ".join(authors) or None
    return None


def _audiobook_metadata(
    values: Mapping[str, object], *, cover: Path | None = None
) -> AudiobookMetadata:
    return AudiobookMetadata(
        title=_metadata_text(values, "title"),
        subtitle=_metadata_text(values, "subtitle"),
        author=_metadata_text(values, "author"),
        narrator=_metadata_text(values, "narrator"),
        series=_metadata_text(values, "series"),
        series_number=(
            _metadata_text(values, "series_number")
            or _metadata_text(values, "series_index")
        ),
        language=_metadata_text(values, "language"),
        publisher=_metadata_text(values, "publisher"),
        year=_metadata_text(values, "year"),
        cover=cover,
    )


def _spacy_model_view(info: readio_api.SpacyModelInfo) -> SpacyModelView:
    return SpacyModelView(
        language=info.language,
        tier=_value(info.tier),
        model=info.model,
        installed=info.installed,
        spacy_version=info.spacy_version,
        model_version=info.model_version,
    )


def _engine_model_view(info: readio_api.EngineModelInfo) -> EngineModelView:
    return EngineModelView(
        engine=info.engine,
        target=info.target,
        quality=info.quality,
        language=info.language,
        label=info.label,
        installed=info.installed,
        available=info.available,
        state=info.state,
        local_version=info.local_version,
        available_version=info.available_version,
        update_state=info.update_state,
        bytes_installed=info.bytes_installed,
        bytes_download=info.bytes_download,
        storage_id=info.storage_id,
        installable=info.installable,
        updatable=info.updatable,
        removable=info.removable,
        verifiable=info.verifiable,
        reason=info.reason,
    )


class ReadioBackend:
    """Delegate workflow and discovery operations to Readio's public API."""

    def __init__(self, app: readio_api.Readio | None = None) -> None:
        self._app = app if app is not None else create_readio()

    def inspect_source(self, source: Path) -> BookInspectionView:
        try:
            inspection = self._app.inspect_source(source)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="source inspection failure",
            ) from error
        metadata = inspection.metadata
        product_metadata = _audiobook_metadata(metadata)
        return BookInspectionView(
            source=inspection.source,
            kind=inspection.kind,
            title=product_metadata.title,
            author=product_metadata.author,
            language=product_metadata.language,
            chapters=tuple(
                BookChapterView(
                    number=chapter.number,
                    title=chapter.title,
                    source_id=chapter.source_id,
                    char_count=chapter.char_count,
                )
                for chapter in inspection.chapters
            ),
            metadata=product_metadata,
        )

    def list_engines(self) -> tuple[readio_api.EngineInfo, ...]:
        try:
            return self._app.list_engines()
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

    def list_targets(
        self,
        *,
        engine: str,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[readio_api.TargetInfo, ...]:
        try:
            return self._app.list_targets(
                engine,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

    def list_models(
        self,
        engine: str,
        *,
        language: str | None = None,
        installed: bool | None = None,
        available: bool = False,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[EngineModelView, ...]:
        try:
            models = self._app.list_models(
                engine,
                language=language,
                installed=installed,
                available=available,
                offline=offline,
                refresh=refresh,
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource inventory failure"
            ) from error
        return tuple(_engine_model_view(model) for model in models)

    def model_status(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        try:
            model = self._app.model_status(engine, target, quality=quality)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource inventory failure"
            ) from error
        return _engine_model_view(model)

    def install_model(
        self,
        engine: str,
        target: str,
        *,
        quality: str | None = None,
        source: str | None = None,
        force: bool = False,
    ) -> EngineModelView:
        try:
            model = self._app.install_model(
                engine,
                target,
                quality=quality,
                source=source,
                force=force,
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource operation failure"
            ) from error
        return _engine_model_view(model)

    def update_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        try:
            model = self._app.update_model(engine, target, quality=quality)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource operation failure"
            ) from error
        return _engine_model_view(model)

    def verify_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        try:
            model = self._app.verify_model(engine, target, quality=quality)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource operation failure"
            ) from error
        return _engine_model_view(model)

    def remove_model(
        self, engine: str, target: str, *, quality: str | None = None
    ) -> EngineModelView:
        try:
            model = self._app.remove_model(engine, target, quality=quality)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="resource operation failure"
            ) from error
        return _engine_model_view(model)

    def list_engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[readio_api.EngineOptionInfo, ...]:
        try:
            return self._app.list_engine_options(engine, target=target)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

    def list_voices(
        self,
        *,
        engine: str | None = None,
        target: str | None = None,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[readio_api.VoiceInfo, ...]:
        try:
            engine_ids = (
                (engine,)
                if engine is not None
                else tuple(
                    item.id for item in self._app.list_engines() if item.runnable
                )
            )
            voices: list[readio_api.VoiceInfo] = []
            for engine_id in engine_ids:
                targets = self._app.list_targets(
                    engine_id,
                    language=language,
                    offline=offline,
                    refresh=refresh,
                )
                for target_info in targets:
                    if target is not None and target_info.id != target:
                        continue
                    voices.extend(
                        self._app.list_voices(
                            engine=engine_id,
                            target=target_info.id,
                            language=language,
                            offline=offline,
                            refresh=refresh,
                        )
                    )
            return tuple(voices)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

    def capabilities(self) -> AudiobookCapabilitiesView:
        try:
            readio_capabilities = self._app.capabilities()
            synthesis = self._app.synthesis_capabilities()
            export_formats = self._app.export_capabilities()
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

        available_engines = tuple(
            engine.id for engine in synthesis.engines if engine.runnable
        )
        m4b_export = any(
            item.extension.casefold() == ".m4b" and item.available
            for item in export_formats
        )
        warnings = list(readio_capabilities.warnings)
        if synthesis.reason is not None and synthesis.reason not in warnings:
            warnings.append(synthesis.reason)
        if not m4b_export:
            m4b = next(
                (
                    item
                    for item in export_formats
                    if item.extension.casefold() == ".m4b"
                ),
                None,
            )
            warnings.append(
                m4b.reason
                if m4b is not None and m4b.reason
                else "M4B export is unavailable."
            )

        return AudiobookCapabilitiesView(
            source_inspection=readio_capabilities.workflow.conversion == "ready",
            synthesis_preview=synthesis.state == "ready",
            m4b_export=m4b_export,
            persistent_workspace=True,
            available_engines=available_engines,
            warnings=tuple(warnings),
        )

    def new_cancellation_token(self) -> readio_api.CancellationToken:
        return readio_api.CancellationToken()

    def synthesize_preview(
        self,
        *,
        text: str,
        profile: Path,
        role: str | None = None,
        cancellation: object | None = None,
    ) -> PreviewAudio:
        try:
            result = self._app.synthesize(
                readio_api.SpeakRequest(text=text, profile=profile, role=role),
                cancellation=cast(readio_api.CancellationToken | None, cancellation),
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error, category="preview synthesis failure"
            ) from error
        audio = result.audio
        return PreviewAudio(
            wav=audio.to_wav_bytes(),
            sample_rate=audio.sample_rate,
            channels=audio.channels,
            frames=audio.frames,
            duration_seconds=audio.duration_seconds,
            warnings=tuple(result.warnings),
        )

    def list_spacy_models(self, language: str) -> tuple[SpacyModelView, ...]:
        try:
            models = readio_api.list_spacy_models(language)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="spaCy model inventory failure",
            ) from error
        return tuple(_spacy_model_view(model) for model in models)

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView:
        try:
            info = readio_api.inspect_spacy_model(language, cast(Any, tier))
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="spaCy model inspection failure",
            ) from error
        return _spacy_model_view(info)

    def ensure_spacy_model(
        self,
        language: str,
        tier: str,
        *,
        offline: bool = False,
    ) -> SpacyModelView:
        if tier not in {"sm", "md", "lg", "trf"}:
            raise ValueError("Only concrete spaCy model tiers can be provisioned.")
        inspected = self.inspect_spacy_model(language, tier)
        if inspected.installed:
            return inspected
        if offline:
            raise WorkflowFailureError(
                f"spaCy model {inspected.model!r} is not installed "
                "and offline mode is enabled.",
                category="spaCy model unavailable",
                stage="prepare",
                package="spacy",
                selector=inspected.model,
                code="spacy_model_missing_offline",
                details={"language": language, "tier": tier, "model": inspected.model},
            )
        try:
            info = readio_api.ensure_spacy_model(
                language,
                cast(Any, tier),
                offline=False,
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="spaCy model provisioning failure",
            ) from error
        except (RuntimeError, subprocess.CalledProcessError) as error:
            raise WorkflowFailureError(
                str(error),
                category="spaCy model provisioning failure",
                stage="prepare",
                package="spacy",
                selector=inspected.model,
                code="spacy_model_provision_failed",
                details={"language": language, "tier": tier, "model": inspected.model},
            ) from error
        return _spacy_model_view(info)

    def inspect_voice(self, selector: str, *, language: str | None = None) -> object:
        return readio_api.inspect_voice(selector, language=language)

    def create_profile(
        self,
        *,
        output: Path,
        engine: str,
        target: str,
        language: str,
        voice: str | None,
        options: Mapping[str, object],
        offline: bool = False,
        refresh: bool = False,
        force: bool = False,
    ) -> object:
        return readio_api.create_profile(
            output=output,
            engine=engine,
            target=target,
            language=language,
            voice=voice,
            options=dict(options),
            offline=offline,
            refresh=refresh,
            force=force,
        )

    def load_profile(self, path: Path) -> object:
        return readio_api.load_profile(path)

    def validate_profile(self, path: Path) -> object:
        return readio_api.validate_profile(path)

    def create_book_intent(
        self,
        *,
        source: Path,
        profile: Path,
        bundle: Path,
        chapters: str,
        language: str | None,
        output: Path,
        bitrate: str | int | None,
        cover: Path | None,
        metadata: Mapping[str, str],
        spacy: str | None = None,
        speech_profile: Path | None = None,
        pause_timing: str | None = None,
        target_lufs: float | None = -18.0,
    ) -> readio_api.RenderIntent:
        planning_spacy = "on" if spacy in {"sm", "md", "lg", "trf"} else spacy or "auto"
        return readio_api.create_book_intent(
            source,
            profile=profile,
            bundle=bundle,
            chapters=chapters,
            language=language,
            spacy=planning_spacy,
            output_format="m4b",
            output=output,
            bitrate=bitrate,
            cover=cover,
            metadata=dict(metadata),
            target_lufs=target_lufs,
            preparation=readio_api.PreparationIntent(
                spacy=cast(Any, spacy),
                speech_profile=speech_profile,
            ),
            projection=readio_api.ProjectionIntent(
                pause_timing=pause_timing or "fixed"
            ),
        )

    def load_intent(self, path: Path) -> readio_api.RenderIntent:
        return readio_api.load_render_intent(path)

    def save_intent(self, intent: readio_api.RenderIntent, path: Path) -> Path:
        return cast(
            Path,
            readio_api.save_render_intent(intent, path, force=True),
        )

    def load_setup(self, paths: ProjectPaths) -> AudiobookRequest:
        intent = self.load_intent(paths.intent)
        profile = cast(Any, self.load_profile(paths.profile))
        self.validate_profile(paths.profile)
        source = intent.input.source
        if source is None:
            raise ValueError(f"Saved render intent has no source: {paths.intent}")

        role = profile.roles[profile.default_role]
        binding = role.binding
        options = dict(binding.get("options", {}))
        speed_value = options.pop("speed", None)
        speed = speed_value if isinstance(speed_value, (int, float)) else None
        output_metadata = intent.output.metadata
        preparation = getattr(intent, "preparation", None)
        projection = getattr(intent, "projection", None)
        spacy = getattr(preparation, "spacy", None)
        speech_profile = getattr(preparation, "speech_profile", None)
        pause_timing = getattr(projection, "pause_timing", None)
        return AudiobookRequest(
            source=source,
            project=paths.root,
            chapters=intent.input.chapters,
            output=intent.output.path,
            language=role.language,
            engine=str(binding["renderer"]),
            target=str(binding["target_id"]),
            voice=binding.get("voice"),
            engine_options=options,
            speed=speed,
            spacy=spacy,
            speech_profile=speech_profile,
            pause_timing=_value(pause_timing) if pause_timing is not None else None,
            bitrate=intent.output.bitrate,
            target_lufs=intent.compose.target_lufs,
            metadata=_audiobook_metadata(output_metadata, cover=intent.output.cover),
            title=output_metadata.get("title"),
            author=output_metadata.get("author"),
            cover=intent.output.cover,
        )

    def save_setup(self, paths: ProjectPaths, request: AudiobookRequest) -> None:
        if request.language is None or request.engine is None or request.target is None:
            raise ValueError("Language, engine, and target are required to save setup.")
        if request.output is None:
            raise ValueError("Output path is required to save setup.")

        options = dict(request.engine_options)
        if request.speed is not None:
            options["speed"] = request.speed
        metadata = request.metadata.to_readio_mapping()
        try:
            intent = self.create_book_intent(
                source=request.source,
                profile=paths.profile,
                bundle=paths.bundle,
                chapters=request.chapters or "all",
                language=request.language,
                output=request.output,
                bitrate=request.bitrate,
                cover=request.cover,
                metadata=metadata,
                spacy=request.spacy,
                speech_profile=request.speech_profile,
                pause_timing=request.pause_timing,
                target_lufs=(
                    request.target_lufs if request.target_lufs is not None else -18.0
                ),
            )
            self.create_profile(
                output=paths.profile,
                engine=request.engine,
                target=request.target,
                language=request.language,
                voice=request.voice,
                options=options,
                offline=request.offline,
                refresh=request.refresh,
                force=paths.profile.exists(),
            )
            self.save_intent(intent, paths.intent)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="configuration / setup invalid",
            ) from error

    def request_from_intent(
        self, paths: ProjectPaths, request: AudiobookRequest
    ) -> object:
        try:
            intent = self.load_intent(paths.intent)
            return readio_api.render_request_from_intent(
                intent,
                source=request.source,
                bundle=paths.bundle,
                profile=paths.profile,
                rebuild_from=request.rebuild_from,
                replace_output=request.replace_output,
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="configuration / setup invalid",
            ) from error

    def inspect(self, request: object) -> WorkflowPlanView:
        try:
            plan = self._app.inspect(cast(readio_api.RenderRequest, request))
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="workflow preflight failure",
            ) from error
        return WorkflowPlanView(
            source=plan.source,
            workspace=plan.workspace,
            workspace_mode=_value(plan.workspace_mode),
            output=plan.output,
            steps=tuple(
                WorkflowStepView(
                    stage=_value(step.stage),
                    package=step.package,
                    action=_value(step.action),
                    selector=step.selector,
                    reason=step.reason,
                    state=_value(step.state),
                    reason_code=_value(step.reason_code),
                    force=step.force,
                    blockers=tuple(
                        WorkflowBlockerView(
                            code=blocker.code,
                            message=blocker.message,
                            owner=blocker.owner,
                            recoverable=blocker.recoverable,
                            suggested_action=blocker.suggested_action,
                        )
                        for blocker in step.blockers
                    ),
                )
                for step in plan.steps
            ),
            warnings=tuple(plan.warnings),
            executable=plan.executable,
            variant=plan.variant,
        )

    def render(
        self,
        request: object,
        *,
        on_progress: Callable[[ApplicationEvent], None] | None = None,
    ) -> ConversionResultView:
        def forward(event: readio_api.WorkflowEvent) -> None:
            if on_progress is not None:
                on_progress(_application_event(event))

        try:
            result = self._app.render(
                cast(readio_api.RenderRequest, request),
                on_progress=forward if on_progress is not None else None,
                include_report=True,
            )
        except readio_api.ReadioError as error:
            failure = _workflow_failure(
                error,
                category="runtime/backend unavailable",
            )
            profile = cast(readio_api.RenderRequest, request).profile
            failure.details["saved_setup"] = {
                "project": str(profile.parent),
                "intent": str(profile.parent / "render.readio.toml"),
                "profile": str(profile),
            }
            raise failure from error

        report = result.report
        execution = (
            ExecutionSummaryView(
                stages=tuple(
                    StageExecutionView(
                        stage=_value(stage.stage),
                        package=stage.package,
                        action=_value(stage.action),
                        state_before=_value(stage.state_before),
                        state_after=(
                            _value(stage.state_after)
                            if stage.state_after is not None
                            else None
                        ),
                        elapsed_seconds=stage.elapsed_seconds,
                        reason_code=_value(stage.reason_code),
                    )
                    for stage in report.stages
                ),
                specialist_versions=dict(report.specialist_versions),
                elapsed_seconds=report.elapsed_seconds,
            )
            if report is not None
            else None
        )
        return ConversionResultView(
            output=result.output,
            workspace=result.workspace,
            workspace_mode=_value(result.workspace_mode),
            executed_stages=tuple(result.executed_stages),
            reused_stages=tuple(result.reused_stages),
            warnings=tuple(result.warnings),
            variant=result.variant,
            execution=execution,
        )


def create_readio() -> readio_api.Readio:
    return readio_api.Readio()
