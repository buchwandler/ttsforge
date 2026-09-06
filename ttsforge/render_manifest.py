"""Portable provenance manifests for completed TTSForge renders."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from .utils import atomic_write_json

MANIFEST_SCHEMA = "ttsforge.render-manifest.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "unavailable"


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def manifest_path(output_path: Path) -> Path:
    """Return the deterministic sidecar path for a final output."""
    return output_path.with_suffix(output_path.suffix + ".ttsforge.json")


def build_render_manifest(
    *,
    output_path: Path,
    plan: Any,
    source_path: Path,
    selected_chapters: Sequence[int],
    generation_fingerprint: str | None = None,
    ssmd_policy_fingerprint: str | None = None,
    marker_path: Path | None = None,
    created_at: str | None = None,
    package_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a manifest from already committed output artifacts."""
    if not output_path.is_file():
        raise FileNotFoundError(f"completed output does not exist: {output_path}")
    plan_payload = plan.to_dict() if hasattr(plan, "to_dict") else _canonical(plan)
    plan_json = json.dumps(
        plan_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    plan_hash = (
        getattr(plan, "sha256", None)
        or hashlib.sha256(plan_json.encode("utf-8")).hexdigest()
    )
    marker_info: dict[str, Any] | None = None
    if marker_path is not None:
        if not marker_path.is_file():
            raise FileNotFoundError(f"marker sidecar does not exist: {marker_path}")
        marker_info = {
            "path": str(marker_path),
            "sha256": sha256_file(marker_path),
        }
    versions = dict(
        package_versions
        or {
            name: _version(name)
            for name in (
                "ttsforge",
                "pykokoro",
                "ssmd",
                "epub2text",
                "phrasplit",
                "kokorog2p",
                "audiosig",
            )
        }
    )
    payload: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
            "selection": list(selected_chapters),
        },
        "plan": {
            "schema": plan_payload.get("schema"),
            "sha256": plan_hash,
            "resolved": plan_payload,
        },
        "generation": {
            "identity_schema": 2,
            "fingerprint": generation_fingerprint,
            "ssmd_policy_fingerprint": ssmd_policy_fingerprint,
        },
        "result": {
            "output": {
                "path": str(output_path),
                "format": output_path.suffix.lstrip("."),
                "byte_count": output_path.stat().st_size,
                "sha256": sha256_file(output_path),
            },
            "markers_sidecar": marker_info,
        },
        "environment": {"packages": versions},
    }
    return _canonical(payload)


def write_render_manifest(
    output_path: Path,
    manifest: Mapping[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Atomically write a manifest without changing the completed media."""
    target = path or manifest_path(output_path)
    atomic_write_json(target, _canonical(manifest), indent=2, ensure_ascii=True)
    return target
