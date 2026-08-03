"""Contract checks for the public PyKokoro paragraph-unit API."""

import inspect

from pykokoro import (
    AudioUnitDescriptor,
    AudioUnitResult,
    KokoroPipeline,
    PreparedAudioUnits,
)


def test_public_paragraph_unit_contract_is_available() -> None:
    prepare_units = KokoroPipeline.prepare_units
    signature = inspect.signature(prepare_units)

    assert signature.parameters["unit"].default == "paragraph"
    assert "text" in signature.parameters
    assert hasattr(PreparedAudioUnits, "units")
    assert hasattr(PreparedAudioUnits, "render")
    assert "skip_indices" in inspect.signature(PreparedAudioUnits.render).parameters
    assert hasattr(AudioUnitDescriptor, "text_hash")
    assert hasattr(AudioUnitResult, "release_audio")


def test_public_prepare_units_rejects_unknown_unit_before_inference() -> None:
    """The public boundary must fail clearly instead of guessing another unit."""

    pipeline = object.__new__(KokoroPipeline)
    try:
        pipeline.prepare_units("text", unit="chapter")
    except ValueError as exc:
        assert "Unsupported audio unit kind" in str(exc)
    else:  # pragma: no cover - protects the dependency contract if it regresses
        raise AssertionError("PyKokoro accepted an unsupported audio unit")
