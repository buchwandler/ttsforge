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
        "use_spacy": None,
        "model": "en_core_web_lg",
        "size": "sm",
    }


def test_request_policy_distinguishes_auto_strict_and_disabled() -> None:
    automatic = SpacyModelRequest()
    strict = SpacyModelRequest(use_spacy=True)
    explicit = SpacyModelRequest(size="lg")
    disabled = SpacyModelRequest(use_spacy=False, model="auto", size="lg")

    assert automatic.is_automatic is True
    assert automatic.strict is False
    assert automatic.disabled is False
    assert strict.strict is True
    assert explicit.strict is True
    assert disabled.disabled is True
    assert disabled.model is None
    assert disabled.size is None


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


def test_automatic_request_falls_back_when_no_model_is_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=()),
    )
    selection = resolve_spacy_model_for_component(
        language="en",
        request=SpacyModelRequest(),
        component="sentence",
    )
    assert selection.model is None
    assert selection.available is False


def test_strict_boolean_and_exact_tier_requests_fail_without_a_model(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "ttsforge.spacy_policy.resolve_spacy_model",
        lambda **_: SimpleNamespace(candidates=()),
    )
    for request in (SpacyModelRequest(use_spacy=True), SpacyModelRequest(size="lg")):
        with pytest.raises(RuntimeError, match="No compatible loadable spaCy model"):
            resolve_spacy_model_for_component(
                language="en",
                request=request,
                component="sentence",
            )


def test_disabled_request_does_not_query_model_discovery(monkeypatch) -> None:
    def fail_if_called(**_):
        raise AssertionError("disabled policy must not discover models")

    monkeypatch.setattr("ttsforge.spacy_policy.resolve_spacy_model", fail_if_called)
    selection = resolve_spacy_model_for_component(
        language="en",
        request=SpacyModelRequest(use_spacy=False),
        component="sentence",
    )
    assert selection.model is None
    assert selection.available is False


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
