"""Packaging metadata regression tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def test_setuptools_scm_has_intentional_fallback() -> None:
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["setuptools_scm"]["fallback_version"] != "0.0.0"


def test_built_wheels_do_not_report_zero_version() -> None:
    wheels = sorted(Path("wheel-smoke").glob("*.whl"))
    if not wheels:
        pytest.skip("wheel-smoke/ has not been built")
    for wheel in wheels:
        assert "0.0.0" not in wheel.name
        with zipfile.ZipFile(wheel) as archive:
            metadata_path = next(
                name for name in archive.namelist() if name.endswith("METADATA")
            )
            metadata = archive.read(metadata_path).decode("utf-8")
        assert "Version: 0.0.0" not in metadata
