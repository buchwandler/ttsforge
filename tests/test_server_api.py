from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient

from ttsforge.application.catalog import (
    EngineChoiceView,
    EngineOptionView,
    TargetChoiceView,
    VoiceChoiceView,
)
from ttsforge.application.library import ProjectSummary
from ttsforge.application.models import (
    AudiobookCapabilitiesView,
    AudiobookRequest,
    BookChapterView,
    BookInspectionView,
    InputOverrides,
    ProjectPaths,
    ProjectVariantView,
    SetupOrigins,
    SetupPreparation,
    SpacyModelView,
    WorkflowPlanView,
)
from ttsforge.server.app import (
    _with_job_activity,
    _write_source_metadata,
    cleanup_imports,
    create_app,
)
from ttsforge.server.jobs import JobState


class FakeAudiobook:
    def __init__(self) -> None:
        self.inspected: list[Path] = []
        self.last_project = None
        self.last_source = None
        self.saved_setups: dict[tuple[Path, str | None], AudiobookRequest] = {}
        self.preparation_args = None
        self.save_calls = 0

    def inspect_book(self, path: Path) -> BookInspectionView:
        self.inspected.append(path)
        kind = "book" if path.suffix == ".epub" else "unsupported"
        return BookInspectionView(
            source=path,
            kind=kind,
            title="Book title" if kind == "book" else None,
            author=None,
            language="en-US" if kind == "book" else None,
            chapters=(BookChapterView(1, "Chapter one"),) if kind == "book" else (),
        )

    def capabilities(self) -> AudiobookCapabilitiesView:
        return AudiobookCapabilitiesView(
            source_inspection=True,
            synthesis_preview=True,
            m4b_export=False,
            persistent_workspace=True,
            available_engines=("kokoro",),
            warnings=("M4B unavailable",),
        )

    def prepare_setup(self, request, overrides, *, interactive: bool = True):
        self.preparation_args = (request, overrides, interactive)
        inspection = self.inspect_book(request.source)
        paths = ProjectPaths.for_source(request.source, request.project)
        resolved = replace(
            request,
            project=paths.root,
            chapters=request.chapters or "all",
            output=request.output or request.source.with_suffix(".m4b"),
            language=request.language or inspection.language,
        )
        origins = SetupOrigins(
            explicit=overrides.fields,
            derived=frozenset({"chapters", "output", "language"}),
        )
        return SetupPreparation(paths, inspection, resolved, origins, reused=False)

    def save_setup(self, preparation, request=None):
        self.save_calls += 1

    def load_saved_setup(self, paths):
        self.last_project = paths
        return self.saved_setups.get((paths.root, paths.variant_key))

    def status(self, paths) -> WorkflowPlanView:
        self.last_project = paths
        return WorkflowPlanView(
            source=Path("/books/book.epub"),
            workspace=paths.root,
            workspace_mode="modern",
            output=Path("/books/book.m4b"),
            steps=(),
        )

    def list_variants(self, paths, *, source: Path | None = None):
        self.last_project = paths
        self.last_source = source
        return (ProjectVariantView("kokoro-en-voice-a"),)


