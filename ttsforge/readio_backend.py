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
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    ConversionResultView,
    ProjectPaths,
    SpacyModelView,
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
    if isinstance(error, readio_api.OutputCollisionError):
        category = "output collision"
    elif isinstance(error, readio_api.WorkflowStageError):
        category = "render-stage failure"
    elif isinstance(error, readio_api.WorkflowError):
        category = "workflow preflight failure"
    details = getattr(error, "details", {})
    return WorkflowFailureError(
        str(error),
        category=category,
        stage=getattr(error, "stage", None),
        package=getattr(error, "package", None),
        selector=getattr(error, "selector", None),
        code=getattr(error, "code", None),
        details=details if isinstance(details, Mapping) else {},
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


def _spacy_model_view(info: readio_api.SpacyModelInfo) -> SpacyModelView:
    return SpacyModelView(
        language=info.language,
        tier=_value(info.tier),
        model=info.model,
        installed=info.installed,
        spacy_version=info.spacy_version,
        model_version=info.model_version,
    )


class ReadioBackend:
    """Delegate workflow and discovery operations to Readio's public API."""

    def __init__(self, app: readio_api.Readio | None = None) -> None:
        self._app = app if app is not None else create_readio()

    def inspect_source(self, source: Path) -> BookInspectionView:
        try:
            inspection = readio_api.inspect_source(source)
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="source inspection failure",
            ) from error
        metadata = inspection.metadata
        return BookInspectionView(
            source=inspection.source,
            kind=inspection.kind,
            title=_metadata_text(metadata, "title"),
            author=_metadata_text(metadata, "author"),
            language=_metadata_text(metadata, "language"),
            chapters=tuple(
                BookChapterView(
                    number=chapter.number,
                    title=chapter.title,
                    source_id=chapter.source_id,
                    char_count=chapter.char_count,
                )
                for chapter in inspection.chapters
            ),
        )

    def list_engines(self) -> tuple[dict[str, object], ...]:
        try:
            return tuple(readio_api.list_engines())
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
    ) -> tuple[object, ...]:
        try:
            return cast(
                tuple[object, ...],
                readio_api.discover_engine_targets(
                    engine,
                    language=language,
                    offline=offline,
                    refresh=refresh,
                ),
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

    def list_engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[object, ...]:
        return cast(
            tuple[object, ...],
            readio_api.list_engine_options(engine, target=target),
        )

    def list_voices(
        self,
        *,
        engine: str | None = None,
        target: str | None = None,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[object, ...]:
        try:
            return cast(
                tuple[object, ...],
                readio_api.list_voices(
                    engine=engine,
                    target=target,
                    language=language,
                    offline=offline,
                    refresh=refresh,
                ),
            )
        except readio_api.ReadioError as error:
            raise _workflow_failure(
                error,
                category="runtime/backend unavailable",
            ) from error

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
        metadata = {
            key: value
            for key, value in (("title", request.title), ("author", request.author))
            if value is not None
        }
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
                )
                for step in plan.steps
            ),
            warnings=tuple(plan.warnings),
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
        return ConversionResultView(
            output=result.output,
            workspace=result.workspace,
            workspace_mode=_value(result.workspace_mode),
            executed_stages=tuple(result.executed_stages),
            reused_stages=tuple(result.reused_stages),
            warnings=tuple(result.warnings),
        )


def create_readio() -> readio_api.Readio:
    return readio_api.Readio()
