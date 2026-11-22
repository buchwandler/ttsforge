from __future__ import annotations

import os
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
from ttsforge.application.models import (
    BookChapterView,
    BookInspectionView,
    ProjectVariantView,
    SpacyModelView,
    WorkflowPlanView,
)
from ttsforge.server.app import cleanup_imports, create_app


class FakeAudiobook:
    def __init__(self) -> None:
        self.inspected: list[Path] = []
        self.last_project = None
        self.last_source = None

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
                default=kwargs.get("default_voice") == "voice-a",
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


def make_client(
    tmp_path: Path,
    *,
    max_upload_bytes: int = 1024,
    allowed_origins: tuple[str, ...] = (),
):
    audiobook = FakeAudiobook()
    catalog = FakeCatalog()
    services = SimpleNamespace(audiobook=audiobook, catalog=catalog, conversion=None)
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
    imported = Path(response.json()["path"])
    assert imported.name == "book.epub"
    assert imported.parent.parent == tmp_path / "state" / "imports"
    assert imported.read_bytes() == b"book-data"
    assert audiobook.inspected == [imported]


def test_upload_size_limit_removes_partial_import(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, max_upload_bytes=4)

    response = client.post(
        "/api/v1/sources/import",
        headers=auth_headers(),
        files={"file": ("book.epub", b"12345", "application/epub+zip")},
    )

    assert response.status_code == 413
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
    assert catalog.voice_default == "voice-a"
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


def test_import_cleanup_removes_only_expired_directories(tmp_path: Path) -> None:
    imports = tmp_path / "imports"
    old = imports / "old"
    recent = imports / "recent"
    old.mkdir(parents=True)
    recent.mkdir()
    now = datetime(2025, 1, 31, tzinfo=timezone.utc)
    old_time = datetime(2024, 12, 1, tzinfo=timezone.utc).timestamp()
    recent_time = datetime(2025, 1, 20, tzinfo=timezone.utc).timestamp()
    os.utime(old, (old_time, old_time))
    os.utime(recent, (recent_time, recent_time))

    cleanup_imports(imports, retention_days=30, now=now)

    assert not old.exists()
    assert recent.exists()
