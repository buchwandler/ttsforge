"""Packaging metadata and wheel-content regression tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = pytest.importorskip("tomli")


ROOT = Path(__file__).parents[1]


def _project() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_setuptools_scm_has_intentional_fallback() -> None:
    assert _project()["tool"]["setuptools_scm"]["fallback_version"] == "0.4.0"


def test_readio_requirement_uses_the_released_preflight_api_floor() -> None:
    dependencies = _project()["project"]["dependencies"]
    assert "readio>=0.3.1" in dependencies
    assert "readio" not in dependencies


def test_removed_backend_modules_are_not_part_of_the_source_package() -> None:
    obsolete = (
        "conversion.py",
        "pykokoro_adapter.py",
        "kokoro_runner.py",
        "audio_merge.py",
        "phonemes.py",
        "resume_identity.py",
    )
    for module in obsolete:
        assert not (ROOT / "ttsforge" / module).exists()


def test_built_wheels_do_not_report_zero_version_or_ship_legacy_orchestration() -> None:
    wheels = sorted((ROOT / "wheel-smoke").glob("*.whl"))
    if not wheels:
        pytest.skip("wheel-smoke/ has not been built")
    for wheel in wheels:
        assert "0.0.0" not in wheel.name
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            metadata_path = next(name for name in names if name.endswith("METADATA"))
            metadata = archive.read(metadata_path).decode("utf-8")
        assert "Version: 0.0.0" not in metadata
        assert "Requires-Dist: readio" in metadata
        assert "ttsforge/conversion.py" not in names
        assert "ttsforge/pykokoro_adapter.py" not in names
