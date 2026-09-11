"""Regression tests for CI-only runtime dependencies."""

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "tests.yml"


def test_windows_ci_exports_espeak_executable_to_following_steps() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    windows_step = workflow.split("- name: Install espeak-ng (Windows)", 1)[1].split(
        "- name: Install packages", 1
    )[0]

    assert "if: matrix.os == 'windows-latest'" in windows_step
    assert "choco install espeak-ng ffmpeg-full --yes --no-progress" in windows_step
    assert "Get-Command espeak-ng.exe" in windows_step
    assert "Get-ChildItem" in windows_step
    assert "$env:GITHUB_PATH" in windows_step
    assert "& $espeakPath --version" in windows_step
