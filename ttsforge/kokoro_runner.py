# ttsforge/kokoro_runner.py
from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
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

from .memory_diagnostics import log_snapshot
from .prosody_support import ProsodyPolicy, build_pykokoro_prosody_config
from .render_units import PreparedUnitDescriptor, descriptor_from_public
from .short_sentence_stats import ShortSentenceStats
from .spacy_policy import SPACY_POLICY_VERSION
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
    use_spacy: bool | None = None
    spacy_model: str | None = None
    spacy_model_size: str | None = None
    spacy_policy: str = SPACY_POLICY_VERSION
    resolved_sentence_models: dict[str, str] = field(default_factory=dict)
    resolved_g2p_models: dict[str, str] = field(default_factory=dict)
    short_sentence_config: ShortSentenceConfig | None = None
    onnx_provider: str | None = None
    ssmd_policy: SSMDPolicy = field(default_factory=SSMDPolicy)
    prosody_policy: ProsodyPolicy = field(default_factory=ProsodyPolicy)

    def effective_onnx_provider(self) -> str:
        """Return the provider requested by this runner option set."""
        if self.onnx_provider is not None:
            return self.onnx_provider
        return "auto" if self.use_gpu else "cpu"


class PreparedParagraphUnits:
    """TTSForge's dependency-light facade over PyKokoro's public provider."""

    def __init__(self, runner: KokoroRunner, prepared: Any):
        self._runner = runner
        self._prepared = prepared
        self._units = tuple(
            descriptor_from_public(descriptor) for descriptor in prepared.units
        )

    @property
    def units(self) -> tuple[PreparedUnitDescriptor, ...]:
        return self._units

    @property
    def document_metadata(self) -> dict[str, Any]:
        value = getattr(self._prepared, "document_metadata", {})
        return dict(value) if hasattr(value, "items") else {}

    @property
    def diagnostics(self) -> Sequence[Any]:
        return tuple(getattr(self._prepared, "diagnostics", ()))

    def render(self, *, skip_indices: Collection[int] = ()) -> Iterator[Any]:
        for result in self._prepared.render(skip_indices=skip_indices):
            self._runner.short_sentence_stats.add_audio_result(result)
            for warning in getattr(getattr(result, "trace", None), "warnings", ()):
                self._runner.log(str(warning), "warning")
            yield result

    def __enter__(self) -> PreparedParagraphUnits:
        self._prepared.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._prepared.__exit__(exc_type, exc, tb)


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

    @property
    def spacy_resolutions(self) -> dict[str, dict[str, str]]:
        """Return frozen, language-keyed model selections for diagnostics."""
        return {
            "sentence": dict(sorted(self.opts.resolved_sentence_models.items())),
            "g2p": dict(sorted(self.opts.resolved_g2p_models.items())),
        }

    def ensure_ready(self) -> None:
        if self._pipeline is not None:
            return

        log_snapshot(
            self.log,
            "before runner initialization",
            provider=self.opts.effective_onnx_provider(),
        )

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
            prosody=build_pykokoro_prosody_config(self.opts.prosody_policy),
            return_trace=True,
            retain_segment_audio=False,
        )

        # Use the same adapters everywhere (text + phonemes)
        self._pipeline = build_pipeline(
            config=pipeline_cfg,
            backend=self._kokoro,
            phoneme_processing=OnnxPhonemeProcessorAdapter(self._kokoro),
            audio_generation=OnnxAudioGenerationAdapter(self._kokoro),
            audio_postprocessing=OnnxAudioPostprocessingAdapter(self._kokoro),
        )
        log_snapshot(
            self.log,
            "after runner initialization",
            provider=self.opts.effective_onnx_provider(),
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
        """Return caller-owned audio samples from a synthesized result.

        The returned array remains valid after this method returns. The caller
        owns that array and is responsible for releasing or replacing its
        reference when it is no longer needed.
        """
        result = self.synthesize(
            text_or_ssmd,
            lang_code=lang_code,
            pause_mode=pause_mode,
            is_phonemes=is_phonemes,
            ssmd_policy=ssmd_policy,
            audio_resolver=audio_resolver,
        )
        return cast(np.ndarray, result.audio)

    def prepare_paragraph_units(
        self,
        text: str,
        *,
        lang_code: str,
        pause_mode: Literal["tts", "manual", "auto"],
        ssmd_policy: SSMDPolicy | None = None,
        audio_resolver: object | None = None,
    ) -> PreparedParagraphUnits:
        """Prepare a complete document using PyKokoro's public unit API."""
        self.ensure_ready()
        pipeline = self._pipeline
        if pipeline is None or not callable(getattr(pipeline, "prepare_units", None)):
            raise RuntimeError(
                "Installed PyKokoro does not provide the public paragraph-unit API; "
                "install pykokoro>=0.8.1,<0.9."
            )
        gen = GenerationConfig(
            speed=self.opts.speed,
            lang=lang_code,
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
        try:
            prepared = pipeline.prepare_units(
                text,
                unit="paragraph",
                **overrides,
            )
        except (AttributeError, TypeError) as exc:
            raise RuntimeError(
                "Installed PyKokoro cannot satisfy the public paragraph-unit API; "
                "install pykokoro>=0.8.1,<0.9."
            ) from exc
        return PreparedParagraphUnits(self, prepared)

    def get_short_sentence_stats(self) -> ShortSentenceStats:
        return self.short_sentence_stats.copy()

    def close(self) -> None:
        """Close pipeline and backend resources, safely and idempotently."""
        pipeline, self._pipeline = self._pipeline, None
        kokoro, self._kokoro = self._kokoro, None
        self._voice_style = None

        try:
            if pipeline is not None:
                pipeline.close()
        finally:
            if kokoro is not None:
                kokoro.close()

    def __enter__(self) -> KokoroRunner:
        self.ensure_ready()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
