"""Quality gates for maintained runnable examples."""

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
MAINTAINED = (
    "paragraph_conversion",
    "paragraph_resume",
    "paragraph_manifest",
    "pykokoro_paragraph_units",
    "phoneme_export",
)


def test_maintained_examples_compile_and_import_without_running_main() -> None:
    for name in MAINTAINED:
        source = (EXAMPLES / f"{name}.py").read_text(encoding="utf-8")
        compile(source, str(EXAMPLES / f"{name}.py"), "exec")
        module = importlib.import_module(f"examples.{name}")
        assert callable(module.main)


def test_examples_do_not_use_private_pykokoro_attributes() -> None:
    for path in EXAMPLES.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "pykokoro._" not in source
        assert "._Prepared" not in source


def test_paragraph_examples_use_lifecycle_and_audio_ownership() -> None:
    conversion = (EXAMPLES / "paragraph_conversion.py").read_text(encoding="utf-8")
    resume = (EXAMPLES / "paragraph_resume.py").read_text(encoding="utf-8")
    low_level = (EXAMPLES / "pykokoro_paragraph_units.py").read_text(encoding="utf-8")
    assert "with TTSConverter" in conversion
    assert "with TTSConverter" in resume
    assert "with KokoroRunner" in low_level
    assert "with runner.prepare_paragraph_units" in low_level
    assert "result.release_audio()" in low_level


def test_manifest_example_uses_only_standard_library_modules() -> None:
    source = (EXAMPLES / "paragraph_manifest.py").read_text(encoding="utf-8")
    assert "from ttsforge" not in source
    assert "import soundfile" not in source
    assert "import numpy" not in source
