"""Tests for source-aware model and provider status rendering."""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from ttsforge.cli import utility_light
from ttsforge.cli.commands_utility import _close_pipeline_and_backend


@dataclass
class _Assets:
    source: str
    variant: str
    quality: str
    config: Path | None
    model: Path
    voices: Path
    missing: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing


def _assets(source: str, *, complete: bool, config: Path | None = None) -> _Assets:
    missing = () if complete else ("model", "voices")
    return _Assets(
        source=source,
        variant="v1.0",
        quality="fp32",
        config=(
            config
            if config is not None
            else (None if source == "github" else Path(f"/{source}/config.json"))
        ),
        model=Path(f"/{source}/model.onnx"),
        voices=Path(f"/{source}/voices.bin"),
        missing=missing,
    )


def test_github_complete_set_is_reported_downloaded(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "pykokoro.model_assets.get_model_asset_paths",
        lambda **kwargs: _assets(kwargs["source"], complete=True),
    )
    utility_light._show_model_status(
        {"model_source": "github", "model_variant": "v1.0", "model_quality": "fp32"}
    )
    output = capsys.readouterr().out
    assert "github / v1.0 / fp32" in output
    assert "ONNX Models" in output and "Downloaded" in output
    assert "config.json: embedded / not required" in output


def test_pykokoro_asset_api_owns_source_specific_voice_filenames() -> None:
    from pykokoro.model_assets import get_model_asset_paths

    github = get_model_asset_paths(source="github", variant="v1.0", quality="fp32")
    huggingface = get_model_asset_paths(
        source="huggingface", variant="v1.0", quality="fp32"
    )
    assert github.voices.name == "voices-v1.0.npz"
    assert huggingface.voices.name == "voices.bin.npz"


def test_incomplete_configured_source_reports_complete_alternate(
    monkeypatch, capsys
) -> None:
    def fake_assets(**kwargs):
        return _assets(kwargs["source"], complete=kwargs["source"] == "github")

    monkeypatch.setattr("pykokoro.model_assets.get_model_asset_paths", fake_assets)
    utility_light._show_model_status(
        {
            "model_source": "huggingface",
            "model_variant": "v1.0",
            "model_quality": "fp32",
        }
    )
    output = capsys.readouterr().out
    assert "Configured model set: huggingface / v1.0 / fp32" in output
    assert "Found a complete alternate model set" in output
    assert "config --set model_source github" in output


def test_provider_probe_failure_does_not_hide_model_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "pykokoro.model_assets.get_model_asset_paths",
        lambda **kwargs: _assets("github", complete=True),
    )
    monkeypatch.setattr(
        "pykokoro.onnx_session.get_available_execution_providers",
        lambda: (_ for _ in ()).throw(RuntimeError("probe failed")),
    )
    config = {
        "model_source": "github",
        "model_variant": "v1.0",
        "model_quality": "fp32",
    }
    utility_light._show_model_status(config)
    utility_light._show_provider_status(config)
    output = capsys.readouterr().out
    assert "ONNX Models" in output and "Downloaded" in output
    assert "ONNX Runtime Providers" in output and "Status unavailable" in output


def test_provider_status_reports_available_configured_and_resolved(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        "pykokoro.onnx_session.get_available_execution_providers",
        lambda: ("OpenVINOExecutionProvider", "CPUExecutionProvider"),
    )
    monkeypatch.setattr(
        "pykokoro.onnx_session.resolve_execution_provider",
        lambda configured: (
            "OpenVINOExecutionProvider"
            if configured == "openvino"
            else "CPUExecutionProvider"
        ),
    )

    utility_light._show_provider_status({"onnx_provider": "openvino"})

    output = capsys.readouterr().out
    assert "Available: OpenVINOExecutionProvider, CPUExecutionProvider" in output
    assert "Configured: openvino" in output
    assert "Resolved: OpenVINOExecutionProvider" in output


def test_direct_pipeline_cleanup_closes_pipeline_before_backend() -> None:
    events: list[str] = []

    class Pipeline:
        def close(self) -> None:
            events.append("pipeline")

    class Backend:
        def close(self) -> None:
            events.append("backend")

    _close_pipeline_and_backend(Pipeline(), Backend())

    assert events == ["pipeline", "backend"]


