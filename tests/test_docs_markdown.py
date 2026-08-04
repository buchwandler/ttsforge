from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_docs_use_markdown_sources_only() -> None:
    assert not list(DOCS.rglob("*.rst"))
    assert (DOCS / "index.md").is_file()
    assert (DOCS / "api" / "index.md").is_file()


def test_sphinx_enables_myst_markdown() -> None:
    config = runpy.run_path(str(DOCS / "conf.py"))

    assert "myst_parser" in config["extensions"]
    assert config["source_suffix"] == {".md": "markdown"}
    assert "deflist" in config["myst_enable_extensions"]


def test_readme_has_no_stale_documentation_rst_link() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/ssmd.rst" not in readme
    assert "docs/ssmd.md" in readme


def test_release_docs_describe_current_paragraph_and_spacy_contracts() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    installation = (DOCS / "installation.md").read_text(encoding="utf-8")
    configuration = (DOCS / "configuration.md").read_text(encoding="utf-8")
    api = (DOCS / "api" / "index.md").read_text(encoding="utf-8")

    assert "retained WAV per render unit" in readme
    assert "falls back" in readme
    assert "AudioSig `>=0.1.2,<0.2`" in installation
    assert "use_spacy=null" in installation
    assert "use_spacy=false" in configuration
    assert "examples/paragraph_manifest.py" in api
