"""Versioned local API backed only by TTSForge application services."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import platform
import re
import shutil
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response
from starlette.types import ASGIApp

from ..application import (
    AudiobookApplicationService,
    BlockedWorkflowError,
    CatalogApplicationService,
    CatalogSelectionError,
    ConversionCoordinator,
    InputValidationError,
    OperationConflictError,
    ProjectPaths,
    WorkflowFailureError,
    error_view,
    json_value,
)
from .auth import require_bearer_token
from .jobs import JobManager, JobRecord
from .models import (
    JobSubmissionModel,
    SourceInspectRequest,
    SpacyEnsureRequest,
)
from .requests import application_overrides, application_request

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


class OriginPolicyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, allowed_origins: Sequence[str]) -> None:
        super().__init__(app)
        self._allowed_origins = frozenset(allowed_origins)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")
        if origin and not self._allowed(request, origin):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "type": "OriginDeniedError",
                        "message": "Origin is not allowed.",
                    }
                },
            )
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
    jobs = job_manager if job_manager is not None else JobManager(debug=debug)
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
        allow_methods=["GET", "POST"],
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

    @app.get("/api/v1/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_bearer_token)])

    @router.get("/system")
    def system() -> dict[str, object]:
        return {
            "api_version": _API_VERSION,
            "ttsforge_version": _distribution_version("ttsforge"),
            "python_version": platform.python_version(),
            "capabilities": {"jobs": True, "cancel": True, "source_upload": True},
        }

    @router.get("/system/runtime")
    def system_runtime() -> dict[str, object]:
        return runtime_status()

    @router.post("/sources/inspect")
    def inspect_source(body: SourceInspectRequest) -> object:
        path = Path(body.path).expanduser()
        if not path.is_file() or not os.access(path, os.R_OK):
            raise InputValidationError(f"Source must be a readable file: {path}.")
        inspection = app_services.audiobook.inspect_book(path)
        if inspection.kind != "book":
            raise InputValidationError("Source is not a supported audiobook book.")
        return json_value(inspection)

    @router.post("/sources/import")
    async def import_source(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        return await _import_source(
            file,
            app_services,
            imports_dir,
            max_upload_bytes=max_upload_bytes,
        )

    @router.get("/catalog/engines")
    def engines() -> object:
        return json_value(app_services.catalog.engines())

    @router.get("/catalog/targets")
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

    @router.get("/catalog/voices")
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
                default_voice=None if selected is None else selected.default_voice,
            )
        )

    @router.get("/catalog/engine-options")
    def engine_options(engine: str, target: str | None = None) -> object:
        return json_value(app_services.catalog.engine_options(engine, target=target))

    @router.get("/resources/spacy")
    def spacy_models(language: str) -> object:
        return json_value(app_services.catalog.spacy_models(language))

    @router.post("/resources/spacy/ensure")
    def ensure_spacy_model(body: SpacyEnsureRequest) -> object:
        return json_value(
            app_services.catalog.ensure_spacy_model(
                body.language, body.tier, offline=body.offline
            )
        )

    @router.get("/projects/status")
    def project_status(project: str) -> object:
        return json_value(
            app_services.audiobook.status(ProjectPaths.for_root(Path(project)))
        )

    @router.get("/projects/variants")
    def project_variants(project: str, source: str | None = None) -> object:
        return json_value(
            app_services.audiobook.list_variants(
                ProjectPaths.for_root(Path(project)),
                source=Path(source) if source is not None else None,
            )
        )

    @router.post("/jobs", status_code=202)
    def create_job(body: JobSubmissionModel) -> dict[str, str]:
        request = application_request(body.request)
        overrides = application_overrides(body.explicit_fields)
        record = jobs.submit(request, overrides)
        return {"id": record.id, "state": record.state.value}

    @router.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, object]:
        return _job_status_view(_get_job_record(jobs, job_id))

    @router.get("/jobs/{job_id}/events")
    def job_events(
        job_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        page = jobs.events(job_id, after=after)
        return {
            "next": page.next,
            "events": [
                {
                    "seq": event.sequence,
                    "timestamp": event.timestamp,
                    "event": event.event,
                }
                for event in page.events
            ],
        }

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, object]:
        try:
            record = jobs.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.") from None
        return _job_status_view(record)

    app.include_router(router)
    return app


def _application_services() -> ApplicationServices:
    from ..readio_backend import ReadioBackend, create_readio

    backend = ReadioBackend(create_readio())
    audiobook = AudiobookApplicationService(backend)
    catalog = CatalogApplicationService(backend)
    return ApplicationServices(
        audiobook, catalog, ConversionCoordinator(audiobook, catalog)
    )


def _get_job_record(job_manager: JobManager, job_id: str) -> JobRecord:
    try:
        return job_manager.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.") from None


def _job_status_view(record: JobRecord) -> dict[str, object]:
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
        "progress": json_value(record.progress),
        "result": json_value(record.result),
        "error": json_value(record.error),
        "event_sequence": record.event_sequence,
    }


def _error_response(error: Exception, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": json_value(error_view(error))}
    )


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_status() -> dict[str, object]:
    audioexport_version = _distribution_version("audioexport")
    tools: dict[str, object] = {}
    for name in ("ffmpeg", "ffprobe"):
        path = shutil.which(name)
        tools[name] = {"available": path is not None, "path": path}
    return {
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "packages": {
            "ttsforge": _distribution_version("ttsforge"),
            "readio": _distribution_version("readio"),
        },
        "audio": {
            "audioexport": {
                "available": audioexport_version is not None,
                "version": audioexport_version,
            },
            **tools,
        },
    }


def cleanup_imports(
    imports_dir: Path, *, retention_days: int, now: datetime | None = None
) -> None:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    for directory in imports_dir.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        modified = datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            shutil.rmtree(directory)


async def _import_source(
    upload: UploadFile,
    services: ApplicationServices,
    imports_dir: Path,
    *,
    max_upload_bytes: int,
) -> dict[str, object]:
    source_id = str(uuid.uuid4())
    directory = imports_dir / source_id
    directory.mkdir(mode=0o700)
    filename = _safe_filename(upload.filename)
    path = directory / filename
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
            "source_id": source_id,
            "path": str(path),
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