def test_direct_pipeline_cleanup_closes_backend_after_pipeline_failure() -> None:
    events: list[str] = []

    class Pipeline:
        def close(self) -> None:
            events.append("pipeline")
            raise RuntimeError("pipeline failure")

    class Backend:
        def close(self) -> None:
            events.append("backend")

    try:
        _close_pipeline_and_backend(Pipeline(), Backend())
    except RuntimeError as exc:
        assert str(exc) == "pipeline failure"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("pipeline failure was swallowed")

    assert events == ["pipeline", "backend"]


def test_demo_combined_gap_uses_exact_generated_silence(monkeypatch, tmp_path) -> None:
    from ttsforge.cli import commands_utility

    class Backend:
        def close(self) -> None:
            pass

    class Result(SimpleNamespace):
        def release_audio(self) -> None:
            pass

    class Pipeline:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def run(self, text, *, voice, lang):
            del text, voice, lang
            return Result(audio=np.ones(4, dtype=np.float32), sample_rate=24000)

        def close(self) -> None:
            pass

    monkeypatch.setattr(commands_utility, "load_config", dict)
    monkeypatch.setattr(
        commands_utility, "resolve_onnx_provider", lambda *args, **kwargs: "cpu"
    )
    monkeypatch.setattr(
        commands_utility, "build_standard_pipeline", lambda **kwargs: Pipeline()
    )

    output = tmp_path / "demo.wav"
    commands_utility.demo(
        SimpleNamespace(obj={}),
        output=output,
        language=None,
        voices_filter="af_heart,af_bella",
        speed=1.0,
        use_gpu=None,
        provider=None,
        silence=0.125,
        text="Demo {voice}",
        separate=False,
        blend=None,
        blend_presets=False,
        play_audio=False,
    )

    rendered, sample_rate = sf.read(output, dtype="float32")
    assert sample_rate == 24000
    assert rendered.shape == (4 + int(0.125 * 24000) + 4,)


def test_default_config_resolves_automatic_model_profile(monkeypatch, capsys) -> None:
    """Default config must resolve a concrete model set before asset lookup."""
    captured_args: dict[str, object] = {}

    def fake_asset_paths(**kwargs):
        captured_args.update(kwargs)
        return _assets(kwargs["source"], complete=True)

    monkeypatch.setattr("pykokoro.model_assets.get_model_asset_paths", fake_asset_paths)

    utility_light._show_model_status(
        {
            "model_source": None,
            "model_variant": None,
            "model_quality": None,
            "default_language": "a",
        }
    )

    assert "source" in captured_args
    assert "variant" in captured_args
    assert "quality" in captured_args
    assert captured_args["source"] is not None
    assert captured_args["variant"] is not None
    assert captured_args["quality"] is not None
    assert captured_args["quality"] != "None"
    output = capsys.readouterr().out
    assert "Status unavailable" not in output


def test_explicit_config_model_status_passes_explicit_values(
    monkeypatch, capsys
) -> None:
    """Explicit config values remain explicit in model-status display."""
    captured_args: dict[str, object] = {}

    def fake_asset_paths(**kwargs):
        captured_args.update(kwargs)
        return _assets(kwargs["source"], complete=True)

    monkeypatch.setattr("pykokoro.model_assets.get_model_asset_paths", fake_asset_paths)

    utility_light._show_model_status(
        {
            "model_source": "github",
            "model_variant": "v1.2-de-martin",
            "model_quality": "fp16",
            "default_language": "d",
        }
    )

    assert captured_args["source"] == "github"
    assert captured_args["variant"] == "v1.2-de-martin"
    assert captured_args["quality"] == "fp16"
    output = capsys.readouterr().out
    assert "v1.2-de-martin" in output
    assert "fp16" in output


def _make_fake_inventory(*model_specs):
    """Create a fake PyKokoro inventory from model spec tuples."""
    from types import SimpleNamespace

    return SimpleNamespace(
        models=[
            SimpleNamespace(source=src, model_id=mid, languages=langs, voices=vs)
            for src, mid, langs, vs in model_specs
        ]
    )


