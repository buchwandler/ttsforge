from __future__ import annotations

from ttsforge import memory_diagnostics


def test_memory_debug_is_opt_in(monkeypatch) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.delenv("TTSFORGE_MEMORY_DEBUG", raising=False)

    memory_diagnostics.log_snapshot(
        lambda message, level: messages.append((message, level)),
        "disabled",
        provider="cpu",
    )

    assert messages == []


def test_enabled_memory_snapshot_includes_phase_and_provider(monkeypatch) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setenv("TTSFORGE_MEMORY_DEBUG", "1")
    monkeypatch.setattr(
        memory_diagnostics,
        "snapshot",
        lambda: memory_diagnostics.MemorySnapshot(100, 200, 300),
    )

    memory_diagnostics.log_snapshot(
        lambda message, level: messages.append((message, level)),
        "after synthesis",
        provider="nnapi",
    )

    assert messages == [
        (
            "Memory phase=after synthesis provider=nnapi rss_bytes=100 "
            "peak_rss_bytes=200 available_bytes=300",
            "info",
        )
    ]


def test_snapshot_reports_process_memory() -> None:
    current = memory_diagnostics.snapshot()

    assert current.rss_bytes is None or current.rss_bytes >= 0
    assert current.peak_rss_bytes is None or current.peak_rss_bytes >= 0
    assert current.available_bytes is None or current.available_bytes >= 0
