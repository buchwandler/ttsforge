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
    assert github.voices.name == "voices-v1.0.bin"
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

    monkeypatch.setattr(commands_utility, "load_config", lambda: {})
    monkeypatch.setattr(
        commands_utility, "resolve_onnx_provider", lambda *args, **kwargs: "cpu"
    )
    monkeypatch.setattr(commands_utility, "Kokoro", lambda **kwargs: Backend())
    monkeypatch.setattr(commands_utility, "KokoroPipeline", Pipeline)
    monkeypatch.setattr(
        commands_utility, "OnnxPhonemeProcessorAdapter", lambda backend: backend
    )
    monkeypatch.setattr(
        commands_utility, "OnnxAudioGenerationAdapter", lambda backend: backend
    )
    monkeypatch.setattr(
        commands_utility, "OnnxAudioPostprocessingAdapter", lambda backend: backend
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
