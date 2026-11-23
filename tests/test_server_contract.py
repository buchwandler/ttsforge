from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from ttsforge.server.app import create_app

EXPECTED_V1_ROUTES = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/system"),
    ("GET", "/api/v1/system/capabilities"),
    ("GET", "/api/v1/system/runtime"),
    ("POST", "/api/v1/sources/inspect"),
    ("POST", "/api/v1/sources/import"),
    ("GET", "/api/v1/sources/imports/{source_id}"),
    ("DELETE", "/api/v1/sources/imports/{source_id}"),
    ("GET", "/api/v1/catalog/engines"),
    ("GET", "/api/v1/catalog/targets"),
    ("GET", "/api/v1/catalog/voices"),
    ("GET", "/api/v1/catalog/engine-options"),
    ("GET", "/api/v1/resources/spacy"),
    ("POST", "/api/v1/resources/spacy/ensure"),
    ("GET", "/api/v1/resources/speech-profiles"),
    ("POST", "/api/v1/resources/speech-profiles/inspect"),
    ("GET", "/api/v1/projects/status"),
    ("GET", "/api/v1/projects/narrations"),
    ("POST", "/api/v1/projects/narrations"),
    ("GET", "/api/v1/projects/narrations/{narration_id}"),
    ("DELETE", "/api/v1/projects/narrations/{narration_id}"),
    ("POST", "/api/v1/previews"),
    ("POST", "/api/v1/projects/narrations/{narration_id}/preflight"),
    ("POST", "/api/v1/projects/narrations/{narration_id}/jobs"),
    ("GET", "/api/v1/projects/variants"),
    ("GET", "/api/v1/jobs"),
    ("POST", "/api/v1/jobs"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/jobs/{job_id}/events"),
    ("POST", "/api/v1/jobs/{job_id}/cancel"),
    ("POST", "/api/v1/jobs/{job_id}/retry"),
    ("POST", "/api/v1/setup/resolve"),
    ("POST", "/api/v1/conversions/preflight"),
    ("GET", "/api/v1/projects/setup"),
    ("GET", "/api/v1/projects/info"),
    ("GET", "/api/v1/library/projects"),
    ("GET", "/api/v1/library/projects/{project_id}"),
    ("GET", "/api/v1/projects/metadata"),
    ("PATCH", "/api/v1/projects/metadata"),
    ("POST", "/api/v1/projects/metadata/validate"),
    ("GET", "/api/v1/projects/chapters"),
    ("POST", "/api/v1/projects/chapters/select"),
    ("POST", "/api/v1/projects/qc"),
}


def test_versioned_route_inventory_matches_explicit_contract(tmp_path: Path) -> None:
    app = create_app(
        token="test-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(audiobook=None, catalog=None, conversion=None),
    )
    schema = app.openapi()
    actual = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert actual == EXPECTED_V1_ROUTES


def test_openapi_documents_typed_responses_bearer_and_public_health(
    tmp_path: Path,
) -> None:
    app = create_app(
        token="test-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(audiobook=None, catalog=None, conversion=None),
    )
    schema = app.openapi()

    excluded_keys = {
        "title",
        "summary",
        "operationId",
        "description",
        "examples",
        "externalDocs",
    }

    def remove_boilerplate(value: object) -> object:
        if isinstance(value, dict):
            normalized = {}
            for key, item in value.items():
                if key in excluded_keys:
                    continue
                if key == "properties" and isinstance(item, dict):
                    normalized[key] = {
                        field: remove_boilerplate(spec) for field, spec in item.items()
                    }
                else:
                    normalized[key] = remove_boilerplate(item)
            return normalized
        if isinstance(value, list):
            return [remove_boilerplate(item) for item in value]
        return value

    normalized_schema = remove_boilerplate(schema)
    assert isinstance(normalized_schema, dict)
    normalized_schema["info"]["title"] = schema["info"]["title"]
    checked_in_schema = json.loads(
        (Path(__file__).parents[1] / "docs/api/openapi-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert checked_in_schema == normalized_schema

    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    health = schema["paths"]["/api/v1/health"]["get"]
    system = schema["paths"]["/api/v1/system"]["get"]
    assert "security" not in health
    assert system["security"] == [{"HTTPBearer": []}]

    for method, path in EXPECTED_V1_ROUTES:
        operation = schema["paths"][path][method.lower()]
        if path != "/api/v1/health":
            assert operation["security"] == [{"HTTPBearer": []}]
        success_code = (
            "201"
            if (method, path) == ("POST", "/api/v1/projects/narrations")
            else "202"
            if method == "POST" and path.endswith(("/jobs", "/retry"))
            else "200"
        )
        response = operation["responses"][success_code]
        if path == "/api/v1/previews":
            assert response["content"]["audio/wav"]["schema"] == {
                "type": "string",
                "format": "binary",
            }
            continue
        response_schema = response["content"]["application/json"]["schema"]
        assert response_schema != {"type": "object"}, (path, method)


def test_runtime_openapi_is_public_and_docs_uis_are_disabled(tmp_path: Path) -> None:
    app = create_app(
        token="test-token",
        state_dir=tmp_path / "state",
        services=SimpleNamespace(audiobook=None, catalog=None, conversion=None),
    )
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/api/v1/system").status_code == 401
