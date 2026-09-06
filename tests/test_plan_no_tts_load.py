from __future__ import annotations

from pathlib import Path

from ttsforge.conversion_plan import resolve_conversion_plan


def test_plan_does_not_construct_pipeline_or_onnx(monkeypatch, tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Text.", encoding="utf-8")

    def fail(*args, **kwargs):
        raise AssertionError("planning constructed a synthesis pipeline")

    monkeypatch.setattr("pykokoro.KokoroPipeline", fail, raising=False)
    plan = resolve_conversion_plan(source, config={"default_language": "a"})
    assert plan.ok
