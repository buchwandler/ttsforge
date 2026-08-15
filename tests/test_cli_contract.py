"""Static contract checks for the explicit Typer command tree."""

from __future__ import annotations

from typer.main import get_command
from typer.testing import CliRunner

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
    visible_root_commands = {
        name for name, command in root.commands.items() if not command.hidden
    }
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
        "extract-names",
        "list-names",
        "phonemes",
        "ssmd",
    } == visible_root_commands
    assert root.commands["short-sentence-advanced-config"].hidden
    assert {"short-sentence"} == set(root.commands["config"].commands)
    assert {"export", "convert", "preview", "info"} == set(
        root.commands["phonemes"].commands
    )


def test_compatibility_sensitive_options_are_declared() -> None:
    root = get_command(app)
    config = root.commands["config"]
    set_option = _option(config, "set_option")
    assert set_option.multiple is True
    assert set_option.nargs == 2

    convert = root.commands["convert"]
    assert {"--gpu", "--no-gpu"}.issubset(_option_names(_option(convert, "use_gpu")))
    assert "--provider" in _option_names(_option(convert, "provider"))
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
    assert "--provider" in _option_names(_option(phonemes_convert, "provider"))
    assert {"--streaming", "--no-streaming"}.issubset(
        _option_names(_option(phonemes_convert, "streaming"))
    )


def test_provider_exists_on_all_synthesis_commands() -> None:
    root = get_command(app)
    for command_name in ("convert", "sample", "read", "demo"):
        assert "--provider" in _option_names(
            _option(root.commands[command_name], "provider")
        )


def test_provider_and_gpu_conflict_exits_before_synthesis() -> None:
    result = CliRunner().invoke(app, ["sample", "test", "--provider", "nnapi", "--gpu"])
    assert result.exit_code == 2
    assert "--provider cannot be combined with --gpu or --no-gpu" in result.output


def test_invalid_provider_exits_before_synthesis() -> None:
    result = CliRunner().invoke(app, ["sample", "test", "--provider", "potato"])
    assert result.exit_code == 2
    assert "Invalid ONNX provider" in result.output


def test_root_and_module_entry_points_share_version_semantics() -> None:
    root = get_command(app)
    result = root.main(["--version"], standalone_mode=False)
    assert result == 0
