"""Secure, bounded audio source resolution for SSMD annotations."""

from __future__ import annotations

import io
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf
from audiosig import downmix_to_mono


class SSMDRemoteAudioError(OSError):
    """A stable error for rejected or bounded remote sources."""


def _decode_audio(data: io.BytesIO, *, max_duration_s: float) -> tuple[np.ndarray, int]:
    try:
        with sf.SoundFile(data) as source:
            if source.frames < 0 or source.samplerate <= 0:
                raise ValueError("audio source has invalid stream metadata")
            if source.frames / source.samplerate > max_duration_s:
                raise ValueError("audio source exceeds the duration limit")
            samples = source.read(dtype="float32", always_2d=True)
            sample_rate = int(source.samplerate)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("audio source could not be decoded") from exc
    return downmix_to_mono(samples, channel_axis=1), sample_rate


def _host_is_private(host: str) -> bool:
    try:
        return (
            ipaddress.ip_address(host).is_private
            or ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        if host.lower() in {"localhost", "localhost.localdomain"}:
            return True
        try:
            addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return False
        for address in addresses:
            candidate = address[4][0]
            try:
                parsed = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if parsed.is_private or parsed.is_loopback or parsed.is_link_local:
                return True
        return False


class LocalSSMDAudioResolver:
    """Resolve SSMD audio paths relative to one document with hard limits."""

    def __init__(
        self,
        document_dir: Path,
        *,
        allowed_root: Path | None = None,
        allow_remote: bool = False,
        timeout_s: float = 10.0,
        max_bytes: int = 20_000_000,
        max_duration_s: float = 120.0,
    ) -> None:
        if isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if timeout_s <= 0 or max_duration_s < 0:
            raise ValueError("audio timeout and duration limits must be valid")
        self.document_dir = Path(document_dir).resolve()
        self.allowed_root = (
            Path(allowed_root).resolve() if allowed_root is not None else None
        )
        self.allow_remote = allow_remote
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.max_duration_s = max_duration_s

    def _within_root(self, path: Path) -> bool:
        if self.allowed_root is None:
            return True
        try:
            path.relative_to(self.allowed_root)
        except ValueError:
            return False
        return True

    def _resolve_local(self, source: str) -> tuple[np.ndarray, int]:
        candidate = Path(source)
        path = (self.document_dir / candidate).resolve()
        if not self._within_root(path):
            raise PermissionError("audio source is outside the allowed root")
        if not path.is_file():
            raise FileNotFoundError("audio source is missing or not a regular file")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise OSError("audio source metadata is unavailable") from exc
        if size > self.max_bytes:
            raise ValueError("audio source exceeds the byte limit")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise OSError("audio source could not be read") from exc
        if len(payload) > self.max_bytes:
            raise ValueError("audio source exceeds the byte limit")
        return _decode_audio(io.BytesIO(payload), max_duration_s=self.max_duration_s)

    def _resolve_remote(self, source: str) -> tuple[np.ndarray, int]:
        if not self.allow_remote:
            raise PermissionError("remote audio is disabled")
        parsed = urlparse(source)
        if parsed.scheme != "https" or not parsed.hostname:
            raise PermissionError("only HTTPS audio sources are allowed")
        if _host_is_private(parsed.hostname):
            raise PermissionError("private-network audio sources are not allowed")
        request = Request(source, headers={"Accept": "audio/*"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > self.max_bytes:
                            raise ValueError("remote audio exceeds the byte limit")
                    except ValueError as exc:
                        if "byte limit" in str(exc):
                            raise
                        raise ValueError("remote audio has invalid length") from exc
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(64 * 1024, self.max_bytes - total + 1))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ValueError("remote audio exceeds the byte limit")
        except ValueError:
            raise
        except Exception as exc:
            raise SSMDRemoteAudioError("remote audio could not be fetched") from exc
        return _decode_audio(
            io.BytesIO(b"".join(chunks)), max_duration_s=self.max_duration_s
        )

    def resolve(self, source: str) -> tuple[np.ndarray, int]:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("audio source must be a non-empty string")
        parsed = urlparse(source)
        if parsed.scheme:
            return self._resolve_remote(source)
        return self._resolve_local(source)


__all__ = ["LocalSSMDAudioResolver", "SSMDRemoteAudioError"]
