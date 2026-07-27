"""Static contract checks for the explicit Typer command tree."""

from __future__ import annotations

from typer.main import get_command

from ttsforge.cli import app


def _option(command: object, name: str) -> object:
    for parameter in command.params:  # type: ignore[attr-defined]
        if parameter.name == name:
            return parameter
    raise AssertionError(f"missing parameter {name}")


def _option_names(parameter: object) -> set[str]:
    return set(parameter.opts) | set(parameter.secondary_opts)  # type: ignore[attr-defined]


def test_public_command_tree_is_complete() -> None:
    root = get_command(app)
    assert {
        "convert",
        "list",
        "info",
        "sample",
        "read",
        "voices",
        "demo",
        "download",
        "config",
        "short-sentence-advanced-config",
        "extract-names",
        "list-names",
        "phonemes",
    } == set(root.commands)
    assert {"export", "convert", "preview", "info"} == set(
        root.commands["phonemes"].commands
    )


def test_compatibility_sensitive_options_are_declared() -> None:
    root = get_command(app)
    convert = root.commands["convert"]
    assert {"--gpu", "--no-gpu"}.issubset(_option_names(_option(convert, "use_gpu")))
    assert {"--resume", "--no-resume"}.issubset(
        _option_names(_option(convert, "resume"))
    )
    assert {"--disable-short-sentence"} == set(
        _option_names(_option(convert, "disable_short_sentence"))
    )
    assert _option(convert, "speed").type.min == 0.5
    assert _option(convert, "speed").type.max == 2.0
    assert "--subchapter-marker" in _option_names(
        _option(convert, "subchapter_markers")
    )

    phonemes_convert = root.commands["phonemes"].commands["convert"]
    assert {"--streaming", "--no-streaming"}.issubset(
        _option_names(_option(phonemes_convert, "streaming"))
    )


def test_root_and_module_entry_points_share_version_semantics() -> None:
    root = get_command(app)
    result = root.main(["--version"], standalone_mode=False)
    assert result == 0
