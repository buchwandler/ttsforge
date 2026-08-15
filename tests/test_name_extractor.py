import sys
import types

from ttsforge import name_extractor


def test_spacy_model_cached(monkeypatch) -> None:
    calls = {"count": 0}

    class FakeEnt:
        def __init__(self, text: str, label: str) -> None:
            self.text = text
            self.label_ = label

    class FakeDoc:
        def __init__(self, text: str) -> None:
            self.ents = [FakeEnt("Alice", "PERSON")]

    class FakeNLP:
        def pipe(self, chunks, batch_size=4):
            for chunk in chunks:
                yield FakeDoc(chunk)

    def fake_load(model_name: str):
        calls["count"] += 1
        return FakeNLP()

    fake_spacy = types.SimpleNamespace(load=fake_load)
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)

    name_extractor._get_nlp.cache_clear()

    text = "Alice went to Wonderland."
    name_extractor.extract_names_from_text(text)
    name_extractor.extract_names_from_text(text)

    assert calls["count"] == 1


def test_generate_phoneme_suggestions_uses_kokorog2p_boundary() -> None:
    names = {"Alice": 4, "Wonderland": 2}
    suggestions = name_extractor.generate_phoneme_suggestions(names)
    repeated = name_extractor.generate_phoneme_suggestions(names)

    assert set(suggestions) == {"Alice", "Wonderland"}
    assert suggestions["Alice"]["occurrences"] == 4
    assert suggestions["Alice"]["phoneme"]
    assert suggestions["Alice"]["suggestion_quality"] == "auto"
    assert suggestions["Wonderland"]["phoneme"]
    assert repeated == suggestions


def test_generate_phoneme_suggestions_preserves_existing_error_policy(
    monkeypatch,
) -> None:
    def fail_phonemize(*_args, **_kwargs):
        raise RuntimeError("phonemizer unavailable")

    import kokorog2p

    monkeypatch.setattr(kokorog2p, "phonemize", fail_phonemize)
    suggestions = name_extractor.generate_phoneme_suggestions({"Alice": 1})

    assert suggestions["Alice"] == {
        "phoneme": "FIXME",
        "occurrences": 1,
        "suggestion_quality": "error",
        "error": "phonemizer unavailable",
    }
