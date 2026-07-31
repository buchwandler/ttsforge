"""Optional process-memory diagnostics for chapter conversion."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """A point-in-time process and system memory snapshot."""

    rss_bytes: int | None
    peak_rss_bytes: int | None
    available_bytes: int | None


_STATUS_VALUE = re.compile(r"^(VmRSS|VmHWM):\s+(\d+)\s+kB$")
_MEMINFO_VALUE = re.compile(r"^MemAvailable:\s+(\d+)\s+kB$")


def memory_debug_enabled() -> bool:
    """Return whether opt-in memory diagnostics are enabled."""
    return os.environ.get("TTSFORGE_MEMORY_DEBUG") == "1"


def snapshot() -> MemorySnapshot:
    """Read Linux/Android memory counters with a portable fallback."""
    rss_bytes: int | None = None
    peak_rss_bytes: int | None = None
    available_bytes: int | None = None

    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            match = _STATUS_VALUE.match(line)
            if not match:
                continue
            value = int(match.group(2)) * 1024
            if match.group(1) == "VmRSS":
                rss_bytes = value
            else:
                peak_rss_bytes = value
    except (OSError, ValueError):
        pass

    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            match = _MEMINFO_VALUE.match(line)
            if match:
                available_bytes = int(match.group(1)) * 1024
                break
    except (OSError, ValueError):
        pass

    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        fallback_peak = int(usage.ru_maxrss)
        if sys.platform != "darwin":
            fallback_peak *= 1024
        if peak_rss_bytes is None:
            peak_rss_bytes = fallback_peak

    return MemorySnapshot(rss_bytes, peak_rss_bytes, available_bytes)


def log_snapshot(
    log: Callable[[str, str], None],
    phase: str,
    *,
    provider: str,
) -> None:
    """Log a snapshot when memory debugging is explicitly enabled."""
    if not memory_debug_enabled():
        return
    current = snapshot()
    log(
        f"Memory phase={phase} provider={provider} "
        f"rss_bytes={current.rss_bytes} peak_rss_bytes={current.peak_rss_bytes} "
        f"available_bytes={current.available_bytes}",
        "info",
    )