def test_voices_uses_discover_models(monkeypatch, capsys) -> None:
    """voices() must call pykokoro.discover_models()."""
    called = []

    def fake_discover_models():
        called.append(True)
        return _make_fake_inventory(("github", "v1.0", ("en",), ("af_heart",)))

    monkeypatch.setattr("pykokoro.discover_models", fake_discover_models)
    utility_light.voices(None)
    assert called
    output = capsys.readouterr().out
    assert "af_heart" in output


def test_voices_german_metadata_visible(monkeypatch, capsys) -> None:
    """German voices from the Martin profile must appear in output."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(
            ("github", "v1.0", ("en",), ("af_heart",)),
            ("github", "v1.2-de-martin", ("de",), ("martin",)),
        ),
    )
    utility_light.voices(None)
    output = capsys.readouterr().out
    assert "martin" in output
    assert "af_heart" in output


def test_voices_filter_by_language_uses_metadata(monkeypatch, capsys) -> None:
    """Language filter must use model language metadata, not voice prefixes."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(
            ("github", "v1.0", ("en",), ("af_heart",)),
            ("github", "v1.2-de-martin", ("de",), ("martin",)),
        ),
    )
    utility_light.voices("d")
    output = capsys.readouterr().out
    assert "martin" in output
    assert "af_heart" not in output


def test_voices_non_prefix_names_displayed(monkeypatch, capsys) -> None:
    """Non-prefix voice names must appear correctly."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(
            ("github", "v1.2-de-martin", ("de",), ("martin",)),
            ("github", "sv-joakim", ("sv",), ("Alice", "Anton")),
        ),
    )
    utility_light.voices(None)
    output = capsys.readouterr().out
    assert "martin" in output
    assert "Alice" in output
    assert "Anton" in output


def test_voices_no_onnx_initialization(monkeypatch) -> None:
    """voices() must not import ONNX runtime modules."""
    import sys

    onnx_modules_before = {m for m in sys.modules if m.startswith("onnxruntime")}
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(),
    )
    utility_light.voices(None)
    onnx_modules_after = {m for m in sys.modules if m.startswith("onnxruntime")}
    assert onnx_modules_after == onnx_modules_before


def test_voices_duplicate_voices_across_profiles(monkeypatch, capsys) -> None:
    """Voices appearing in multiple models get languages merged."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(
            ("github", "v1.0", ("en",), ("af_heart",)),
            ("github", "v1.1", ("en", "zh"), ("af_heart", "zf_xia")),
        ),
    )
    utility_light.voices(None)
    output = capsys.readouterr().out
    # af_heart appears in both models with "en"; v1.1 also has "zh"
    assert output.count("af_heart") == 1
    # "en" primary language maps to both American and British English;
    # "zh" maps to Mandarin Chinese.  Table column may wrap long strings
    # so check each expected token separately.
    assert "American English" in output
    assert "Mandarin Chinese" in output or "Mandarin" in output


def test_voices_metadata_unavailable_shows_error(monkeypatch, capsys) -> None:
    """When discover_models raises, voices must show a clear error message."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: (_ for _ in ()).throw(RuntimeError("metadata broken")),
    )
    utility_light.voices(None)
    output = capsys.readouterr().out
    assert "Failed to load voice metadata" in output
    assert "metadata broken" in output


def test_voices_empty_inventory(monkeypatch, capsys) -> None:
    """Empty metadata inventory must display a clear message."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(),
    )
    utility_light.voices(None)
    output = capsys.readouterr().out
    assert "No voices found in metadata" in output


def test_voices_marks_automatic_default_for_language(monkeypatch, capsys) -> None:
    """When filtering by language, the automatic voice is marked as default."""
    monkeypatch.setattr(
        "pykokoro.discover_models",
        lambda: _make_fake_inventory(
            ("github", "v1.2-de-martin", ("de",), ("martin",)),
        ),
    )
    utility_light.voices("d")
    output = capsys.readouterr().out
    assert "martin" in output
    assert "Yes" in output
