"""Focused tests for the canonical resumable-conversion identity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ttsforge.conversion import ConversionOptions
from ttsforge.resume_identity import (
    GENERATION_IDENTITY_SCHEMA,
    build_generation_identity,
    canonicalize_json,
    diff_generation_identity,
    generation_fingerprint,
    path_identity,
    validate_saved_generation_identity,
)


def _identity(options: ConversionOptions):
    return build_generation_identity(
        options,
        resolved_sentence_models={},
        resolved_g2p_models={},
    )


def test_identity_dict_order_is_irrelevant() -> None:
    assert generation_fingerprint({"b": 2, "a": 1}) == generation_fingerprint(
        {"a": 1, "b": 2}
    )


def test_identity_tuple_is_canonical_list() -> None:
    assert canonicalize_json(("a", 1)) == ["a", 1]


def test_identity_rejects_set() -> None:
    with pytest.raises(TypeError, match="cannot be a set"):
        canonicalize_json({"values": {1, 2}})


def test_identity_rejects_nan() -> None:
    with pytest.raises(ValueError, match="finite"):
        canonicalize_json(float("nan"))


def test_identity_rejects_unknown_object_instead_of_using_repr() -> None:
    with pytest.raises(TypeError, match="unsupported identity value"):
        canonicalize_json(object())


def test_identity_diff_returns_dotted_paths() -> None:
    differences = diff_generation_identity(
        {"voice": "af_heart", "prosody": {"method": "wsola"}},
        {"voice": "af_bella", "prosody": {"method": "psola"}},
    )
    assert [difference.path for difference in differences] == [
        "prosody.method",
        "voice",
    ]


def test_saved_payload_hash_must_match_saved_digest() -> None:
    identity = _identity(ConversionOptions(conversion_unit="paragraph"))
    assert validate_saved_generation_identity(
        schema=GENERATION_IDENTITY_SCHEMA,
        payload=identity.payload,
        fingerprint=identity.fingerprint,
    )
    assert not validate_saved_generation_identity(
        schema=GENERATION_IDENTITY_SCHEMA,
        payload=identity.payload,
        fingerprint="corrupt",
    )


def test_fresh_and_resume_flags_are_identity_neutral() -> None:
    fresh = _identity(ConversionOptions(conversion_unit="paragraph", resume=False))
    resume = _identity(ConversionOptions(conversion_unit="paragraph", resume=True))
    assert fresh.payload == resume.payload
    assert fresh.fingerprint == resume.fingerprint


def test_default_model_cache_files_do_not_enter_identity(tmp_path: Path) -> None:
    before = _identity(ConversionOptions())
    (tmp_path / "model.onnx").write_bytes(b"downloaded later")
    after = _identity(ConversionOptions())
    assert before == after


def test_explicit_model_file_hash_changes_identity(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"one")
    first = _identity(ConversionOptions(model_path=model))
    model.write_bytes(b"two")
    second = _identity(ConversionOptions(model_path=model))
    assert first.payload["model_path"] != second.payload["model_path"]
    assert first.fingerprint != second.fingerprint


def test_path_identity_normalizes_files_and_rejects_directories(tmp_path: Path) -> None:
    file_path = tmp_path / "model.onnx"
    file_path.write_bytes(b"model")
    identity = path_identity(file_path, required=True)
    assert identity is not None
    assert identity["kind"] == "file"
    assert identity["exists"] is True
    with pytest.raises(ValueError, match="not a file"):
        path_identity(tmp_path, required=True)


def test_identity_is_deterministic_across_processes(tmp_path: Path) -> None:
    output = tmp_path / "identity.json"
    script = """
import json
from ttsforge.conversion import ConversionOptions
from ttsforge.resume_identity import build_generation_identity
identity = build_generation_identity(
    ConversionOptions(conversion_unit='paragraph'),
    resolved_sentence_models={},
    resolved_g2p_models={},
)
print(json.dumps(
    {'payload': identity.payload, 'fingerprint': identity.fingerprint},
    sort_keys=True,
))
"""
    first = subprocess.check_output([sys.executable, "-c", script], text=True)
    second = subprocess.check_output([sys.executable, "-c", script], text=True)
    output.write_text(first, encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(second)
