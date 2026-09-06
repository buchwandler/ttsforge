from __future__ import annotations

import json
from pathlib import Path

from ttsforge.conversion_plan import plan_json, resolve_conversion_plan


def test_plan_is_deterministic_and_contains_input_selection(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("First chapter.\n\nSecond chapter.", encoding="utf-8")

    request = {"chapters": "1", "output_format": "wav", "provider": "cpu"}
    first = resolve_conversion_plan(
        source, request=request, config={"default_language": "a"}
    )
    second = resolve_conversion_plan(
        source, request=request, config={"default_language": "a"}
    )

    assert first.sha256 == second.sha256
    assert first.input.source_sha256
    assert first.input.selected_chapters == (0,)
    assert first.output.format == "wav"
    assert first.pipeline.provider == "cpu"
    payload = json.loads(plan_json(first))
    assert payload["schema"] == "ttsforge.conversion-plan.v1"
    assert payload["plan_sha256"] == first.sha256


def test_generation_payload_excludes_display_only_decisions(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Text.", encoding="utf-8")
    plan = resolve_conversion_plan(source, config={"default_language": "a"})
    payload = plan.generation_payload()
    assert payload["input"]["source_sha256"] == plan.input.source_sha256
    assert "decisions" not in payload
    assert "environment" not in payload


def test_explicit_invalid_provider_fails_before_tts(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Text.", encoding="utf-8")
    try:
        resolve_conversion_plan(source, request={"provider": "not-a-provider"})
    except ValueError as exc:
        assert "provider" in str(exc).lower()
    else:
        raise AssertionError("invalid provider unexpectedly produced a plan")
