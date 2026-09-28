from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_docs_use_markdown_sources_only() -> None:
    assert not list(DOCS.rglob("*.rst"))
    assert (DOCS / "index.md").is_file()
    assert (DOCS / "api" / "index.md").is_file()
    assert (DOCS / "projects.md").is_file()
    assert (ROOT / "examples" / "README.md").is_file()


def test_sphinx_enables_myst_markdown() -> None:
    config = runpy.run_path(str(DOCS / "conf.py"))

    assert "myst_parser" in config["extensions"]
    assert config["source_suffix"] == {".md": "markdown"}
    assert "deflist" in config["myst_enable_extensions"]


def test_install_docs_describe_released_readio_floor() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    installation = (DOCS / "installation.md").read_text(encoding="utf-8")
    index = (DOCS / "index.md").read_text(encoding="utf-8")
    testing = (DOCS / "testing.md").read_text(encoding="utf-8")

    for document in (readme, installation, index, testing):
        assert "Readio `>=0.3.3`" in document
        assert "not yet available" not in document
    assert "Readio checkout is not required for a normal installation" in " ".join(
        installation.split()
    )
    assert "python -m pip install ttsforge" in installation


def test_user_docs_cover_interaction_progress_and_persisted_chapter_scope() -> None:
    quickstart = (DOCS / "quickstart.md").read_text(encoding="utf-8")
    cli = (DOCS / "cli.md").read_text(encoding="utf-8")
    projects = (DOCS / "projects.md").read_text(encoding="utf-8")
    examples = " ".join(
        (ROOT / "examples" / "README.md").read_text(encoding="utf-8").split()
    )
    api = (DOCS / "api" / "index.md").read_text(encoding="utf-8")

    assert "prompts for a selection" in quickstart
    assert "--yes" in quickstart and "--non-interactive" in quickstart
    assert "--model-source" in quickstart and "--quality" in quickstart
    assert "--model MODEL" in cli and "--model-source SOURCE" in cli
    assert "## Guided synthesis setup" in quickstart
    assert "--spacy POLICY" in cli and "--unit UNIT" in cli
    assert "does not run the guided" in cli
    assert "`--chapters` when reusing a project" in projects
    assert "no TTSForge examples that import PyKokoro" in examples
    assert "from readio.api import Readio" in api
