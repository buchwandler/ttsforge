"""The library must not alter warning policy for its host process."""

from __future__ import annotations

import subprocess
import sys


def test_import_preserves_unrelated_warnings() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import warnings; import ttsforge; warnings.warn('caller warning')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "caller warning" in result.stderr
