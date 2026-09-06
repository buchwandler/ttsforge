from __future__ import annotations

import json
from pathlib import Path

from ttsforge.conversion_plan import resolve_conversion_plan
from ttsforge.render_manifest import (
    MANIFEST_SCHEMA,
    build_render_manifest,
    manifest_path,
    write_render_manifest,
)


def test_manifest_records_committed_hashes_and_exact_plan(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Text.", encoding="utf-8")
    output = tmp_path / "Book.m4b"
    output.write_bytes(b"audio")
    markers = tmp_path / "Book.m4b.markers.json"
    markers.write_text('{"markers": []}', encoding="utf-8")
    plan = resolve_conversion_plan(
        source, request={"output": output}, config={"default_language": "a"}
    )

    payload = build_render_manifest(
        output_path=output,
        plan=plan,
        source_path=source,
        selected_chapters=[0],
        generation_fingerprint="generation-hash",
        marker_path=markers,
        created_at="2026-01-01T00:00:00+00:00",
    )
    path = write_render_manifest(output, payload)
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert path == manifest_path(output)
    assert loaded["schema"] == MANIFEST_SCHEMA
    assert loaded["plan"]["sha256"] == plan.sha256
    assert loaded["result"]["output"]["byte_count"] == 5
    assert loaded["result"]["markers_sidecar"]["path"] == str(markers)


def test_manifest_requires_committed_output(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("Text.", encoding="utf-8")
    plan = resolve_conversion_plan(source, config={"default_language": "a"})
    missing = tmp_path / "missing.m4b"

    try:
        build_render_manifest(
            output_path=missing,
            plan=plan,
            source_path=source,
            selected_chapters=[0],
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing output unexpectedly produced a manifest")
