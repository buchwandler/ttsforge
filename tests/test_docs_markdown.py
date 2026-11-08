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


def test_installation_and_migration_docs_are_present() -> None:
    for path in (
        ROOT / "README.md",
        DOCS / "installation.md",
        DOCS / "migration-readio.md",
        DOCS / "testing.md",
    ):
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()
