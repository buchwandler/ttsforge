"""Frontend-neutral catalog discovery and presentation normalization."""

from __future__ import annotations

from typing import Protocol

from .catalog import (
    EngineChoiceView,
    EngineInfoRecord,
    EngineOptionInfoRecord,
    EngineOptionView,
    TargetChoiceView,
    TargetInfoRecord,
    VoiceChoiceView,
    VoiceInfoRecord,
    engine_choice_view,
    engine_option_view,
    inspected_voice_choice_view,
    target_choice_view,
    voice_choice_view,
)
from .models import SpacyModelView


class CatalogBackend(Protocol):
    def list_engines(self) -> tuple[EngineInfoRecord, ...]: ...

    def list_targets(
        self,
        *,
        engine: str,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[TargetInfoRecord, ...]: ...

    def list_engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[EngineOptionInfoRecord, ...]: ...

    def list_voices(
        self,
        *,
        engine: str | None = None,
        target: str | None = None,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[VoiceInfoRecord, ...]: ...

    def list_spacy_models(self, language: str) -> tuple[SpacyModelView, ...]: ...

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView: ...

    def ensure_spacy_model(
        self, language: str, tier: str, *, offline: bool = False
    ) -> SpacyModelView: ...

    def inspect_voice(
        self, selector: str, *, language: str | None = None
    ) -> object: ...


class CatalogApplicationService:
    """Normalize discovery results into stable TTSForge application views."""

    def __init__(self, backend: CatalogBackend) -> None:
        self._backend = backend

    def engines(self) -> tuple[EngineChoiceView, ...]:
        return tuple(
            engine_choice_view(engine) for engine in self._backend.list_engines()
        )

    def targets(
        self,
        *,
        engine: str,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[TargetChoiceView, ...]:
        values = self._backend.list_targets(
            engine=engine,
            language=language,
            offline=offline,
            refresh=refresh,
        )
        return tuple(target_choice_view(target) for target in values)

    def engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[EngineOptionView, ...]:
        return tuple(
            engine_option_view(option)
            for option in self._backend.list_engine_options(engine, target=target)
        )

    def voices(
        self,
        *,
        engine: str | None = None,
        target: str | None = None,
        language: str | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> tuple[VoiceChoiceView, ...]:
        return tuple(
            voice_choice_view(voice)
            for voice in self._backend.list_voices(
                engine=engine,
                target=target,
                language=language,
                offline=offline,
                refresh=refresh,
            )
        )

    def spacy_models(self, language: str) -> tuple[SpacyModelView, ...]:
        return self._backend.list_spacy_models(language)

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView:
        return self._backend.inspect_spacy_model(language, tier)

    def ensure_spacy_model(
        self, language: str, tier: str, *, offline: bool = False
    ) -> SpacyModelView:
        return self._backend.ensure_spacy_model(language, tier, offline=offline)

    def inspect_voice(
        self, selector: str, *, language: str | None = None
    ) -> VoiceChoiceView | None:
        return inspected_voice_choice_view(
            self._backend.inspect_voice(selector, language=language)
        )