class FakeCatalog:
    def __init__(self) -> None:
        self.target_calls = []
        self.voice_default = None
        self.spacy_args = None

    def engines(self):
        return (EngineChoiceView("kokoro", "1.0", True, True, ("voices",)),)

    def targets(self, **kwargs):
        self.target_calls.append(kwargs)
        return (
            TargetChoiceView(
                id="target-a",
                languages=("en-US",),
                status="available",
                runtime_available=True,
                default_voice="voice-a",
                voice_count=1,
                qualities=(),
                voice_mode="named",
                sample_rate=24000,
                features=("voices",),
                reference_only=False,
            ),
        )

    def voices(self, **kwargs):
        self.voice_default = kwargs.get("default_voice")
        return (
            VoiceChoiceView(
                id="voice-a",
                language="en-US",
                locale="en-US",
                language_label="English",
                gender="female",
                default=True,
                runtime_available=True,
            ),
        )

    def engine_options(self, engine: str, *, target: str | None = None):
        return (
            EngineOptionView(
                "quality",
                "string",
                False,
                "standard",
                ("standard", "high"),
                None,
                None,
                "Synthesis quality",
                True,
                False,
            ),
        )

    def spacy_models(self, language: str):
        return (SpacyModelView(language, "lg", "en_core_web_lg", True, "3.8", "3.8.0"),)

    def ensure_spacy_model(self, language: str, tier: str, *, offline: bool = False):
        self.spacy_args = (language, tier, offline)
        return SpacyModelView(language, tier, "en_core_web_lg", True, "3.8", "3.8.0")


class FakeConversion:
    def __init__(self, prepared) -> None:
        self.prepared = prepared
        self.prepare_args = None
        self.execute_calls = 0

    def prepare(self, request, overrides):
        self.prepare_args = (request, overrides)
        return (
            self.prepared(request, overrides)
            if callable(self.prepared)
            else self.prepared
        )

    def execute(self, prepared, *, on_progress=None):
        self.execute_calls += 1
        raise AssertionError("HTTP preflight must not execute rendering")


def make_client(
    tmp_path: Path,
    *,
    max_upload_bytes: int = 1024,
    allowed_origins: tuple[str, ...] = (),
    conversion: object | None = None,
):
    audiobook = FakeAudiobook()
    catalog = FakeCatalog()
    services = SimpleNamespace(
        audiobook=audiobook, catalog=catalog, conversion=conversion
    )
    app = create_app(
        token="secret-token",
        state_dir=tmp_path / "state",
        services=services,
        max_upload_bytes=max_upload_bytes,
        allowed_origins=allowed_origins,
    )
    return TestClient(app), audiobook, catalog


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer secret-token"}


