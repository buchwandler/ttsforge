"""Versioned local API backed only by TTSForge application services."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
import platform
import re
import shutil
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response
from starlette.types import ASGIApp

from ..application import (
    AudiobookApplicationService,
    AudiobookRequest,
    BlockedWorkflowError,
    CatalogApplicationService,
    CatalogSelectionError,
    ChapterApplicationService,
    ConversionCoordinator,
    InputValidationError,
    LibraryApplicationService,
    MetadataApplicationService,
    NarrationApplicationService,
    OperationConflictError,
    PreviewApplicationService,
    PreviewRequest,
    ProjectPaths,
    ProjectSummary,
    QcApplicationService,
    WorkflowFailureError,
    error_view,
    json_value,
)
from ..application.speech_profiles import (
    discover_speech_replacement_profiles,
    is_speech_replacement_profile,
)
from .auth import require_bearer_token
from .job_store import SqliteJobStore
from .jobs import JobManager, JobRecord, JobState
from .models import (
    ApiErrorResponseModel,
    AudiobookCapabilitiesResponseModel,
    AudiobookMetadataViewResponseModel,
    BookInspectionResponseModel,
    ChapterListResponseModel,
    ChapterSelectionRequestModel,
    ChapterSelectionResponseModel,
    DeleteSourceImportResponseModel,
    EngineChoiceResponseModel,
    EngineOptionResponseModel,
    HealthResponseModel,
    JobCreateResponseModel,
    JobEventsPageResponseModel,
    JobListResponseModel,
    JobStateLiteral,
    JobStatusResponseModel,
    JobSubmissionModel,
    LibraryProjectsResponseModel,
    MetadataValidationResponseModel,
    NarrationCreateRequestModel,
    NarrationDeleteResponseModel,
    NarrationListResponseModel,
    NarrationResponseModel,
    PreflightResponseModel,
    PreviewRequestModel,
    ProjectInfoResponseModel,
    ProjectMetadataSetRequestModel,
    ProjectPathRequestModel,
    ProjectQcRequestModel,
    ProjectSetupResponseModel,
    ProjectSummaryResponseModel,
    ProjectVariantResponseModel,
    QcReportResponseModel,
    RuntimeStatusResponseModel,
    SetupResolutionResponseModel,
    SourceImportResponseModel,
    SourceImportStatusResponseModel,
    SourceInspectRequest,
    SpacyEnsureRequest,
    SpacyModelResponseModel,
    SpeechProfileInspectRequest,
    SpeechProfileInspectResponseModel,
    SpeechProfilesResponseModel,
    SystemResponseModel,
    TargetChoiceResponseModel,
    VoiceChoiceResponseModel,
    WorkflowPlanResponseModel,
)
from .requests import application_overrides, application_request, request_path

_LOG = logging.getLogger(__name__)
_API_VERSION = 1
_TAURI_ORIGINS = (
    "tauri://localhost",
    "https://tauri.localhost",
    "http://tauri.localhost",
)


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    audiobook: AudiobookApplicationService
    catalog: CatalogApplicationService
    conversion: ConversionCoordinator
    preview: PreviewApplicationService | None = None


class OriginPolicyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, allowed_origins: Sequence[str]) -> None:
        super().__init__(app)
        self._allowed_origins = frozenset(allowed_origins)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")
        if origin and not self._allowed(request, origin):
            return _http_error_response(403)
        return await call_next(request)

    def _allowed(self, request: Request, origin: str) -> bool:
        if origin in self._allowed_origins:
            return True
        same_origin = f"{request.url.scheme}://{request.url.netloc}"
        return origin.rstrip("/") == same_origin


def _job_lifespan(
    job_manager: JobManager,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await run_in_threadpool(job_manager.shutdown)

    return lifespan


def create_app(  # noqa: C901
    *,
    token: str,
    state_dir: Path | None = None,
    services: ApplicationServices | None = None,
    job_manager: JobManager | None = None,
    allowed_origins: Sequence[str] = (),
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024,
    import_retention_days: int = 30,
    debug: bool = False,
) -> FastAPI:
    if not token:
        raise ValueError("A non-empty bearer token is required.")
    if max_upload_bytes <= 0 or import_retention_days < 0:
        raise ValueError("Upload size and retention settings are invalid.")
    if any(origin == "*" for origin in allowed_origins):
        raise ValueError("Wildcard origins are not supported.")

    state = (state_dir or Path.home() / ".local" / "state" / "ttsforge").expanduser()
    imports_dir = state / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    cleanup_imports(imports_dir, retention_days=import_retention_days)
    app_services = services or _application_services()
    narrations = NarrationApplicationService(
        app_services.audiobook, app_services.catalog
    )
    chapter_service = ChapterApplicationService(app_services.audiobook)
    metadata_service = MetadataApplicationService(app_services.audiobook)
    qc_service = QcApplicationService(app_services.audiobook, narrations)
    library_service = LibraryApplicationService(app_services.audiobook, narrations)
    preview_service = getattr(app_services, "preview", None)
    jobs = (
        job_manager
        if job_manager is not None
        else JobManager(debug=debug, store=SqliteJobStore(state / "jobs.sqlite3"))
    )
    origins = tuple(dict.fromkeys((*_TAURI_ORIGINS, *allowed_origins)))

    app = FastAPI(
        title="TTSForge Local API",
        version="1",
        docs_url=None,
        redoc_url=None,
        lifespan=_job_lifespan(jobs),
    )
    app.state.token = token
    app.state.state_dir = state
    app.state.imports_dir = imports_dir
    app.state.services = app_services
    app.state.job_manager = jobs
    app.state.max_upload_bytes = max_upload_bytes
    app.state.debug = debug
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )
    app.add_middleware(OriginPolicyMiddleware, allowed_origins=origins)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        del request
        if debug:
            _LOG.exception("Unhandled local API request failure")
        else:
            _LOG.error("Unhandled local API request failure: %s", type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": json_value(error_view(error))},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request
        issues = [
            {
                "location": list(issue.get("loc", ())),
                "type": issue.get("type", "validation_error"),
                "message": issue.get("msg", "Invalid value."),
            }
            for issue in error.errors()
        ]
        return _api_error_response(
            status=400,
            error_type="RequestValidationError",
            message="The request is invalid.",
            code="invalid_request",
            details={"issues": issues},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        del request
        return _http_error_response(error.status_code)

    @app.exception_handler(InputValidationError)
    @app.exception_handler(CatalogSelectionError)
    async def handle_input_error(request: Request, error: Exception) -> JSONResponse:
        del request
        return _error_response(error, 400)

    @app.exception_handler(OperationConflictError)
    async def handle_conflict_error(request: Request, error: Exception) -> JSONResponse:
        del request
        return _error_response(error, 409)

    @app.exception_handler(BlockedWorkflowError)
    async def handle_blocked_workflow(
        request: Request, error: Exception
    ) -> JSONResponse:
        del request
        return _error_response(error, 422)

    @app.exception_handler(WorkflowFailureError)
    async def handle_workflow_failure(
        request: Request, error: WorkflowFailureError
    ) -> JSONResponse:
        del request
        status = (
            503
            if error.code in {"audioexport_unavailable", "spacy_model_missing_offline"}
            else 422
        )
        return _error_response(error, status)

    @app.get("/api/v1/health", response_model=HealthResponseModel)
    async def health() -> dict[str, bool]:
        return {"ok": True}

    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_bearer_token)],
        responses={
            400: {"model": ApiErrorResponseModel},
            401: {"model": ApiErrorResponseModel},
            403: {"model": ApiErrorResponseModel},
            404: {"model": ApiErrorResponseModel},
            409: {"model": ApiErrorResponseModel},
            413: {"model": ApiErrorResponseModel},
            422: {"model": ApiErrorResponseModel},
            503: {"model": ApiErrorResponseModel},
        },
    )

    @router.get("/system", response_model=SystemResponseModel)
    def system() -> dict[str, object]:
        return {
            "api_version": _API_VERSION,
            "ttsforge_version": _distribution_version("ttsforge"),
            "python_version": platform.python_version(),
            "capabilities": {
                "jobs": True,
                "job_events": True,
                "cancel": True,
                "source_upload": True,
                "setup_resolve": True,
                "preflight": True,
                "project_setup": True,
                "spacy_ensure": True,
                "speech_profiles": True,
                "narrations": True,
                "library": True,
                "preview": preview_service is not None,
            },
        }

    @router.get(
        "/system/capabilities",
        response_model=AudiobookCapabilitiesResponseModel,
    )
    def system_capabilities() -> object:
        return json_value(app_services.audiobook.capabilities())

    @router.get("/system/runtime", response_model=RuntimeStatusResponseModel)
    def system_runtime() -> dict[str, object]:
        return runtime_status()

    @router.post("/sources/inspect", response_model=BookInspectionResponseModel)
    def inspect_source(body: SourceInspectRequest) -> object:
        path = request_path(body.path)
        if not path.is_file() or not os.access(path, os.R_OK):
            raise InputValidationError(f"Source must be a readable file: {path}.")
        inspection = app_services.audiobook.inspect_book(path)
        if inspection.kind != "book":
            raise InputValidationError("Source is not a supported audiobook book.")
        return json_value(inspection)

    @router.post("/sources/import", response_model=SourceImportResponseModel)
    async def import_source(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        return await _import_source(
            file,
            app_services,
            imports_dir,
            max_upload_bytes=max_upload_bytes,
            retention_days=import_retention_days,
        )

    @router.get(
        "/sources/imports/{source_id}", response_model=SourceImportStatusResponseModel
    )
    def source_import_status(source_id: str) -> dict[str, object]:
        record = _source_import_record(source_id, imports_dir)
        if record is None:
            raise HTTPException(status_code=404, detail="Imported source not found.")
        directory, metadata = record
        return _source_import_view(directory, metadata, import_retention_days)

    @router.delete(
        "/sources/imports/{source_id}", response_model=DeleteSourceImportResponseModel
    )
    def delete_source_import(source_id: str) -> dict[str, object]:
        record = _source_import_record(source_id, imports_dir)
        if record is None:
            raise HTTPException(status_code=404, detail="Imported source not found.")
        directory, _ = record
        shutil.rmtree(directory)
        return {"source_id": source_id, "deleted": True}

    @router.post("/setup/resolve", response_model=SetupResolutionResponseModel)
    def resolve_setup(body: JobSubmissionModel) -> dict[str, object]:
        request = _request_for_import(
            application_request(body.request), imports_dir, state
        )
        overrides = application_overrides(body.explicit_fields)
        preparation = app_services.audiobook.prepare_setup(
            request, overrides, interactive=False
        )
        origins = preparation.origins
        return {
            "project": str(preparation.paths.root),
            "configuration_variant": preparation.paths.variant_key,
            "reused_setup": preparation.reused,
            "inspection": json_value(preparation.inspection),
            "request": json_value(preparation.request),
            "origins": {
                "explicit": sorted(origins.explicit),
                "project": sorted(origins.project),
                "derived": sorted(origins.derived),
            },
        }

    @router.post("/conversions/preflight", response_model=PreflightResponseModel)
    def conversion_preflight(body: JobSubmissionModel) -> dict[str, object]:
        request = _request_for_import(
            application_request(body.request),
            imports_dir,
            state,
            claim=True,
            create_output_parent=True,
        )
        overrides = application_overrides(body.explicit_fields)
        prepared = app_services.conversion.prepare(request, overrides)
        setup = prepared.resolved.preparation
        return {
            "project": str(setup.paths.root),
            "configuration_variant": setup.paths.variant_key,
            "reused_setup": setup.reused,
            "spacy_model": json_value(prepared.spacy_model),
            "request": json_value(prepared.resolved.request),
            "workflow": json_value(prepared.preflight.workflow),
        }

    @router.get("/catalog/engines", response_model=list[EngineChoiceResponseModel])
    def engines() -> object:
        return json_value(app_services.catalog.engines())

    @router.get("/catalog/targets", response_model=list[TargetChoiceResponseModel])
    def targets(
        engine: str,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> object:
        return json_value(
            app_services.catalog.targets(
                engine=engine,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        )

    @router.get("/catalog/voices", response_model=list[VoiceChoiceResponseModel])
    def voices(
        engine: str,
        target: str,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> object:
        target_views = app_services.catalog.targets(
            engine=engine,
            language=language,
            offline=offline,
            refresh=refresh,
        )
        selected = next((item for item in target_views if item.id == target), None)
        if selected is None:
            raise CatalogSelectionError(
                f"Target {target!r} is not available for engine {engine!r}."
            )
        return json_value(
            app_services.catalog.voices(
                engine=engine,
                target=target,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        )

    @router.get(
        "/catalog/engine-options", response_model=list[EngineOptionResponseModel]
    )
    def engine_options(engine: str, target: str | None = None) -> object:
        return json_value(app_services.catalog.engine_options(engine, target=target))

    @router.get("/resources/spacy", response_model=list[SpacyModelResponseModel])
    def spacy_models(language: str) -> object:
        return json_value(app_services.catalog.spacy_models(language))

    @router.post("/resources/spacy/ensure", response_model=SpacyModelResponseModel)
    def ensure_spacy_model(body: SpacyEnsureRequest) -> object:
        return json_value(
            app_services.catalog.ensure_spacy_model(
                body.language, body.tier, offline=body.offline
            )
        )

    @router.get(
        "/resources/speech-profiles", response_model=SpeechProfilesResponseModel
    )
    def speech_profiles(directory: str) -> dict[str, object]:
        path = request_path(directory)
        profiles = discover_speech_replacement_profiles(path)
        return {
            "directory": str(path),
            "profiles": [
                {"path": str(profile), "name": profile.name} for profile in profiles
            ],
        }

    @router.post(
        "/resources/speech-profiles/inspect",
        response_model=SpeechProfileInspectResponseModel,
    )
    def inspect_speech_profile(
        body: SpeechProfileInspectRequest,
    ) -> dict[str, object]:
        path = request_path(body.path)
        return {"path": str(path), "valid": is_speech_replacement_profile(path)}

    @router.get("/projects/status", response_model=WorkflowPlanResponseModel)
    def project_status(project: str) -> object:
        return json_value(
            app_services.audiobook.status(ProjectPaths.for_root(request_path(project)))
        )

    def narration_or_404(paths: ProjectPaths, narration_id: str):
        try:
            return narrations.get(paths, narration_id)
        except InputValidationError:
            raise HTTPException(
                status_code=404, detail="Narration not found."
            ) from None

    @router.get("/projects/narrations", response_model=NarrationListResponseModel)
    def list_narrations(project: str, source: str | None = None) -> dict[str, object]:
        paths = ProjectPaths.for_root(request_path(project))
        values = narrations.list(
            paths, source=request_path(source) if source is not None else None
        )
        return {"project": str(paths.root), "narrations": json_value(values)}

    @router.post(
        "/projects/narrations",
        response_model=NarrationResponseModel,
        status_code=201,
    )
    def create_narration(body: NarrationCreateRequestModel) -> object:
        item = narrations.create(
            ProjectPaths.for_root(request_path(body.project)),
            display_name=body.display_name,
            engine=body.engine,
            target=body.target,
            voice=body.voice,
            engine_options=dict(body.engine_options),
            speed=body.speed,
            output=request_path(body.output) if body.output is not None else None,
        )
        return json_value(item)

    @router.get(
        "/projects/narrations/{narration_id}", response_model=NarrationResponseModel
    )
    def narration_info(project: str, narration_id: str) -> object:
        paths = ProjectPaths.for_root(request_path(project))
        return json_value(narration_or_404(paths, narration_id))

    @router.delete(
        "/projects/narrations/{narration_id}",
        response_model=NarrationDeleteResponseModel,
    )
    def delete_narration(project: str, narration_id: str) -> dict[str, bool]:
        paths = ProjectPaths.for_root(request_path(project))
        narration_or_404(paths, narration_id)
        narrations.delete(paths, narration_id)
        return {"deleted": True}

    @router.post(
        "/previews",
        response_class=Response,
        responses={
            200: {
                "content": {
                    "audio/wav": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    )
    async def create_preview(body: PreviewRequestModel, request: Request) -> Response:
        if preview_service is None:
            raise HTTPException(
                status_code=503, detail="Preview synthesis is unavailable."
            )
        preview_request = PreviewRequest(
            project=request_path(body.project),
            narration_id=body.narration_id,
            text=body.text,
            chapter=body.chapter,
            paragraph=body.paragraph,
        )
        cancellation = preview_service.new_cancellation_token()
        task = asyncio.create_task(
            run_in_threadpool(
                preview_service.preview,
                preview_request,
                cancellation=cancellation,
            )
        )
        while not task.done():
            if await request.is_disconnected():
                cancellation.cancel()
            await asyncio.sleep(0.05)
        result = await task
        return Response(
            content=result.audio.wav,
            media_type="audio/wav",
            headers={
                "X-TTSForge-Narration-Id": result.narration_id,
                "X-TTSForge-Sample-Rate": str(result.audio.sample_rate),
                "X-TTSForge-Channels": str(result.audio.channels),
                "X-TTSForge-Duration-Seconds": str(result.audio.duration_seconds),
            },
        )

    @router.post(
        "/projects/narrations/{narration_id}/preflight",
        response_model=PreflightResponseModel,
    )
    def preflight_narration(project: str, narration_id: str) -> dict[str, object]:
        paths = ProjectPaths.for_root(request_path(project))
        narration_or_404(paths, narration_id)
        request, overrides = narrations.request_for_render(paths, narration_id)
        request = _request_for_import(
            request,
            imports_dir,
            state,
            claim=True,
            create_output_parent=True,
        )
        prepared = app_services.conversion.prepare(request, overrides)
        setup = prepared.resolved.preparation
        return {
            "project": str(setup.paths.root),
            "configuration_variant": setup.paths.variant_key,
            "reused_setup": setup.reused,
            "spacy_model": json_value(prepared.spacy_model),
            "request": json_value(prepared.resolved.request),
            "workflow": json_value(prepared.preflight.workflow),
        }

    @router.post(
        "/projects/narrations/{narration_id}/jobs",
        status_code=202,
        response_model=JobCreateResponseModel,
    )
    def create_narration_job(project: str, narration_id: str) -> dict[str, str]:
        paths = ProjectPaths.for_root(request_path(project))
        narration_or_404(paths, narration_id)
        request, overrides = narrations.request_for_render(paths, narration_id)
        request = _request_for_import(
            request,
            imports_dir,
            state,
            claim=True,
            create_output_parent=True,
        )
        record = jobs.submit(request, overrides, narration_id=narration_id)
        return {"id": record.id, "state": record.state.value}

    @router.get("/projects/variants", response_model=list[ProjectVariantResponseModel])
    def project_variants(project: str, source: str | None = None) -> object:
        return json_value(
            app_services.audiobook.list_variants(
                ProjectPaths.for_root(request_path(project)),
                source=request_path(source) if source is not None else None,
            )
        )

    @router.get("/projects/setup", response_model=ProjectSetupResponseModel)
    def project_setup(project: str, variant: str | None = None) -> dict[str, object]:
        paths = _project_paths(project, variant)
        saved = app_services.audiobook.load_saved_setup(paths)
        return {
            "project": str(paths.root),
            "variant": variant,
            "saved_setup": json_value(saved),
        }

    @router.get("/projects/info", response_model=ProjectInfoResponseModel)
    def project_info(project: str) -> dict[str, object]:
        paths = _project_paths(project)
        saved = app_services.audiobook.load_saved_setup(paths)
        workflow = app_services.audiobook.status(paths) if saved is not None else None
        variants = app_services.audiobook.list_variants(
            paths, source=saved.source if saved is not None else None
        )
        narration_views = narrations.list(
            paths, source=saved.source if saved is not None else None
        )
        return {
            "project": str(paths.root),
            "saved_setup": json_value(saved),
            "workflow": json_value(workflow),
            "variants": json_value(variants),
            "narrations": json_value(narration_views),
        }

    @router.get("/library/projects", response_model=LibraryProjectsResponseModel)
    def list_library_projects(root: str) -> dict[str, object]:
        library_root = request_path(root)
        records = jobs.list_jobs(limit=100)
        projects = [
            json_value(_with_job_activity(item, records))
            for item in library_service.list(library_root)
        ]
        return {"root": str(library_root), "projects": projects}

    @router.get(
        "/library/projects/{project_id}", response_model=ProjectSummaryResponseModel
    )
    def library_project(project_id: str) -> object:
        return json_value(
            _with_job_activity(
                library_service.get(project_id), jobs.list_jobs(limit=100)
            )
        )

    @router.get("/projects/metadata", response_model=AudiobookMetadataViewResponseModel)
    def project_metadata(project: str) -> object:
        return json_value(metadata_service.show(_project_paths(project)))

    @router.patch(
        "/projects/metadata", response_model=AudiobookMetadataViewResponseModel
    )
    def set_project_metadata(body: ProjectMetadataSetRequestModel) -> object:
        values = body.metadata.model_dump(exclude_unset=True)
        if "cover" in values and values["cover"] is not None:
            values["cover"] = request_path(values["cover"])
        updates = {key: value for key, value in values.items() if value is not None}
        return json_value(metadata_service.set(_project_paths(body.project), updates))

    @router.post(
        "/projects/metadata/validate", response_model=MetadataValidationResponseModel
    )
    def validate_project_metadata(body: ProjectPathRequestModel) -> object:
        return json_value(metadata_service.validate(_project_paths(body.project)))

    @router.get("/projects/chapters", response_model=ChapterListResponseModel)
    def project_chapters(project: str) -> dict[str, object]:
        paths = _project_paths(project)
        return {
            "project": str(paths.root),
            "chapters": json_value(chapter_service.status(paths)),
        }

    @router.post(
        "/projects/chapters/select", response_model=ChapterSelectionResponseModel
    )
    def select_project_chapters(body: ChapterSelectionRequestModel) -> object:
        return json_value(
            chapter_service.select(_project_paths(body.project), body.selection)
        )

    @router.post("/projects/qc", response_model=QcReportResponseModel)
    def project_qc(body: ProjectQcRequestModel) -> object:
        return json_value(
            qc_service.check(_project_paths(body.project), body.narration_id)
        )

    @router.post("/jobs", status_code=202, response_model=JobCreateResponseModel)
    def create_job(body: JobSubmissionModel) -> dict[str, str]:
        request = _request_for_import(
            application_request(body.request),
            imports_dir,
            state,
            claim=True,
            create_output_parent=True,
        )
        overrides = application_overrides(body.explicit_fields)
        record = jobs.submit(request, overrides)
        return {"id": record.id, "state": record.state.value}

    @router.get("/jobs", response_model=JobListResponseModel)
    def list_jobs(
        state: JobStateLiteral | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        before: str | None = None,
    ) -> dict[str, object]:
        try:
            records = jobs.list_jobs(
                state=JobState(state) if state is not None else None,
                limit=limit,
                before=before,
            )
        except KeyError:
            raise HTTPException(
                status_code=404, detail="Job cursor not found."
            ) from None
        return {"jobs": [_job_summary_view(record) for record in records]}

    @router.get("/jobs/{job_id}", response_model=JobStatusResponseModel)
    def job_status(job_id: str) -> dict[str, object]:
        return _job_status_view(_get_job_record(jobs, job_id))

    @router.post(
        "/jobs/{job_id}/retry",
        status_code=202,
        response_model=JobCreateResponseModel,
    )
    def retry_job(job_id: str) -> dict[str, str]:
        try:
            record = jobs.retry(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.") from None
        except InputValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except OperationConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        return {"id": record.id, "state": record.state.value}

    @router.get("/jobs/{job_id}/events", response_model=JobEventsPageResponseModel)
    def job_events(
        job_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        page = jobs.events(job_id, after=after)
        return {
            "first": page.first,
            "next": page.next,
            "truncated": page.truncated,
            "events": [
                {
                    "seq": event.sequence,
                    "timestamp": event.timestamp,
                    "event": event.event,
                }
                for event in page.events
            ],
        }

    @router.post("/jobs/{job_id}/cancel", response_model=JobStatusResponseModel)
    def cancel_job(job_id: str) -> dict[str, object]:
        try:
            record = jobs.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.") from None
        return _job_status_view(record)

    app.include_router(router)
    return app


def _project_paths(project: str, variant: str | None = None) -> ProjectPaths:
    root = request_path(project)
    if variant is None:
        return ProjectPaths.for_root(root)
    if variant in {"", ".", ".."} or "/" in variant or "\\" in variant:
        raise InputValidationError("Variant must be a single project variant key.")
    return ProjectPaths.for_variant(root, variant)


def _with_job_activity(
    summary: ProjectSummary, records: Sequence[JobRecord]
) -> ProjectSummary:
    project = summary.project.resolve()
    matching = tuple(
        record
        for record in records
        if record.project is not None and record.project.resolve() == project
    )
    active = next(
        (
            record
            for record in matching
            if record.state in {JobState.QUEUED, JobState.PREPARING, JobState.RUNNING}
        ),
        None,
    )
    timestamps = [summary.last_activity] if summary.last_activity is not None else []
    for record in matching:
        timestamps.extend(
            timestamp
            for timestamp in (record.created_at, record.started_at, record.finished_at)
            if timestamp is not None
        )
        if record.event_history:
            try:
                timestamps.append(
                    datetime.fromisoformat(record.event_history[-1].timestamp)
                )
            except ValueError:
                pass
    return replace(
        summary,
        active_job_id=active.id if active is not None else None,
        last_activity=max(timestamps) if timestamps else None,
    )


def _application_services() -> ApplicationServices:
    from ..readio_backend import ReadioBackend, create_readio

    backend = ReadioBackend(create_readio())
    audiobook = AudiobookApplicationService(backend)
    catalog = CatalogApplicationService(backend)
    conversion = ConversionCoordinator(audiobook, catalog)
    preview = PreviewApplicationService(
        NarrationApplicationService(audiobook, catalog), backend
    )
    return ApplicationServices(audiobook, catalog, conversion, preview)


def _get_job_record(job_manager: JobManager, job_id: str) -> JobRecord:
    try:
        return job_manager.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.") from None


def _job_summary_view(record: JobRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "state": record.state.value,
        "created_at": record.created_at.isoformat(),
        "started_at": (
            record.started_at.isoformat() if record.started_at is not None else None
        ),
        "finished_at": (
            record.finished_at.isoformat() if record.finished_at is not None else None
        ),
        "project": str(record.project) if record.project is not None else None,
        "output": str(record.output) if record.output is not None else None,
        "narration_id": record.narration_id,
        "retry_of": record.retry_of,
        "event_sequence": record.event_sequence,
    }


def _job_status_view(record: JobRecord) -> dict[str, object]:
    return {
        **_job_summary_view(record),
        "progress": json_value(record.progress),
        "result": json_value(record.result),
        "error": json_value(record.error),
    }


def _api_error_response(
    *,
    status: int,
    error_type: str,
    message: str,
    code: str,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "type": error_type,
                "message": message,
                "category": "request",
                "code": code,
                "stage": None,
                "package": None,
                "selector": None,
                "details": details or {},
            }
        },
    )


def _http_error_response(status: int) -> JSONResponse:
    errors = {
        401: (
            "AuthenticationError",
            "A valid bearer token is required.",
            "unauthorized",
        ),
        403: ("OriginDeniedError", "Origin is not allowed.", "origin_denied"),
        404: ("NotFoundError", "The requested resource was not found.", "not_found"),
        413: (
            "UploadTooLargeError",
            "Uploaded source exceeds the size limit.",
            "upload_too_large",
        ),
    }
    error_type, message, code = errors.get(
        status, ("HttpError", "The request could not be completed.", f"http_{status}")
    )
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return _api_error_response(
        status=status,
        error_type=error_type,
        message=message,
        code=code,
        details={"status_code": status} if status not in errors else {},
        headers=headers,
    )


def _error_response(error: Exception, status: int) -> JSONResponse:
    error_data = error_view(error).to_dict()
    if error_data["category"] is None:
        error_data["category"] = "request"
    if error_data["code"] is None and status == 400:
        error_data["code"] = "invalid_request"
    return JSONResponse(status_code=status, content={"error": error_data})


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_status() -> dict[str, object]:
    audioexport_version = _distribution_version("audioexport")
    packages = {
        "ttsforge": _distribution_version("ttsforge"),
        "readio": _distribution_version("readio"),
    }
    tools: dict[str, object] = {}
    problems: list[dict[str, str]] = []
    for name in ("ffmpeg", "ffprobe"):
        path = shutil.which(name)
        tools[name] = {"available": path is not None, "path": path}
        if path is None:
            problems.append(
                {
                    "code": f"{name}_missing",
                    "message": f"{name} is not installed or not on PATH.",
                }
            )

    if audioexport_version is None:
        problems.append(
            {
                "code": "audioexport_missing",
                "message": "The audioexport package is not installed.",
            }
        )
    if packages["readio"] is None:
        problems.append(
            {
                "code": "readio_missing",
                "message": "The Readio package is not installed.",
            }
        )

    return {
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "packages": packages,
        "audio": {
            "audioexport": {
                "available": audioexport_version is not None,
                "version": audioexport_version,
            },
            **tools,
        },
        "ready": not problems,
        "problems": problems,
    }


def cleanup_imports(
    imports_dir: Path, *, retention_days: int, now: datetime | None = None
) -> None:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    for directory in imports_dir.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        metadata = _read_source_metadata(directory)
        if metadata is None or metadata["claimed"] is True:
            continue
        created_at = _metadata_created_at(metadata)
        if created_at is not None and created_at < cutoff:
            shutil.rmtree(directory)


def _read_source_metadata(directory: Path) -> dict[str, object] | None:
    try:
        metadata = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    if metadata.get("source_id") != directory.name:
        return None
    if not isinstance(metadata.get("filename"), str):
        return None
    if not isinstance(metadata.get("created_at"), str):
        return None
    if not isinstance(metadata.get("claimed"), bool):
        return None
    if metadata.get("last_used_at") is not None and not isinstance(
        metadata.get("last_used_at"), str
    ):
        return None
    return metadata


def _metadata_created_at(metadata: dict[str, object]) -> datetime | None:
    value = metadata.get("created_at")
    if not isinstance(value, str):
        return None
    try:
        created_at = datetime.fromisoformat(value)
    except ValueError:
        return None
    if created_at.tzinfo is None:
        return None
    return created_at.astimezone(timezone.utc)


def _write_source_metadata(directory: Path, metadata: dict[str, object]) -> None:
    path = directory / "source.json"
    temporary = directory / f".source.{uuid.uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _source_import_directory(source: Path, imports_dir: Path) -> Path | None:
    try:
        parts = source.resolve().relative_to(imports_dir.resolve()).parts
    except (OSError, ValueError):
        return None
    if len(parts) != 2:
        return None
    source_id, filename = parts
    try:
        if str(uuid.UUID(source_id)) != source_id:
            return None
    except ValueError:
        return None
    directory = imports_dir / source_id
    if directory.is_symlink() or not directory.is_dir():
        return None
    metadata_path = directory / "source.json"
    if metadata_path.exists():
        metadata = _read_source_metadata(directory)
        if metadata is None or metadata["filename"] != filename:
            return None
    return directory


def _claim_source_import(source: Path, imports_dir: Path) -> None:
    directory = _source_import_directory(source, imports_dir)
    if directory is None:
        return
    metadata_path = directory / "source.json"
    metadata = _read_source_metadata(directory)
    if metadata is None:
        if metadata_path.exists():
            return
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "source_id": directory.name,
            "filename": source.name,
            "created_at": now,
            "claimed": False,
            "last_used_at": None,
        }
    elif metadata["filename"] != source.name:
        return
    metadata["claimed"] = True
    metadata["last_used_at"] = datetime.now(timezone.utc).isoformat()
    _write_source_metadata(directory, metadata)


def _source_import_record(
    source_id: str, imports_dir: Path
) -> tuple[Path, dict[str, object]] | None:
    try:
        if str(uuid.UUID(source_id)) != source_id:
            return None
    except ValueError:
        return None
    directory = imports_dir / source_id
    if directory.is_symlink() or not directory.is_dir():
        return None
    metadata = _read_source_metadata(directory)
    if metadata is None:
        return None
    filename = metadata["filename"]
    if not isinstance(filename, str) or not filename or "\\" in filename:
        return None
    if PurePosixPath(filename).name != filename:
        return None
    if _metadata_created_at(metadata) is None:
        return None
    return directory, metadata


def _source_import_view(
    directory: Path, metadata: dict[str, object], retention_days: int
) -> dict[str, object]:
    claimed = bool(metadata["claimed"])
    return {
        "source_id": metadata["source_id"],
        "path": str(directory / str(metadata["filename"])),
        "managed": True,
        "temporary": not claimed,
        "retention_days": retention_days,
        "claimed": claimed,
        "created_at": metadata["created_at"],
        "last_used_at": metadata["last_used_at"],
    }


def _request_for_import(
    request: AudiobookRequest,
    imports_dir: Path,
    state_dir: Path,
    *,
    claim: bool = False,
    create_output_parent: bool = False,
) -> AudiobookRequest:
    directory = _source_import_directory(request.source, imports_dir)
    if directory is None:
        return request
    source_id = directory.name
    default_output = request.output is None
    output = request.output or (
        state_dir / "outputs" / source_id / request.source.with_suffix(".m4b").name
    )
    selected = replace(
        request,
        project=request.project or state_dir / "projects" / source_id,
        output=output,
    )
    if claim:
        _claim_source_import(request.source, imports_dir)
    if create_output_parent and default_output:
        output.parent.mkdir(parents=True, exist_ok=True)
    return selected


async def _import_source(
    upload: UploadFile,
    services: ApplicationServices,
    imports_dir: Path,
    *,
    max_upload_bytes: int,
    retention_days: int,
) -> dict[str, object]:
    source_id = str(uuid.uuid4())
    directory = imports_dir / source_id
    directory.mkdir(mode=0o700)
    filename = _safe_filename(upload.filename)
    path = directory / filename
    created_at = datetime.now(timezone.utc).isoformat()
    metadata: dict[str, object] = {
        "source_id": source_id,
        "filename": filename,
        "created_at": created_at,
        "claimed": False,
        "last_used_at": None,
    }
    _write_source_metadata(directory, metadata)
    size = 0
    try:
        with path.open("xb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Uploaded source exceeds the size limit.",
                    )
                target.write(chunk)
        inspection = await run_in_threadpool(services.audiobook.inspect_book, path)
        if inspection.kind != "book":
            raise InputValidationError(
                "Uploaded source is not a supported audiobook book."
            )
        return {
            **_source_import_view(directory, metadata, retention_days),
            "inspection": json_value(inspection),
        }
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await upload.close()


def _safe_filename(filename: str | None) -> str:
    name = PurePosixPath((filename or "source.epub").replace("\\", "/")).name
    name = re.sub(r"[^\w. -]", "_", name, flags=re.UNICODE).strip(" .")
    if name in {"", ".", ".."}:
        return "source.epub"
    return name[:180]
