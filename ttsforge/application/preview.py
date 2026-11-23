"""Explicit-text narration previews synthesized through Readio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import InputValidationError
from .models import PreviewAudio, ProjectPaths
from .narrations import NarrationApplicationService


@dataclass(frozen=True, slots=True)
class PreviewRequest:
    project: Path
    narration_id: str | None = None
    text: str | None = None
    chapter: int | None = None
    paragraph: int | None = None


@dataclass(frozen=True, slots=True)
class PreviewExcerpt:
    text: str
    chapter: int | None = None
    chapter_title: str | None = None
    paragraph: int | None = None
    source: str = "explicit"


@dataclass(frozen=True, slots=True)
class PreviewResult:
    narration_id: str
    excerpt: PreviewExcerpt
    audio: PreviewAudio


class PreviewCancellation(Protocol):
    def cancel(self) -> None: ...


class PreviewBackend(Protocol):
    def new_cancellation_token(self) -> PreviewCancellation: ...

    def synthesize_preview(
        self,
        *,
        text: str,
        profile: Path,
        role: str | None = None,
        cancellation: PreviewCancellation | None = None,
    ) -> PreviewAudio: ...


class PreviewApplicationService:
    """Resolve a saved narration profile and synthesize explicit preview text."""

    def __init__(
        self,
        narrations: NarrationApplicationService,
        backend: PreviewBackend,
    ) -> None:
        self._narrations = narrations
        self._backend = backend

    def new_cancellation_token(self) -> PreviewCancellation:
        return self._backend.new_cancellation_token()

    def preview(
        self,
        request: PreviewRequest,
        *,
        cancellation: PreviewCancellation | None = None,
    ) -> PreviewResult:
        if request.chapter is not None or request.paragraph is not None:
            raise InputValidationError(
                "Chapter-derived previews are unavailable until Readio exposes "
                "a public source excerpt API."
            )
        text = (request.text or "").strip()
        if not text:
            raise InputValidationError("Preview text cannot be blank.")

        narration_id = (
            "primary" if request.narration_id is None else request.narration_id
        )
        paths = ProjectPaths.for_root(request.project)
        profile = self._narrations.profile_path(paths, narration_id)
        token = (
            cancellation if cancellation is not None else self.new_cancellation_token()
        )
        audio = self._backend.synthesize_preview(
            text=text,
            profile=profile,
            cancellation=token,
        )
        return PreviewResult(
            narration_id=narration_id,
            excerpt=PreviewExcerpt(text=text),
            audio=audio,
        )
