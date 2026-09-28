"""TTSForge delegates all synthesis/backend ownership to Readio."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = pytest.importorskip("tomli")


PROJECT = Path(__file__).parents[1]
BACKEND_DISTRIBUTIONS = (
    "pykokoro",
    "kokorog2p",
    "phrasplit",
    "ssmd",
    "epub2text",
    "audiosig",
    "soundfile",
)


def _metadata() -> dict[str, object]:
    return tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))


def test_readio_requirement_uses_the_released_preflight_api_floor() -> None:
    dependencies = _metadata()["project"]["dependencies"]
    readio = [
        item for item in dependencies if item.split("[", 1)[0].startswith("readio")
    ]

    assert readio == ["readio>=0.3.3"]


def test_ttsforge_does_not_declare_backend_or_rendering_dependencies() -> None:
    metadata = _metadata()["project"]
    declared = [*metadata["dependencies"]]
    for extra in metadata.get("optional-dependencies", {}).values():
        declared.extend(extra)

    names = {
        item.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0] for item in declared
    }
    assert not names.intersection(BACKEND_DISTRIBUTIONS)
    assert not {"cpu", "gpu", "openvino", "directml", "coreml"}.intersection(
        metadata.get("optional-dependencies", {})
    )
