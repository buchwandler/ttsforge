"""Packaging metadata regression tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def test_setuptools_scm_has_intentional_fallback() -> None:
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["setuptools_scm"]["fallback_version"] == "0.3.4"


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


def test_pykokoro_dependency_floor_is_released_handoff() -> None:
    tomllib = pytest.importorskip("tomllib")
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = project["project"]["dependencies"]
    assert "pykokoro[cpu]>=0.8.3,<0.9" in dependencies
    assert "kokorog2p[espeak,en]>=0.8.0,<0.9" in dependencies
    assert "phrasplit>=0.3.4,<0.4" in dependencies
    assert not any("pykokoro[cpu]>=0.8.2" in dependency for dependency in dependencies)
    assert not any("pykokoro[cpu]>=0.8.1" in dependency for dependency in dependencies)
    assert not any("pykokoro[cpu]>=0.7.3" in dependency for dependency in dependencies)
    assert not any("pykokoro[cpu]>=0.6.6" in dependency for dependency in dependencies)


def test_ssmd_dependency_is_direct_and_bounded() -> None:
    tomllib = pytest.importorskip("tomllib")
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert "ssmd>=0.8.1,<0.9" in project["project"]["dependencies"]


def test_audiosig_dependency_floor_supports_waveform_primitives() -> None:
    tomllib = pytest.importorskip("tomllib")
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = project["project"]["dependencies"]
    assert "audiosig>=0.1.2,<0.2" in dependencies
    assert "numpy" in dependencies
    assert "soundfile>=0.12.0" in dependencies


def test_audiosig_waveform_primitives_are_importable() -> None:
    from audiosig import downmix_to_mono, generate_silence

    assert callable(downmix_to_mono)
    assert callable(generate_silence)


def test_pykokoro_ssmd_080_contract_is_importable() -> None:
    pytest.importorskip("pykokoro")
    try:
        from pykokoro import SSMDPauseOverrides, SSMDRenderConfig
        from pykokoro.ssmd_parser import parse_ssmd_document
    except ImportError as exc:  # pragma: no cover - dependency compatibility path
        pytest.fail(
            "pykokoro>=0.8.3 is required for SSMD 0.8 and memory-release integration; "
            f"missing public symbol: {exc}"
        )

    assert SSMDPauseOverrides is not None
    assert SSMDRenderConfig is not None
    assert callable(parse_ssmd_document)
