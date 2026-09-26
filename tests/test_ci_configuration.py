"""CI keeps development on Readio source and gates publishing on PyPI compatibility."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_test_workflow_uses_readio_source_without_backend_extras() -> None:
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    assert "repository: buchwandler/readio" in workflow
    assert "path: readio" in workflow
    assert "python -m pip install -e ../readio" in workflow
    assert '".[cpu]"' not in workflow
    assert "pykokoro[" not in workflow
    assert "espeak-ng" not in workflow
    for name in ("codecov.yml", "docs.yml"):
        auxiliary = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "python -m pip install -e ../readio" in auxiliary
        assert "pykokoro[" not in auxiliary
        assert "espeak-ng" not in auxiliary


def test_publish_workflow_gates_on_the_published_readio_api() -> None:
    workflow = (ROOT / ".github" / "workflows" / "python-publish.yml").read_text(
        encoding="utf-8"
    )
    install = workflow.index("python -m pip install build readio")
    gate = workflow.index("Require Readio's compatible public API")
    build = workflow.index("- name: Build package")
    publish = workflow.index("- name: Publish package")
    assert install < gate < build < publish
    assert "PUBLIC_API_VERSION" in workflow
    assert "app.audiobooks.export" in workflow
    assert "app.projects.build" in workflow
