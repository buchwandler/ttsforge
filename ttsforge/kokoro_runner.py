# ttsforge/kokoro_runner.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

import numpy as np
from pykokoro import GenerationConfig, KokoroPipeline, PipelineConfig
from pykokoro.onnx_backend import (
    DEFAULT_MODEL_QUALITY,
    DEFAULT_MODEL_SOURCE,
    DEFAULT_MODEL_VARIANT,
    Kokoro,
    ModelQuality,
    ModelSource,
    ModelVariant,
    VoiceBlend,
    are_models_downloaded,
    download_all_models,
    download_all_models_github,
)
from pykokoro.pipeline import build_pipeline
from pykokoro.short_sentence_handler import ShortSentenceConfig
from pykokoro.stages.audio_generation.onnx import OnnxAudioGenerationAdapter
from pykokoro.stages.audio_postprocessing.onnx import OnnxAudioPostprocessingAdapter
from pykokoro.stages.phoneme_processing.onnx import OnnxPhonemeProcessorAdapter

from .short_sentence_stats import ShortSentenceStats
from .ssmd_support import SSMDPolicy, build_pykokoro_ssmd_config


@dataclass(slots=True)
class KokoroRunOptions:
    voice: str
    speed: float
    use_gpu: bool
    pause_clause: float
    pause_sentence: float
    pause_paragraph: float
    pause_variance: float
    random_seed: int | None = None
    enable_short_sentence: bool | None = None
    model_quality: ModelQuality | None = DEFAULT_MODEL_QUALITY
    model_source: ModelSource = DEFAULT_MODEL_SOURCE
    model_variant: ModelVariant = DEFAULT_MODEL_VARIANT
    model_path: Any | None = None
    voices_path: Any | None = None
    voice_blend: str | None = None
    voice_database: Any | None = None
    tokenizer_config: Any | None = None  # pykokoro.tokenizer.TokenizerConfig
    short_sentence_config: ShortSentenceConfig | None = None
    onnx_provider: str | None = None
    ssmd_policy: SSMDPolicy = field(default_factory=SSMDPolicy)

    def effective_onnx_provider(self) -> str:
        """Return the provider requested by this runner option set."""
        if self.onnx_provider is not None:
            return self.onnx_provider
        return "auto" if self.use_gpu else "cpu"