def test_health_is_public_and_other_endpoints_require_bearer(
    tmp_path: Path,
) -> None:
    client, _, _ = make_client(tmp_path)

    assert client.get("/api/v1/health").json() == {"ok": True}
    assert client.get("/api/v1/system").status_code == 401
    assert (
        client.get(
            "/api/v1/system", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/system", headers=auth_headers()).status_code == 200


def test_origin_policy_accepts_same_origin_and_explicit_allowlist(
    tmp_path: Path,
) -> None:
    client, _, _ = make_client(tmp_path, allowed_origins=("http://localhost:3000",))

    allowed = client.get(
        "/api/v1/system",
        headers={**auth_headers(), "Origin": "http://localhost:3000"},
    )
    same_origin = client.get(
        "/api/v1/system",
        headers={**auth_headers(), "Origin": "http://testserver"},
    )
    denied = client.get(
        "/api/v1/system",
        headers={**auth_headers(), "Origin": "https://untrusted.example"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert same_origin.status_code == 200
    assert denied.status_code == 403


def test_wildcard_origins_are_rejected(tmp_path: Path) -> None:
    services = SimpleNamespace(audiobook=None, catalog=None, conversion=None)

    with pytest.raises(ValueError, match="Wildcard origins"):
        create_app(
            token="secret-token",
            state_dir=tmp_path / "state",
            services=services,
            allowed_origins=("*",),
        )


def test_source_inspection_accepts_only_readable_supported_files(
    tmp_path: Path,
) -> None:
    client, audiobook, _ = make_client(tmp_path)
    book = tmp_path / "book.epub"
    book.write_bytes(b"book")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a book")

    response = client.post(
        "/api/v1/sources/inspect",
        headers=auth_headers(),
        json={"path": str(book)},
    )
    unsupported_response = client.post(
        "/api/v1/sources/inspect",
        headers=auth_headers(),
        json={"path": str(unsupported)},
    )
    directory_response = client.post(
        "/api/v1/sources/inspect",
        headers=auth_headers(),
        json={"path": str(tmp_path)},
    )

    assert response.status_code == 200
    assert response.json()["source"] == str(book)
    assert unsupported_response.status_code == 400
    assert directory_response.status_code == 400
    assert audiobook.inspected == [book, unsupported]


def test_upload_sanitizes_filename_and_stores_under_unique_import_directory(
    tmp_path: Path,
) -> None:
    client, audiobook, _ = make_client(tmp_path)

    response = client.post(
        "/api/v1/sources/import",
        headers=auth_headers(),
        files={"file": ("../../books/book.epub", b"book-data", "application/epub+zip")},
    )

    assert response.status_code == 200
    imported_view = response.json()
    imported = Path(imported_view["path"])
    source_id = imported_view["source_id"]
    assert imported.name == "book.epub"
    assert imported.parent.parent == tmp_path / "state" / "imports"
    assert imported.read_bytes() == b"book-data"
    assert audiobook.inspected == [imported]
    assert imported_view["managed"] is True
    assert imported_view["temporary"] is True
    assert imported_view["retention_days"] == 30
    assert imported_view["claimed"] is False
    assert imported_view["last_used_at"] is None

    status = client.get(f"/api/v1/sources/imports/{source_id}", headers=auth_headers())
    assert status.status_code == 200
    assert status.json()["path"] == str(imported)
    assert status.json()["temporary"] is True

    deleted = client.delete(
        f"/api/v1/sources/imports/{source_id}", headers=auth_headers()
    )
    assert deleted.json() == {"source_id": source_id, "deleted": True}
    assert not imported.parent.exists()


def test_upload_size_limit_removes_partial_import(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, max_upload_bytes=4)

    response = client.post(
        "/api/v1/sources/import",
        headers=auth_headers(),
        files={"file": ("book.epub", b"12345", "application/epub+zip")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
    assert list((tmp_path / "state" / "imports").iterdir()) == []


def test_catalog_and_spacy_endpoints_return_application_views(
    tmp_path: Path,
) -> None:
    client, _, catalog = make_client(tmp_path)
    headers = auth_headers()

    engines = client.get("/api/v1/catalog/engines", headers=headers)
    targets = client.get(
        "/api/v1/catalog/targets?engine=kokoro&language=en-US&offline=true",
        headers=headers,
    )
    voices = client.get(
        "/api/v1/catalog/voices?engine=kokoro&target=target-a&language=en-US",
        headers=headers,
    )
    options = client.get(
        "/api/v1/catalog/engine-options?engine=kokoro&target=target-a",
        headers=headers,
    )
    spacy = client.get("/api/v1/resources/spacy?language=en-US", headers=headers)
    ensured = client.post(
        "/api/v1/resources/spacy/ensure",
        headers=headers,
        json={"language": "en-US", "tier": "lg", "offline": True},
    )

    assert engines.json()[0]["id"] == "kokoro"
    assert targets.json()[0]["default_voice"] == "voice-a"
    assert catalog.target_calls[0] == {
        "engine": "kokoro",
        "language": "en-US",
        "offline": True,
        "refresh": False,
    }
    assert voices.json()[0]["default"] is True
    assert catalog.voice_default is None
    assert options.json()[0]["identity_affecting"] is True
    assert spacy.json()[0]["model"] == "en_core_web_lg"
    assert ensured.json()["installed"] is True
    assert catalog.spacy_args == ("en-US", "lg", True)


def test_catalog_voice_rejects_unknown_target(tmp_path: Path) -> None:
    client, _, catalog = make_client(tmp_path)

    response = client.get(
        "/api/v1/catalog/voices?engine=kokoro&target=missing",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert catalog.voice_default is None


def test_project_status_and_variants_delegate_to_application_service(
    tmp_path: Path,
) -> None:
    client, audiobook, _ = make_client(tmp_path)
    project = tmp_path / "book.ttsforge"
    source = tmp_path / "book.epub"

    status = client.get(
        "/api/v1/projects/status",
        params={"project": str(project)},
        headers=auth_headers(),
    )
    variants = client.get(
        "/api/v1/projects/variants",
        params={"project": str(project), "source": str(source)},
        headers=auth_headers(),
    )

    assert status.json()["workspace"] == str(project)
    assert variants.json()[0]["variant_key"] == "kokoro-en-voice-a"
    assert audiobook.last_project.root == project
    assert audiobook.last_source == source


def test_project_narration_routes_expose_user_facing_ids_and_names(
    tmp_path: Path,
) -> None:
    client, _, _ = make_client(tmp_path)
    project = tmp_path / "book.ttsforge"
    headers = auth_headers()

    response = client.get(
        "/api/v1/projects/narrations",
        params={"project": str(project)},
        headers=headers,
    )
    detail = client.get(
        "/api/v1/projects/narrations/kokoro-en-voice-a",
        params={"project": str(project)},
        headers=headers,
    )
    missing = client.get(
        "/api/v1/projects/narrations/missing",
        params={"project": str(project)},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["narrations"][0]["id"] == "kokoro-en-voice-a"
    assert response.json()["narrations"][0]["display_name"] == "Additional narration"
    assert detail.json()["primary"] is False
    assert missing.status_code == 404


def test_runtime_endpoint_exposes_only_normalized_package_and_tool_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ttsforge.server import app as server_app

    client, _, _ = make_client(tmp_path)
    versions = {"ttsforge": "0.5.0", "readio": "0.6.7", "audioexport": "0.1.8"}
    monkeypatch.setattr(server_app, "_distribution_version", versions.get)
    monkeypatch.setattr(
        server_app.shutil,
        "which",
        lambda name: f"/runtime/bin/{name}" if name == "ffmpeg" else None,
    )

    response = client.get("/api/v1/system/runtime", headers=auth_headers())
    runtime = response.json()

    assert response.status_code == 200
    assert runtime["packages"] == {"ttsforge": "0.5.0", "readio": "0.6.7"}
    assert runtime["audio"]["audioexport"] == {"available": True, "version": "0.1.8"}
    assert runtime["audio"]["ffmpeg"] == {
        "available": True,
        "path": "/runtime/bin/ffmpeg",
    }
    assert runtime["audio"]["ffprobe"] == {"available": False, "path": None}
    assert "environment" not in runtime
    assert runtime["ready"] is False
    assert runtime["problems"] == [
        {
            "code": "ffprobe_missing",
            "message": "ffprobe is not installed or not on PATH.",
        }
    ]


def test_import_cleanup_removes_only_expired_directories(tmp_path: Path) -> None:
    imports = tmp_path / "imports"
    old = imports / "old"
    recent = imports / "recent"
    old.mkdir(parents=True)
    recent.mkdir()
    now = datetime(2025, 1, 31, tzinfo=timezone.utc)
    old_created = datetime(2024, 12, 1, tzinfo=timezone.utc)
    recent_created = datetime(2025, 1, 20, tzinfo=timezone.utc)
    for directory, created_at in ((old, old_created), (recent, recent_created)):
        _write_source_metadata(
            directory,
            {
                "source_id": directory.name,
                "filename": "book.epub",
                "created_at": created_at.isoformat(),
                "claimed": False,
                "last_used_at": None,
            },
        )

    cleanup_imports(imports, retention_days=30, now=now)

    assert not old.exists()
    assert recent.exists()


def test_import_cleanup_preserves_claimed_and_untracked_directories(
    tmp_path: Path,
) -> None:
    imports = tmp_path / "imports"
    claimed = imports / "claimed"
    expired = imports / "expired"
    untracked = imports / "untracked"
    claimed.mkdir(parents=True)
    expired.mkdir()
    untracked.mkdir()
    created_at = datetime(2024, 12, 1, tzinfo=timezone.utc).isoformat()
    for directory, is_claimed in ((claimed, True), (expired, False)):
        _write_source_metadata(
            directory,
            {
                "source_id": directory.name,
                "filename": "book.epub",
                "created_at": created_at,
                "claimed": is_claimed,
                "last_used_at": created_at if is_claimed else None,
            },
        )

    cleanup_imports(
        imports, retention_days=30, now=datetime(2025, 1, 31, tzinfo=timezone.utc)
    )

    assert claimed.exists()
    assert not expired.exists()
    assert untracked.exists()


def test_import_preflight_claims_source_and_uses_durable_defaults(
    tmp_path: Path,
) -> None:
    def prepare(request, overrides):
        paths = ProjectPaths.for_root(request.project)
        workflow = WorkflowPlanView(
            source=request.source,
            workspace=request.project,
            workspace_mode="modern",
            output=request.output,
            steps=(),
        )
        return SimpleNamespace(
            resolved=SimpleNamespace(
                preparation=SimpleNamespace(paths=paths, reused=False), request=request
            ),
            spacy_model=None,
            preflight=SimpleNamespace(workflow=workflow),
        )

    conversion = FakeConversion(prepare)
    client, _, _ = make_client(tmp_path, conversion=conversion)
    imported_response = client.post(
        "/api/v1/sources/import",
        headers=auth_headers(),
        files={"file": ("book.epub", b"book-data", "application/epub+zip")},
    )
    imported = imported_response.json()
    source = Path(imported["path"])
    source_id = imported["source_id"]
    request_body = {"request": {"source": str(source)}}

    resolved = client.post(
        "/api/v1/setup/resolve",
        headers=auth_headers(),
        json=request_body,
    )
    state_dir = tmp_path / "state"
    project = state_dir / "projects" / source_id
    output = state_dir / "outputs" / source_id / "book.m4b"
    assert resolved.status_code == 200
    assert resolved.json()["project"] == str(project)
    assert resolved.json()["request"]["output"] == str(output)
    assert resolved.json()["reused_setup"] is False

    before_preflight = client.get(
        f"/api/v1/sources/imports/{source_id}", headers=auth_headers()
    ).json()
    assert before_preflight["claimed"] is False

    preflight = client.post(
        "/api/v1/conversions/preflight",
        headers=auth_headers(),
        json=request_body,
    )
    assert preflight.status_code == 200
    assert conversion.prepare_args[0].project == project
    assert conversion.prepare_args[0].output == output
    assert output.parent.is_dir()
    claimed = client.get(
        f"/api/v1/sources/imports/{source_id}", headers=auth_headers()
    ).json()
    assert claimed["claimed"] is True
    assert claimed["temporary"] is False
    assert claimed["last_used_at"] is not None
    assert conversion.execute_calls == 0

    _write_source_metadata(
        source.parent,
        {
            "source_id": source_id,
            "filename": source.name,
            "created_at": "2024-12-01T00:00:00+00:00",
            "claimed": True,
            "last_used_at": claimed["last_used_at"],
        },
    )
    cleanup_imports(
        state_dir / "imports",
        retention_days=30,
        now=datetime(2025, 1, 31, tzinfo=timezone.utc),
    )
    assert source.exists()

    deleted = client.delete(
        f"/api/v1/sources/imports/{source_id}", headers=auth_headers()
    )
    assert deleted.status_code == 200
    assert not source.parent.exists()


def test_request_validation_errors_use_safe_api_envelope(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    responses = [
        client.post(
            "/api/v1/sources/inspect",
            headers=auth_headers(),
            json={"path": 123},
        ),
        client.post(
            "/api/v1/sources/inspect",
            headers=auth_headers(),
            json={"path": "/books/book.epub", "unexpected": True},
        ),
        client.get("/api/v1/catalog/targets", headers=auth_headers()),
        client.get(
            "/api/v1/catalog/targets?engine=kokoro&offline=invalid",
            headers=auth_headers(),
        ),
    ]

    for response in responses:
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["type"] == "RequestValidationError"
        assert error["category"] == "request"
        assert error["code"] == "invalid_request"
        assert error["details"]["issues"]
        assert all(
            set(issue) == {"location", "type", "message"}
            for issue in error["details"]["issues"]
        )
        assert '"input":' not in response.text
        assert "123" not in response.text


def test_framework_http_errors_use_safe_api_envelope(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    unauthorized = client.get("/api/v1/system")
    denied = client.get(
        "/api/v1/system",
        headers={**auth_headers(), "Origin": "https://untrusted.example"},
    )
    missing = client.get("/api/v1/jobs/missing", headers=auth_headers())

    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert unauthorized.json()["error"]["code"] == "unauthorized"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "origin_denied"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_explicit_fields_validation_uses_api_error_envelope(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    body = {"request": {"source": "/books/book.epub"}}
    responses = [
        client.post(
            "/api/v1/jobs",
            headers=auth_headers(),
            json={**body, "explicit_fields": ["source", "source"]},
        ),
        client.post(
            "/api/v1/jobs",
            headers=auth_headers(),
            json={**body, "explicit_fields": ["unknown"]},
        ),
    ]

    for response in responses:
        assert response.status_code == 400
        assert "error" in response.json()
        assert response.json()["error"]["category"] == "request"


def test_request_paths_expand_home_and_preserve_relative_unicode_and_windows_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ttsforge.server.requests import request_path

    monkeypatch.setenv("HOME", str(tmp_path))
    assert request_path("~/books/ü book.epub") == tmp_path / "books" / "ü book.epub"
    assert request_path("relative folder/ü book.epub") == Path(
        "relative folder/ü book.epub"
    )
    windows_path = r"C:\books\ü book.epub"
    assert request_path(windows_path) == Path(windows_path)


def test_project_query_paths_use_shared_expansion_and_preserve_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client, audiobook, _ = make_client(tmp_path)
    status = client.get(
        "/api/v1/projects/status",
        params={"project": "~/books/book.ttsforge"},
        headers=auth_headers(),
    )

    assert status.status_code == 200
    assert audiobook.last_project.root == tmp_path / "books" / "book.ttsforge"

    variants = client.get(
        "/api/v1/projects/variants",
        params={
            "project": "relative folder/book.ttsforge",
            "source": "relative folder/ü book.epub",
        },
        headers=auth_headers(),
    )

    assert variants.status_code == 200
    assert audiobook.last_project.root == Path("relative folder/book.ttsforge")
    assert audiobook.last_source == Path("relative folder/ü book.epub")


def test_setup_resolve_returns_application_resolution_without_saving(
    tmp_path: Path,
) -> None:
    client, audiobook, _ = make_client(tmp_path)
    source = tmp_path / "book.epub"
    response = client.post(
        "/api/v1/setup/resolve",
        headers=auth_headers(),
        json={
            "request": {"source": str(source), "engine": "kokoro"},
            "explicit_fields": ["engine"],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["project"] == str(source.with_suffix(".ttsforge"))
    assert result["configuration_variant"] is None
    assert result["reused_setup"] is False
    assert result["inspection"]["chapters"] == [
        {"number": 1, "title": "Chapter one", "source_id": None, "char_count": None}
    ]
    assert result["request"]["chapters"] == "all"
    assert result["request"]["output"] == str(source.with_suffix(".m4b"))
    assert result["request"]["language"] == "en-US"
    assert result["origins"]["explicit"] == ["engine"]
    assert audiobook.preparation_args[1] == InputOverrides(frozenset({"engine"}))
    assert audiobook.preparation_args[2] is False
    assert audiobook.save_calls == 0


def test_conversion_preflight_returns_prepared_workflow_without_execution(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    project = tmp_path / "book.ttsforge"
    output = tmp_path / "book.m4b"
    request = AudiobookRequest(
        source=source,
        project=project,
        chapters="1",
        output=output,
        language="en-US",
        engine="kokoro",
        target="target-a",
        voice="voice-a",
        spacy="lg",
    )
    inspection = BookInspectionView(
        source,
        "book",
        "Book title",
        "Author",
        "en-US",
        (BookChapterView(1, "Chapter one"),),
    )
    paths = ProjectPaths.for_variant(project, "kokoro-en-voice-a")
    preparation = SetupPreparation(
        paths,
        inspection,
        request,
        SetupOrigins(explicit=frozenset({"engine"})),
        reused=True,
    )
    workflow = WorkflowPlanView(
        source=source,
        workspace=project,
        workspace_mode="modern",
        output=output,
        steps=(),
        warnings=("Prepared warning",),
        variant="kokoro-en-voice-a",
    )
    prepared = SimpleNamespace(
        resolved=SimpleNamespace(preparation=preparation, request=request),
        spacy_model=SpacyModelView(
            "en-US", "lg", "en_core_web_lg", True, "3.8", "3.8.0"
        ),
        preflight=SimpleNamespace(workflow=workflow),
    )
    conversion = FakeConversion(prepared)
    client, _, _ = make_client(tmp_path, conversion=conversion)
    response = client.post(
        "/api/v1/conversions/preflight",
        headers=auth_headers(),
        json={
            "request": {
                "source": str(source),
                "project": str(project),
                "chapters": "1",
                "output": str(output),
                "language": "en-US",
                "engine": "kokoro",
                "target": "target-a",
                "voice": "voice-a",
                "spacy": "lg",
            },
            "explicit_fields": ["engine"],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["project"] == str(project)
    assert result["configuration_variant"] == "kokoro-en-voice-a"
    assert result["reused_setup"] is True
    assert result["spacy_model"]["installed"] is True
    assert result["request"]["output"] == str(output)
    assert result["workflow"]["warnings"] == ["Prepared warning"]
    assert conversion.prepare_args[0].source == source
    assert conversion.prepare_args[1] == InputOverrides(frozenset({"engine"}))
    assert conversion.execute_calls == 0


def test_project_setup_and_info_load_base_variant_and_workflow(
    tmp_path: Path,
) -> None:
    client, audiobook, _ = make_client(tmp_path)
    project = tmp_path / "book.ttsforge"
    saved = AudiobookRequest(
        source=tmp_path / "book.epub",
        project=project,
        output=tmp_path / "book.m4b",
        language="en-US",
        engine="kokoro",
        target="target-a",
        voice="voice-a",
    )
    variant_saved = replace(saved, voice="voice-b")
    audiobook.saved_setups[(project, None)] = saved
    audiobook.saved_setups[(project, "kokoro-en-voice-b")] = variant_saved

    base = client.get(
        "/api/v1/projects/setup",
        params={"project": str(project)},
        headers=auth_headers(),
    )
    variant = client.get(
        "/api/v1/projects/setup",
        params={"project": str(project), "variant": "kokoro-en-voice-b"},
        headers=auth_headers(),
    )
    info = client.get(
        "/api/v1/projects/info",
        params={"project": str(project)},
        headers=auth_headers(),
    )

    assert base.json()["saved_setup"]["voice"] == "voice-a"
    assert base.json()["variant"] is None
    assert variant.json()["saved_setup"]["voice"] == "voice-b"
    assert variant.json()["variant"] == "kokoro-en-voice-b"
    assert info.json()["saved_setup"]["engine"] == "kokoro"
    assert info.json()["workflow"]["workspace"] == str(project)
    assert info.json()["variants"][0]["variant_key"] == "kokoro-en-voice-a"
    assert audiobook.last_source == saved.source


def test_project_setup_rejects_variant_path_traversal(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    response = client.get(
        "/api/v1/projects/setup",
        params={"project": str(tmp_path / "project"), "variant": "../outside"},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_system_advertises_setup_and_preflight_capabilities(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    capabilities = client.get("/api/v1/system", headers=auth_headers()).json()[
        "capabilities"
    ]

    assert capabilities["setup_resolve"] is True
    assert capabilities["preflight"] is True
    assert capabilities["project_setup"] is True
    assert capabilities["speech_profiles"] is True
    assert capabilities["narrations"] is True

    assert capabilities["library"] is True


def test_system_capabilities_exposes_ttsforge_product_view(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)

    response = client.get("/api/v1/system/capabilities", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {
        "source_inspection": True,
        "synthesis_preview": True,
        "m4b_export": False,
        "persistent_workspace": True,
        "available_engines": ["kokoro"],
        "warnings": ["M4B unavailable"],
    }


def test_speech_profile_routes_list_and_inspect_shared_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / "profiles"
    directory.mkdir()
    valid = directory / "custom profile.toml"
    valid.write_text('schema = "ssmdconvert-speech-profile"\n', encoding="utf-8")
    unrelated = directory / "settings.toml"
    unrelated.write_text('schema = "other"\n', encoding="utf-8")
    client, _, _ = make_client(tmp_path)

    unauthorized = client.get(
        "/api/v1/resources/speech-profiles", params={"directory": str(directory)}
    )
    listed = client.get(
        "/api/v1/resources/speech-profiles",
        params={"directory": "~/profiles"},
        headers=auth_headers(),
    )
    inspected = client.post(
        "/api/v1/resources/speech-profiles/inspect",
        headers=auth_headers(),
        json={"path": str(valid)},
    )
    rejected = client.post(
        "/api/v1/resources/speech-profiles/inspect",
        headers=auth_headers(),
        json={"path": str(unrelated)},
    )

    assert unauthorized.status_code == 401
    assert listed.json() == {
        "directory": str(directory),
        "profiles": [{"path": str(valid), "name": valid.name}],
    }
    assert inspected.json() == {"path": str(valid), "valid": True}
    assert rejected.json() == {"path": str(unrelated), "valid": False}


def test_library_project_routes_keep_malformed_candidates_visible(
    tmp_path: Path,
) -> None:
    client, _, _ = make_client(tmp_path)
    root = tmp_path / "Audiobooks"
    project = root / "Broken.ttsforge"
    project.mkdir(parents=True)
    (project / "render.readio.toml").touch()

    listed = client.get(
        "/api/v1/library/projects",
        params={"root": str(root)},
        headers=auth_headers(),
    )

    assert listed.status_code == 200
    body = listed.json()
    assert body["root"] == str(root)
    assert len(body["projects"]) == 1
    summary = body["projects"][0]
    assert summary["project"] == str(project)
    assert summary["error"]

    detail = client.get(
        f"/api/v1/library/projects/{summary['project_id']}", headers=auth_headers()
    )
    assert detail.status_code == 200
    assert detail.json()["project_id"] == summary["project_id"]
    assert detail.json()["error"] == summary["error"]


def test_library_summary_reports_matching_active_job(tmp_path: Path) -> None:
    project = tmp_path / "Book.ttsforge"
    project.mkdir()
    summary = ProjectSummary(
        project_id="project-id",
        title=None,
        author=None,
        source=None,
        project=project,
        chapter_count=0,
        selected_chapter_count=0,
        narrations=(),
        primary_narration_id=None,
        outputs=(),
        qc_state=None,
        active_job_id=None,
        last_activity=None,
        error=None,
    )
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    active_job = SimpleNamespace(
        id="job-1",
        state=JobState.RUNNING,
        project=project,
        created_at=created,
        started_at=created,
        finished_at=None,
        event_history=(),
    )

    result = _with_job_activity(summary, (active_job,))

    assert result.active_job_id == "job-1"
    assert result.last_activity == created
