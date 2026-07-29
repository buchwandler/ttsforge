from __future__ import annotations

from pathlib import Path

from ttsforge.ssmd_support import (
    SSMDPauseOverrideOptions,
    SSMDPolicy,
    build_pykokoro_ssmd_config,
    inspect_ssmd_document,
    validate_ssmd_document,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_complete_ssmd_080_fixture_preserves_metadata_and_has_no_errors() -> None:
    source = (FIXTURES / "ssmd_080_complete.ssmd").read_text(encoding="utf-8")

    info = inspect_ssmd_document(source)

    assert info.title == "Review podcast"
    assert info.header["voice_bindings"]["kokoro"]["moderator"] == "af_sarah"
    assert info.body.startswith("# Review podcast")
    assert not info.errors, [issue.format() for issue in info.errors]


def test_extensions_are_rejected_by_default_for_kokoro() -> None:
    source = (FIXTURES / "ssmd_080_extension_unsupported.ssmd").read_text(
        encoding="utf-8"
    )

    info = inspect_ssmd_document(source)

    assert any(issue.code == "header.extensions_unsupported" for issue in info.errors)


def test_pause_override_precedence_is_explicit_and_deterministic() -> None:
    source = "---\npause_defaults:\n  sentence: 250ms\n---\nHello.\n"
    policy = SSMDPolicy(pause_overrides=SSMDPauseOverrideOptions(sentence="900ms"))

    first = validate_ssmd_document(source, policy=policy)
    second = validate_ssmd_document(source, policy=policy)

    assert first.header == second.header
    assert first.issues == second.issues


def test_explicit_binding_override_wins_and_emits_conflict_diagnostic() -> None:
    source = """---
voice_bindings:
  kokoro:
    narrator: af_sarah
---
<div voice="narrator">Hello.</div>
"""

    info = inspect_ssmd_document(
        source,
        policy=SSMDPolicy(voice_bindings={"kokoro": {"narrator": "af_bella"}}),
    )

    assert any(issue.code == "ssmd.voice_binding_override" for issue in info.warnings)


def test_pykokoro_pause_resolution_uses_api_over_document_header() -> None:
    from pykokoro.ssmd_parser import parse_ssmd_document

    source = "---\npause_defaults:\n  sentence: 250ms\n---\nHello.\n"
    parsed = parse_ssmd_document(
        source,
        render_config=build_pykokoro_ssmd_config(
            SSMDPolicy(pause_overrides=SSMDPauseOverrideOptions(sentence="900ms"))
        ),
    )

    assert parsed.pause_defaults.sentence == 0.9