class KokoroRunner:
    class LogCallback(Protocol):
        def __call__(self, message: str, level: str = "info") -> None: ...

    def __init__(self, opts: KokoroRunOptions, log: KokoroRunner.LogCallback):
        self.opts = opts
        self.log = log
        self._kokoro: Kokoro | None = None
        self._pipeline: KokoroPipeline | None = None
        self._voice_style: str | VoiceBlend | None = None
        self.short_sentence_stats = ShortSentenceStats()

    def ensure_ready(self) -> None:
        if self._pipeline is not None:
            return

        if self.opts.model_path is None or self.opts.voices_path is None:
            model_quality = self.opts.model_quality or DEFAULT_MODEL_QUALITY
            model_source = self.opts.model_source or DEFAULT_MODEL_SOURCE
            models_ready = are_models_downloaded(
                quality=model_quality,
                source=model_source,
                variant=self.opts.model_variant,
            )
            if not models_ready and model_source == "github":
                self.log("Downloading ONNX model files from GitHub...")
                download_all_models_github(
                    variant=self.opts.model_variant,
                    quality=model_quality,
                )
            elif not models_ready:
                self.log("Downloading ONNX model files...")
                download_all_models(
                    variant=self.opts.model_variant,
                    quality=model_quality,
                )

        self._kokoro = Kokoro(
            model_path=self.opts.model_path,
            voices_path=self.opts.voices_path,
            provider=self.opts.effective_onnx_provider(),
            tokenizer_config=self.opts.tokenizer_config,
            short_sentence_config=self.opts.short_sentence_config,
            model_quality=self.opts.model_quality,
            model_source=self.opts.model_source,
            model_variant=self.opts.model_variant,
        )

        assert self._kokoro is not None

        if self.opts.voice_database:
            try:
                self._kokoro.load_voice_database(self.opts.voice_database)
                self.log(f"Loaded voice database: {self.opts.voice_database}")
            except Exception as e:
                self.log(f"Failed to load voice database: {e}", "warning")

        if self.opts.voice_blend:
            self._voice_style = VoiceBlend.parse(self.opts.voice_blend)
        else:
            # if voice_database provides overrides, let Kokoro resolve it
            if self.opts.voice_database:
                db_voice = cast(
                    str | VoiceBlend | None,
                    self._kokoro.get_voice_from_database(self.opts.voice),
                )
                self._voice_style = (
                    db_voice if db_voice is not None else self.opts.voice
                )
            else:
                self._voice_style = self.opts.voice

        # GenerationConfig will be supplied per call because lang / is_phonemes
        # can vary.
        pipeline_cfg = PipelineConfig(
            voice=self._voice_style,
            generation=GenerationConfig(
                speed=self.opts.speed,
                lang="en-us",
                random_seed=self.opts.random_seed,
            ),
            model_quality=self.opts.model_quality,
            model_source=self.opts.model_source,
            model_variant=self.opts.model_variant,
            model_path=self.opts.model_path,
            voices_path=self.opts.voices_path,
            tokenizer_config=self.opts.tokenizer_config,
            short_sentence_config=self.opts.short_sentence_config,
            ssmd=build_pykokoro_ssmd_config(self.opts.ssmd_policy),
            return_trace=True,
        )

        # Use the same adapters everywhere (text + phonemes)
        self._pipeline = build_pipeline(
            config=pipeline_cfg,
            backend=self._kokoro,
            phoneme_processing=OnnxPhonemeProcessorAdapter(self._kokoro),
            audio_generation=OnnxAudioGenerationAdapter(self._kokoro),
            audio_postprocessing=OnnxAudioPostprocessingAdapter(self._kokoro),
        )

    def synthesize(
        self,
        text_or_ssmd: str,
        *,
        lang_code: str,
        pause_mode: Literal["tts", "manual", "auto"],
        is_phonemes: bool = False,
        ssmd_policy: SSMDPolicy | None = None,
        audio_resolver: object | None = None,
    ) -> Any:
        self.ensure_ready()
        assert self._pipeline is not None
        gen = GenerationConfig(
            speed=self.opts.speed,
            lang=lang_code,
            is_phonemes=is_phonemes,
            pause_mode=pause_mode,
            enable_short_sentence=self.opts.enable_short_sentence,
            pause_clause=self.opts.pause_clause,
            pause_sentence=self.opts.pause_sentence,
            pause_paragraph=self.opts.pause_paragraph,
            pause_variance=self.opts.pause_variance,
            random_seed=self.opts.random_seed,
        )
        overrides: dict[str, Any] = {"generation": gen}
        if ssmd_policy is not None or audio_resolver is not None:
            effective_policy = ssmd_policy or self.opts.ssmd_policy
            overrides["ssmd"] = build_pykokoro_ssmd_config(
                effective_policy, audio_resolver=audio_resolver
            )
        result = self._pipeline.run(text_or_ssmd, **overrides)
        self.short_sentence_stats.add_audio_result(result)
        for warning in getattr(getattr(result, "trace", None), "warnings", ()):
            self.log(str(warning), "warning")
        return result

    def synthesize_audio(
        self,
        text_or_ssmd: str,
        *,
        lang_code: str,
        pause_mode: Literal["tts", "manual", "auto"],
        is_phonemes: bool = False,
        ssmd_policy: SSMDPolicy | None = None,
        audio_resolver: object | None = None,
    ) -> np.ndarray:
        """Compatibility helper returning only the audio samples."""
        result = self.synthesize(
            text_or_ssmd,
            lang_code=lang_code,
            pause_mode=pause_mode,
            is_phonemes=is_phonemes,
            ssmd_policy=ssmd_policy,
            audio_resolver=audio_resolver,
        )
        return cast(np.ndarray, result.audio)

    def get_short_sentence_stats(self) -> ShortSentenceStats:
        return self.short_sentence_stats.copy()
