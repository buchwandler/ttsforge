"""Regression tests for TTSForge's released spaCy model policy adapter."""

from types import SimpleNamespace

import pytest

from ttsforge.conversion import ConversionOptions
from ttsforge.spacy_policy import (
    SPACY_POLICY_VERSION,
    SpacyCapabilityError,
    SpacyModelRequest,
    normalize_spacy_model,
    normalize_spacy_model_size,
    resolve_spacy_model_for_component,
)


def test_request_normalizes_without_discovery() -> None:
    assert normalize_spacy_model("") is None
    assert normalize_spacy_model("auto") is None
    assert normalize_spacy_model_size("auto") is None
    assert normalize_spacy_model_size("LG") == "lg"
    assert SpacyModelRequest(model=" en_core_web_lg ", size="sm").as_dict() == {
        "use_spacy": True,
        "model": "en_core_web_lg",
        "size": "sm",
    }


def test_invalid_tier_is_rejected_without_model_lookup() -> None:
    with pytest.raises(ValueError, match="sm, md, lg, trf"):
        normalize_spacy_model_size("tiny")


def test_automatic_selection_uses_first_ranked_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=("en_core_web_lg", "en_core_web_sm")),
    )
    monkeypatch.setattr(
        "ttsforge.spacy_policy._load_model",
        lambda model: SimpleNamespace(pipe_names=["ner", "tagger"]),
    )

    selection = resolve_spacy_model_for_component(
        language="en-us",
        request=SpacyModelRequest(),
        component="name",
        include_all=True,
    )

    assert selection.model == "en_core_web_lg"
    assert selection.language == "en-us"
    assert selection.policy == SPACY_POLICY_VERSION


def test_exact_model_wins_over_size_and_is_strict(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=("en_core_web_lg",)),
    )
    monkeypatch.setattr(
        "ttsforge.spacy_policy._load_model",
        lambda model: seen.append(model) or SimpleNamespace(pipe_names=["ner"]),
    )

    selection = resolve_spacy_model_for_component(
        language="en",
        request=SpacyModelRequest(model="en_core_web_sm", size="lg"),
        component="name",
    )

    assert selection.model == "en_core_web_sm"
    assert seen == ["en_core_web_sm"]


def test_automatic_name_selection_skips_missing_capability(monkeypatch) -> None:
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=("en_core_web_lg", "en_core_web_sm")),
    )

    def fake_load(model: str):
        if model.endswith("lg"):
            return SimpleNamespace(pipe_names=["tagger"])
        return SimpleNamespace(pipe_names=["ner", "tagger"])

    monkeypatch.setattr("ttsforge.spacy_policy._load_model", fake_load)
    selection = resolve_spacy_model_for_component(
        language="en",
        request=SpacyModelRequest(),
        component="name",
    )
    assert selection.model == "en_core_web_sm"


def test_exact_model_missing_capability_is_strict(monkeypatch) -> None:
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=("custom",)),
    )
    monkeypatch.setattr(
        "ttsforge.spacy_policy._load_model",
        lambda model: SimpleNamespace(pipe_names=["tagger"]),
    )
    with pytest.raises(SpacyCapabilityError, match="lacks required ner"):
        resolve_spacy_model_for_component(
            language="en",
            request=SpacyModelRequest(model="custom"),
            component="name",
        )


def test_conversion_options_do_not_discover_models(monkeypatch) -> None:
    def fail_if_called(**_):
        raise AssertionError("availability lookup must not happen in dataclass init")

    monkeypatch.setattr("ttsforge.spacy_policy.resolve_spacy_model", fail_if_called)
    automatic = ConversionOptions()
    disabled = ConversionOptions(
        use_spacy=False, spacy_model="auto", spacy_model_size="lg"
    )
    assert automatic.spacy_model is None
    assert automatic.spacy_model_size is None
    assert disabled.spacy_model is None
    assert disabled.spacy_model_size is None
