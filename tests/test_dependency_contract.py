"""Focused checks for the supported PyKokoro/kokorog2p dependency boundary."""

from __future__ import annotations

from importlib.metadata import version

import kokorog2p
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from ttsforge.vocab import (
    decode,
    encode,
    filter_for_kokoro,
    get_vocab_info,
    ids_to_phonemes,
    load_vocab,
    phonemes_to_ids,
    validate_for_kokoro,
)


def test_supported_dependency_versions_are_installed() -> None:
    assert Version(version("pykokoro")) in SpecifierSet(">=0.8.4,<0.9")
    assert Version(version("kokorog2p")) in SpecifierSet(">=0.8.0,<0.9")


def test_written_to_spoken_preparation_reaches_g2p_without_ttsforge_rewrite() -> None:
    source = (
        "Dr. Smith will see you at 10:30 on 05/20/2023. "
        "The box weighs 5 kg and costs $10.99."
    )
    result = kokorog2p.phonemize(source, language="en-us", use_spacy=False)

    assert result.phonemes
    assert result.token_ids
    assert not result.warnings
    assert not any(character.isdigit() for character in result.phonemes)


def test_ttsforge_vocabulary_compatibility_layer_is_available() -> None:
    assert load_vocab()
    assert get_vocab_info()["backend"] == "kokorog2p"
    assert callable(encode)
    assert callable(decode)
    assert callable(validate_for_kokoro)
    assert callable(filter_for_kokoro)
    assert callable(phonemes_to_ids)
    assert callable(ids_to_phonemes)
