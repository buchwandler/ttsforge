"""Tests for resolving interactive CLI behavior from terminal capabilities."""

from __future__ import annotations

import sys

import pytest

from ttsforge.ui.interaction import resolve_interaction_mode


class _Stream:
    def __init__(self, terminal: bool) -> None:
        self.terminal = terminal

    def isatty(self) -> bool:
        return self.terminal


@pytest.mark.parametrize(
    ("stdin_tty", "stdout_tty", "stderr_tty", "interactive_expected"),
    [
        (True, True, True, True),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
        (False, False, False, False),
    ],
)
def test_interaction_requires_all_stdio_streams_to_be_tty(
    monkeypatch,
    stdin_tty: bool,
    stdout_tty: bool,
    stderr_tty: bool,
    interactive_expected: bool,
) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(stdin_tty))
    monkeypatch.setattr(sys, "stdout", _Stream(stdout_tty))
    monkeypatch.setattr(sys, "stderr", _Stream(stderr_tty))

    mode = resolve_interaction_mode(
        json_mode=False, assume_yes=False, force_non_interactive=False
    )

    assert mode.interactive is interactive_expected
    assert mode.live_progress is interactive_expected
    assert mode.confirm is interactive_expected


def test_yes_keeps_interaction_but_suppresses_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(True))
    monkeypatch.setattr(sys, "stdout", _Stream(True))
    monkeypatch.setattr(sys, "stderr", _Stream(True))

    mode = resolve_interaction_mode(
        json_mode=False, assume_yes=True, force_non_interactive=False
    )

    assert mode.interactive is True
    assert mode.live_progress is True
    assert mode.confirm is False


@pytest.mark.parametrize(
    "json_mode,force_non_interactive", [(True, False), (False, True)]
)
def test_json_and_non_interactive_disable_all_prompts(
    monkeypatch, json_mode: bool, force_non_interactive: bool
) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(True))
    monkeypatch.setattr(sys, "stdout", _Stream(True))
    monkeypatch.setattr(sys, "stderr", _Stream(True))

    mode = resolve_interaction_mode(
        json_mode=json_mode,
        assume_yes=False,
        force_non_interactive=force_non_interactive,
    )

    assert mode.interactive is False
    assert mode.live_progress is False
    assert mode.confirm is False
    assert mode.json is json_mode
