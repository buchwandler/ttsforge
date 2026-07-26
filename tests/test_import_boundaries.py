"""Regression tests for provider-independent imports and CLI startup."""

from __future__ import annotations

import subprocess
import sys


def _run_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "error", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_import_ttsforge_does_not_load_onnx_backend() -> None:
    result = _run_python(
        "-c",
        "import sys; import ttsforge; "
        "assert 'pykokoro.onnx_backend' not in sys.modules",
    )
    assert result.returncode == 0, result.stderr


def test_help_and_version_are_available_without_backend_import() -> None:
    help_result = _run_python("-c", "from ttsforge.cli import main; main(['--help'])")
    version_result = _run_python(
        "-c", "from ttsforge.cli import main; main(['--version'])"
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage:" in help_result.stdout
    assert version_result.returncode == 0, version_result.stderr
    assert "ttsforge version" in version_result.stdout


def test_conversion_help_is_provider_independent() -> None:
    result = _run_python(
        "-c", "from ttsforge.cli import main; main(['convert', '--help'])"
    )
    assert result.returncode == 0, result.stderr
    assert "Generate only SSMD files" in result.stdout
