from __future__ import annotations

import pytest

from ttsforge.ssmd_support import (
    SSMDPauseOverrideOptions,
    SSMDPolicy,
    SSMDValidationError,
    build_pykokoro_ssmd_config,
    inspect_ssmd_document,
    validate_ssmd_document,
)


def test_inspection_separates_header_and_preserves_title() -> None:
    source = "---\ntitle: Portable review\n---\nBody text.\n"

    info = inspect_ssmd_document(source)

    assert info.title == "Portable review"
    assert info.body == "Body text.\n"
    assert info.issues == ()


def test_unknown_header_policy_is_applied() -> None:
    source = "---\ncustom: value\n---\nBody text.\n"

    assert inspect_ssmd_document(source).warnings[0].code == "header.unknown_key"
    error_info = inspect_ssmd_document(
        source, policy=SSMDPolicy(unknown_header="error")
    )
    assert error_info.errors[0].code == "header.unknown_key"
    assert (
        inspect_ssmd_document(source, policy=SSMDPolicy(unknown_header="ignore")).issues
        == ()
    )


def test_malformed_header_is_line_aware_and_validation_collects_it() -> None:
    source = "---\ntitle: [invalid\n---\nBody text.\n"

    info = inspect_ssmd_document(source)
    assert info.errors[0].code == "header.yaml_invalid"
    assert info.errors[0].line == 2
    with pytest.raises(SSMDValidationError) as raised:
        validate_ssmd_document(source)
    assert "[header.yaml_invalid]" in str(raised.value)


def test_policy_translation_keeps_explicit_pause_provenance() -> None:
    policy = SSMDPolicy(
        pause_overrides=SSMDPauseOverrideOptions(
            enabled=False, sentence="250ms", voice_change="350ms"
        ),
        voice_bindings={"kokoro": {"narrator": "af_sarah"}},
    )

    config = build_pykokoro_ssmd_config(policy)

    assert config.parse_header is True
    assert config.voice_bindings == {"kokoro": {"narrator": "af_sarah"}}
    assert config.pause_defaults.enabled is False
    assert config.pause_defaults.sentence == "250ms"
    assert config.pause_defaults.voice_change == "350ms"


def test_literal_header_mode_does_not_parse_or_speak_yaml_as_metadata() -> None:
    source = "---\nThis is spoken text\n---\n"

    info = inspect_ssmd_document(source, policy=SSMDPolicy(parse_header=False))

    assert info.header == {}
    assert info.body == source
