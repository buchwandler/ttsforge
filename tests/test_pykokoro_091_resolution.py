"""Focused PyKokoro 0.9.1 resolution-contract tests.

These tests pin TTSForge's metadata-only default resolution to the public
``pykokoro.resolve_pipeline_config`` boundary added in 0.9.1.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ttsforge.cli.backend_config import (
    ResolvedPipelineDefaults,
    resolve_model_source_and_variant,
    resolve_pykokoro_pipeline_defaults,
)
from ttsforge.kokoro_lang import get_onnx_lang_code, get_pykokoro_language


def test_public_resolver_is_importable() -> None:
    """resolve_pipeline_config must be part of the public pykokoro API."""
    import pykokoro
    from pykokoro import resolve_pipeline_config

    assert pykokoro.__version__ == "0.9.1"
    assert callable(resolve_pipeline_config)


def test_german_document_resolves_martin_profile() -> None:
    """German resolves the verified v1.2-de-martin profile and voice."""
    resolved = resolve_pykokoro_pipeline_defaults(ttsforge_language="d")

    assert resolved.language == "de"
    assert resolved.model_source == "github"
    assert resolved.model_variant == "v1.2-de-martin"
    assert resolved.model_quality == "fp32"
    assert resolved.voice == "martin"


def test_ttsforge_language_codes_map_to_document_languages() -> None:
    """The TTSForge one-character codes reach PyKokoro as BCP-47 languages."""
    assert get_onnx_lang_code("d") == "de"
    assert get_onnx_lang_code("a") == "en-us"
    assert get_onnx_lang_code("b") == "en-gb"
    assert get_pykokoro_language("d") == "de"
    assert get_pykokoro_language("a") == "en-us"
    assert get_pykokoro_language("b") == "en-gb"
    assert get_onnx_lang_code("d") == "de"

    resolved = resolve_pykokoro_pipeline_defaults(ttsforge_language="d")
    assert resolved.language == get_pykokoro_language("d")


def test_matches_upstream_public_resolver() -> None:
    """TTSForge's helper must return exactly what the public resolver returns."""
    from pykokoro import GenerationConfig, PipelineConfig, resolve_pipeline_config

    upstream = resolve_pipeline_config(
        PipelineConfig(generation=GenerationConfig(lang="de"))
    )
    ours = resolve_pykokoro_pipeline_defaults(ttsforge_language="d")

    assert ours.language == upstream.generation.lang
    assert ours.model_source == upstream.model_source
    assert ours.model_variant == upstream.model_variant
    assert ours.model_quality == upstream.model_quality
    assert ours.voice == upstream.voice


def test_explicit_values_are_preserved() -> None:
    """Explicit model and voice requests must remain explicit."""
    resolved = resolve_pykokoro_pipeline_defaults(
        ttsforge_language="d",
        voice="martin",
        model_source="github",
        model_variant="v1.2-de-martin",
        model_quality="fp16",
    )

    assert resolved.voice == "martin"
    assert resolved.model_source == "github"
    assert resolved.model_variant == "v1.2-de-martin"
    assert resolved.model_quality == "fp16"


def test_resolution_is_idempotent_for_the_same_ttsforge_code() -> None:
    """Resolving the same TTSForge language twice gives identical results."""
    first = resolve_pykokoro_pipeline_defaults(ttsforge_language="d")
    second = resolve_pykokoro_pipeline_defaults(ttsforge_language="d")
    assert first == second


def test_upstream_resolver_requires_document_language() -> None:
    from pykokoro import PipelineConfig, resolve_pipeline_config

    with pytest.raises(ValueError, match="document language"):
        resolve_pipeline_config(PipelineConfig())


def test_resolution_does_not_import_onnx_runtime() -> None:
    """Metadata resolution must stay dependency-light (no ONNX session)."""
    code = (
        "import sys; "
        "from ttsforge.cli.backend_config import resolve_pykokoro_pipeline_defaults; "
        "resolved = resolve_pykokoro_pipeline_defaults(ttsforge_language='d'); "
        "assert resolved.model_variant == 'v1.2-de-martin', resolved; "
        "offenders = [m for m in sys.modules "
        "if m.startswith('onnxruntime') or m == 'pykokoro.onnx_session']; "
        "assert not offenders, offenders"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_standard_resolution_has_no_private_model_profiles_import() -> None:
    """Standard default resolution must not use private upstream modules."""
    source = Path("ttsforge/cli/backend_config.py").read_text(encoding="utf-8")
    assert "model_profiles" not in source


def test_automatic_model_config_stays_none() -> None:
    """Automatic configuration keeps None instead of guessing defaults."""
    assert resolve_model_source_and_variant(
        {"model_source": None, "model_variant": None}
    ) == (None, None)
    assert resolve_model_source_and_variant({}) == (None, None)


def test_explicit_variant_is_validated_through_public_resolver() -> None:
    resolved = resolve_model_source_and_variant(
        {"model_source": "github", "model_variant": "v1.2-de-martin"}
    )
    assert resolved == ("github", "v1.2-de-martin")

    with pytest.raises(ValueError, match="Unknown model profile"):
        resolve_model_source_and_variant(
            {"model_source": "github", "model_variant": "bogus"}
        )


def test_resolved_record_is_immutable() -> None:
    resolved = resolve_pykokoro_pipeline_defaults(ttsforge_language="a")
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass
        resolved.model_variant = "v1.0"
    assert isinstance(resolved, ResolvedPipelineDefaults)
