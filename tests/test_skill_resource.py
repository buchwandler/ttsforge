from __future__ import annotations

from importlib.resources import files


def test_audiobook_skill_and_reference_resources_are_installed() -> None:
    skill = files("ttsforge").joinpath("skills", "ttsforge")
    expected = (
        skill.joinpath("SKILL.md"),
        skill.joinpath("references", "cli.md"),
        skill.joinpath("references", "projects.md"),
        skill.joinpath("references", "narrations.md"),
        skill.joinpath("references", "qc.md"),
    )

    assert all(resource.is_file() for resource in expected)
