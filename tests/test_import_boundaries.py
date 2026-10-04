"""Regression tests for provider-independent imports and the public API boundary."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "ttsforge"
FORBIDDEN_IMPORTS = {
    "pykokoro",
    "kokorog2p",
    "phrasplit",
    "epub2text",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "kivy",
    "gi",
}


def _run_python(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in ("FORCE_COLOR", "CLICOLOR_FORCE", "CLICOLOR"):
        env.pop(name, None)
    env["NO_COLOR"] = "1"
    env["COLUMNS"] = "240"
    return subprocess.run(
        [sys.executable, "-W", "error", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )


def _semantic_output(output: str) -> str:
    without_ansi = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    return " ".join(without_ansi.split())


def _import_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_production_imports_only_the_readio_public_api() -> None:
    violations: list[str] = []
    for path in PRODUCTION.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                root = module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    violations.append(f"{path.relative_to(ROOT)}: {module}")
                if root == "readio" and (
                    module != "readio.api" or path.name != "readio_backend.py"
                ):
                    violations.append(f"{path.relative_to(ROOT)}: {module}")
    assert not violations, "Forbidden imports:\n" + "\n".join(violations)


def test_application_modules_do_not_import_frontend_or_readio_modules() -> None:
    forbidden = {
        "typer",
        "rich",
        "readio",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
        "kivy",
        "gi",
    }
    violations = [
        f"{path.relative_to(ROOT)}: {module}"
        for path in (PRODUCTION / "application").rglob("*.py")
        for module in _import_modules(path)
        if module.split(".", 1)[0] in forbidden
    ]
    assert not violations, "Frontend dependencies in application:\n" + "\n".join(
        violations
    )


def test_cli_modules_do_not_import_readio() -> None:
    violations = [
        f"{path.relative_to(ROOT)}: {module}"
        for path in (PRODUCTION / "cli").rglob("*.py")
        for module in _import_modules(path)
        if module.split(".", 1)[0] == "readio"
    ]
    assert not violations, "Readio imports in CLI:\n" + "\n".join(violations)


def test_readio_public_api_imports_are_confined_to_the_adapter() -> None:
    owners = [
        path.relative_to(PRODUCTION)
        for path in PRODUCTION.rglob("*.py")
        if any(module == "readio.api" for module in _import_modules(path))
    ]
    assert owners == [Path("readio_backend.py")]


def test_import_ttsforge_does_not_load_a_synthesis_backend() -> None:
    result = _run_python(
        "-c",
        "import sys; import ttsforge; "
        "assert not any(name == 'pykokoro' or name.startswith('pykokoro.') "
        "for name in sys.modules)",
    )
    assert result.returncode == 0, result.stderr


def test_cli_help_and_version_are_available_without_backend_import() -> None:
    help_result = _run_python("-c", "from ttsforge.cli import main; main(['--help'])")
    version_result = _run_python(
        "-c", "from ttsforge.cli import main; main(['--version'])"
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage:" in _semantic_output(help_result.stdout)
    assert version_result.returncode == 0, version_result.stderr
    assert "ttsforge version" in version_result.stdout


def test_convert_help_exposes_public_synthesis_controls_not_backend_controls() -> None:
    result = _run_python(
        "-c", "from ttsforge.cli import main; main(['convert', '--help'])"
    )
    assert result.returncode == 0, result.stderr
    help_text = _semantic_output(result.stdout)
    for option in (
        "--chapters",
        "--voice",
        "--fresh",
        "--spacy",
        "--short-sentence",
        "--lexicon",
        "--no-lexicons",
        "--auto-lexicons",
        "--g2p-fallback",
        "--lexicon-data-policy",
        "--voice-level",
        "--pause-mode",
        "--unit",
        "--synthesis-unit",
        "--allow-experimental",
    ):
        assert option in help_text
    assert "--provider" not in help_text


def test_phoneme_command_is_not_registered() -> None:
    result = _run_python(
        "-c", "from ttsforge.cli import main; main(['phonemes', '--help'])"
    )
    assert result.returncode != 0
    assert "No such command 'phonemes'." in result.stderr
