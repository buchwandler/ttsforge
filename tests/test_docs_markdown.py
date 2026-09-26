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


def test_readme_describes_readio_frontend_and_release_gate() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    installation = (DOCS / "installation.md").read_text(encoding="utf-8")
    migration = (DOCS / "migration-readio.md").read_text(encoding="utf-8")

    assert "audiobook-focused command-line frontend for [Readio]" in readme
    assert "no minimum version is guessed" in readme
    assert "compatible published pin" in installation
    assert "A compatible release is not yet available on PyPI" in installation
    assert "not Readio projects" in migration
    assert "--fresh" in migration
    assert (
        "`read`, `sample`, `demo`, `download`, and `phonemes` are removed" in migration
    )


def test_user_docs_explain_project_reuse_and_removed_backend_examples() -> None:
    projects = (DOCS / "projects.md").read_text(encoding="utf-8")
    cli = (DOCS / "cli.md").read_text(encoding="utf-8")
    examples = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    api = (DOCS / "api" / "index.md").read_text(encoding="utf-8")

    assert "chapter scope" in projects
    assert "Former TTSForge workspaces" in projects
    assert "are no longer registered" in cli
    assert "no TTSForge examples that import PyKokoro" in examples
    assert "from readio.api import Readio" in api
