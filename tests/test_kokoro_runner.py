"""Tests for ttsforge.kokoro_runner."""

from pathlib import Path

import numpy as np
from pykokoro.short_sentence_handler import ShortSentenceConfig

from ttsforge.kokoro_runner import KokoroRunner, KokoroRunOptions


def test_kokoro_run_options_accepts_short_sentence_override():
    opts = KokoroRunOptions(
        voice="af_heart",
        speed=1.0,
        use_gpu=False,
        pause_clause=0.3,
        pause_sentence=0.5,
        pause_paragraph=0.9,
        pause_variance=0.05,
        enable_short_sentence=True,
    )

    assert opts.enable_short_sentence is True


def test_kokoro_runner_passes_short_sentence_config_to_backend(monkeypatch):
    captured: dict[str, object] = {}
    short_sentence_config = ShortSentenceConfig()

    class FakeKokoro:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    def fake_build_pipeline(**kwargs):
        return object()

    monkeypatch.setattr("ttsforge.kokoro_runner.Kokoro", FakeKokoro)
    monkeypatch.setattr("ttsforge.kokoro_runner.build_pipeline", fake_build_pipeline)

    opts = KokoroRunOptions(
        voice="af_heart",
        speed=1.0,
        use_gpu=False,
        pause_clause=0.3,
        pause_sentence=0.5,
        pause_paragraph=0.9,
        pause_variance=0.05,
        model_path=Path("model.onnx"),
        voices_path=Path("voices.bin"),
        short_sentence_config=short_sentence_config,
    )

    runner = KokoroRunner(opts, log=lambda message, level="info": None)
    runner.ensure_ready()

    assert captured["short_sentence_config"] is short_sentence_config


def test_kokoro_runner_passes_provider_to_backend(monkeypatch):
    captured: dict[str, object] = {}

    class FakeKokoro:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("ttsforge.kokoro_runner.Kokoro", FakeKokoro)
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.build_pipeline", lambda **kwargs: object()
    )
    opts = _runner_options(
        onnx_provider="nnapi",
        model_path=Path("model.onnx"),
        voices_path=Path("voices.bin"),
    )
    KokoroRunner(opts, log=lambda message, level="info": None).ensure_ready()
    assert captured["provider"] == "nnapi"
    assert "use_gpu" not in captured


def test_kokoro_runner_forwards_short_sentence_disable_override():
    captured: dict[str, object] = {}

    class FakePipeline:
        def run(self, text_or_ssmd: str, *, generation):
            captured["text"] = text_or_ssmd
            captured["enable_short_sentence"] = generation.enable_short_sentence
            return type("Result", (), {"audio": np.array([], dtype=np.float32)})()

    opts = KokoroRunOptions(
        voice="af_heart",
        speed=1.0,
        use_gpu=False,
        pause_clause=0.3,
        pause_sentence=0.5,
        pause_paragraph=0.9,
        pause_variance=0.05,
        enable_short_sentence=False,
    )

    runner = KokoroRunner(opts, log=lambda message, level="info": None)
    runner._pipeline = FakePipeline()

    runner.synthesize("No.", lang_code="en-us", pause_mode="auto")

    assert captured["enable_short_sentence"] is False


def test_kokoro_runner_forwards_random_seed():
    captured: dict[str, object] = {}

    class FakePipeline:
        def run(self, text_or_ssmd: str, *, generation):
            captured["random_seed"] = generation.random_seed
            return type("Result", (), {"audio": np.array([], dtype=np.float32)})()

    opts = KokoroRunOptions(
        voice="af_heart",
        speed=1.0,
        use_gpu=False,
        pause_clause=0.3,
        pause_sentence=0.5,
        pause_paragraph=0.9,
        pause_variance=0.05,
        random_seed=1234,
    )

    runner = KokoroRunner(opts, log=lambda message, level="info": None)
    runner._pipeline = FakePipeline()

    runner.synthesize("No.", lang_code="en-us", pause_mode="auto")

    assert captured["random_seed"] == 1234


def _runner_options(**kwargs):
    values = {
        "voice": "af_heart",
        "speed": 1.0,
        "use_gpu": False,
        "pause_clause": 0.3,
        "pause_sentence": 0.5,
        "pause_paragraph": 0.9,
        "pause_variance": 0.05,
        "model_source": "github",
        "model_variant": "v1.0",
        "model_quality": "fp32",
    }
    values.update(kwargs)
    return KokoroRunOptions(**values)


def test_runner_readiness_uses_source_variant_quality_and_skips_complete_download(
    monkeypatch,
):
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        "ttsforge.kokoro_runner.are_models_downloaded",
        lambda **kwargs: calls.update(kwargs) or True,
    )
    monkeypatch.setattr("ttsforge.kokoro_runner.Kokoro", lambda **kwargs: object())
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.build_pipeline", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.download_all_models_github",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("downloaded")),
    )

    KokoroRunner(
        _runner_options(), log=lambda message, level="info": None
    ).ensure_ready()
    assert calls == {"quality": "fp32", "source": "github", "variant": "v1.0"}


def test_runner_downloads_only_incomplete_configured_source(monkeypatch):
    calls: dict[str, object] = {}
    downloads: list[str] = []
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.are_models_downloaded",
        lambda **kwargs: calls.update(kwargs) or False,
    )
    monkeypatch.setattr("ttsforge.kokoro_runner.Kokoro", lambda **kwargs: object())
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.build_pipeline", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.download_all_models_github",
        lambda **kwargs: downloads.append("github"),
    )

    KokoroRunner(
        _runner_options(), log=lambda message, level="info": None
    ).ensure_ready()
    assert calls == {"quality": "fp32", "source": "github", "variant": "v1.0"}
    assert downloads == ["github"]


def test_runner_downloads_incomplete_huggingface_set(monkeypatch):
    downloads: list[str] = []
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.are_models_downloaded", lambda **kwargs: False
    )
    monkeypatch.setattr("ttsforge.kokoro_runner.Kokoro", lambda **kwargs: object())
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.build_pipeline", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        "ttsforge.kokoro_runner.download_all_models",
        lambda **kwargs: downloads.append("huggingface"),
    )
    opts = _runner_options(model_source="huggingface")
    KokoroRunner(opts, log=lambda message, level="info": None).ensure_ready()
    assert downloads == ["huggingface"]
