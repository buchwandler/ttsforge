from __future__ import annotations

from types import SimpleNamespace

import readio.api as readio_api

from ttsforge.application.catalog import EngineChoiceView, EngineOptionView
from ttsforge.application.catalog_service import CatalogApplicationService
from ttsforge.application.models import SpacyModelView


class FakeCatalogBackend:
    def list_engines(self) -> tuple[readio_api.EngineInfo, ...]:
        return (
            readio_api.EngineInfo(
                id="kokoro",
                version=None,
                installed=True,
                runnable=True,
                features=("named_voices",),
            ),
        )

    def list_targets(self, **kwargs: object) -> tuple[readio_api.TargetInfo, ...]:
        return (
            readio_api.TargetInfo(
                id="target-a",
                languages=("en-US",),
                status="ready",
                runtime_available=True,
                default_voice="voice-a",
                voice_count=2,
                qualities=(),
                voice_mode="named",
                sample_rate=24000,
                features=("voices",),
                reference_only=False,
            ),
        )

    def list_engine_options(
        self, engine: str, *, target: str | None = None
    ) -> tuple[readio_api.EngineOptionInfo, ...]:
        return (
            readio_api.EngineOptionInfo(
                name="quality",
                value_type="string",
                required=False,
                default="standard",
                choices=("standard", "high"),
                minimum=None,
                maximum=None,
                description="Synthesis quality",
                identity_affecting=True,
                runtime_only=False,
            ),
        )

    def list_voices(self, **kwargs: object) -> tuple[readio_api.VoiceInfo, ...]:
        return (
            readio_api.VoiceInfo(
                "voice-a", "en-US", "en-US", "English", "female", "builtin", True, True
            ),
            readio_api.VoiceInfo(
                "voice-b", "en-US", "en-US", "English", "male", "builtin", False, True
            ),
        )

    def list_spacy_models(self, language: str) -> tuple[SpacyModelView, ...]:
        return (self.inspect_spacy_model(language, "sm"),)

    def inspect_spacy_model(self, language: str, tier: str) -> SpacyModelView:
        return SpacyModelView(language, tier, "en_core_web_sm", True, "3.8", "3.8.0")

    def ensure_spacy_model(
        self, language: str, tier: str, *, offline: bool = False
    ) -> SpacyModelView:
        return self.inspect_spacy_model(language, tier)

    def inspect_voice(self, selector: str, *, language: str | None = None) -> object:
        return SimpleNamespace(id=selector, language=language)


def test_catalog_service_normalizes_engine_target_voice_and_options() -> None:
    service = CatalogApplicationService(FakeCatalogBackend())

    assert service.engines() == (
        EngineChoiceView(
            id="kokoro",
            version=None,
            installed=True,
            runnable=True,
            features=("voices",),
            reason=None,
        ),
    )
    targets = service.targets(engine="kokoro", language="en-US")
    assert targets[0].id == "target-a"
    assert targets[0].voice_count == 2
    voices = service.voices(engine="kokoro", target="target-a", language="en-US")
    assert [voice.id for voice in voices] == ["voice-a", "voice-b"]
    assert [voice.default for voice in voices] == [True, False]
    assert service.engine_options("kokoro", target="target-a") == (
        EngineOptionView(
            name="quality",
            value_type="string",
            required=False,
            default="standard",
            choices=("standard", "high"),
            minimum=None,
            maximum=None,
            description="Synthesis quality",
            identity_affecting=True,
            runtime_only=False,
        ),
    )


def test_catalog_service_exposes_spacy_and_inspected_voice_views() -> None:
    service = CatalogApplicationService(FakeCatalogBackend())

    assert service.spacy_models("en-US")[0].tier == "sm"
    assert service.ensure_spacy_model("en-US", "sm").installed
    inspected = service.inspect_voice("voice-a", language="en-US")
    assert inspected is not None
    assert inspected.id == "voice-a"
