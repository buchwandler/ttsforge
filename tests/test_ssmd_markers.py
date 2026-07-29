from __future__ import annotations

import json

from ttsforge.conversion import _result_issues, _write_marker_sidecar


def test_marker_offsets_are_exported_with_time(tmp_path) -> None:
    result = type(
        "Result",
        (),
        {
            "sample_rate": 24000,
            "markers": [{"name": "intro", "char_offset": 12, "sample_offset": 24000}],
            "trace": type("Trace", (), {"warnings": []})(),
        },
    )()
    path = tmp_path / "chapter.markers.json"

    markers = _write_marker_sidecar(path, result)

    assert markers[0]["time_s"] == 1.0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["markers"] == markers


def test_renderer_warning_codes_are_retained() -> None:
    result = type(
        "Result",
        (),
        {"trace": type("Trace", (), {"warnings": ["ssmd.audio_fallback: missing"]})()},
    )()

    issues = _result_issues(result)

    assert issues[0].code == "ssmd.audio_fallback"
    assert issues[0].message == "missing"
