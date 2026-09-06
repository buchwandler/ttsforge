"""Backend-light, deterministic conversion planning.

A plan resolves user/configuration policy before the synthesis runner is
constructed.  It is deliberately independent from :mod:`ttsforge.conversion`
so dry-run and help paths can inspect the exact request without loading ONNX.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Literal

from .chapter_selection import resolve_chapter_selection
from .cli.backend_config import (
    resolve_model_source_and_variant,
    resolve_onnx_provider,
    resolve_pykokoro_pipeline_defaults,
)
from .constants import DEFAULT_CONFIG
from .input_reader import InputReader
from .utils import load_config, resolve_conversion_defaults

PLAN_SCHEMA = "ttsforge.conversion-plan.v1"


@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    field: str
    value: Any
    origin: str
    locator: str | None = None


@dataclass(frozen=True, slots=True)
class InputPlan:
    source_path: str
    source_sha256: str
    source_type: str
    title: str
    author: str
    chapter_count: int
    selected_chapters: tuple[int, ...]
    extraction_mode: str


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    language: str
    voice: str | None
    model_source: str | None
    model_variant: str | None
    model_quality: str | None
    provider: str
    speed: float
    conversion_unit: str
    pause_mode: str
    pause_clause: float
    pause_sentence: float
    pause_paragraph: float
    pause_variance: float
    short_sentence: str | None
    enable_short_sentence: bool | None
    prosody: Mapping[str, Any]
    ssmd: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OutputPlan:
    path: str
    format: str
    merge_at_end: bool
    keep_chapter_files: bool


@dataclass(frozen=True, slots=True)
class EnvironmentPlan:
    packages: Mapping[str, str]
    provider_available: bool | None = None


@dataclass(frozen=True, slots=True)
class ConversionPlan:
    schema: str
    ok: bool
    input: InputPlan
    pipeline: PipelinePlan
    output: OutputPlan
    environment: EnvironmentPlan
    decisions: tuple[ResolutionDecision, ...] = ()
    diagnostics: tuple[PlanDiagnostic, ...] = ()

    def resolved_payload(self) -> dict[str, Any]:
        return _normalize(asdict(self))

    def canonical_json(self) -> str:
        return json.dumps(
            self.resolved_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def generation_sha256(self) -> str:
        payload = json.dumps(
            self.generation_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = self.resolved_payload()
        payload["plan_sha256"] = self.sha256
        return payload

    def generation_payload(self) -> dict[str, Any]:
        """Return only values that can change generated audio."""
        return _normalize(
            {
                "schema": self.schema,
                "input": {
                    "source_sha256": self.input.source_sha256,
                    "selected_chapters": self.input.selected_chapters,
                    "extraction_mode": self.input.extraction_mode,
                },
                "pipeline": asdict(self.pipeline),
                "output": {"format": self.output.format},
            }
        )


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value.expanduser().resolve(strict=False))
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "unavailable"


def _decision(
    field: str, value: Any, explicit: bool, config_key: str
) -> ResolutionDecision:
    return ResolutionDecision(
        field=field,
        value=_normalize(value),
        origin="cli" if explicit else "config",
        locator=None if explicit else config_key,
    )


def resolve_conversion_plan(
    source_path: Path,
    *,
    request: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ConversionPlan:
    """Resolve a conversion request without constructing a TTS pipeline."""
    request = dict(request or {})
    config = dict(load_config() if config is None else config)
    source_path = source_path.expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise ValueError(f"input file does not exist: {source_path}")

    extraction_mode = str(
        request.get("epub_content_mode")
        or config.get(
            "epub_content_mode",
            DEFAULT_CONFIG.get("epub_content_mode", "markdown"),
        )
    )
    if extraction_mode not in {"markdown", "plain"}:
        raise ValueError("epub_content_mode must be markdown or plain")
    provided_count = request.get("chapter_count")
    if provided_count is None:
        reader = InputReader(source_path)
        metadata = reader.get_metadata()
        chapters = reader.get_chapters()
        chapter_count = len(chapters)
        if chapter_count == 0:
            raise ValueError("input contains no chapters")
        metadata_title = metadata.title
        metadata_author = metadata.authors[0] if metadata.authors else "Unknown"
    else:
        chapter_count = int(provided_count)
        if chapter_count <= 0:
            raise ValueError("input contains no chapters")
        metadata_title = ""
        metadata_author = "Unknown"
    title = str(
        request.get("title")
        or metadata_title
        or config.get("default_title", source_path.stem)
    )
    author = str(request.get("author") or metadata_author)
    selected_value = request.get("selected_chapters")
    if selected_value is not None:
        selected = [int(index) for index in selected_value]
    else:
        selected = resolve_chapter_selection(
            request.get("chapters"), request.get("skip_chapters"), chapter_count
        )
        if selected is None:
            selected = list(range(chapter_count))
    raw_language = request.get("language")
    language = str(
        raw_language
        if raw_language is not None
        else config.get("default_language", "a")
    )
    defaults = resolve_conversion_defaults(
        config,
        {
            "voice": request.get("voice"),
            "language": language,
            "speed": request.get("speed"),
            "split_mode": request.get("split_mode"),
            "use_gpu": request.get("use_gpu"),
            "onnx_provider": request.get("provider"),
            "lang": request.get("lang"),
        },
    )
    provider = resolve_onnx_provider(
        config,
        provider_override=request.get("provider"),
        use_gpu_override=request.get("use_gpu"),
    )
    raw_source = request.get("model_source")
    if raw_source is None:
        raw_source, configured_variant = resolve_model_source_and_variant(config)
    else:
        configured_variant = request.get("model_variant")
    raw_variant = (
        request.get("model_variant")
        if request.get("model_variant") is not None
        else configured_variant
    )
    raw_quality = (
        request.get("model_quality")
        if request.get("model_quality") is not None
        else config.get("model_quality")
    )
    resolved = resolve_pykokoro_pipeline_defaults(
        ttsforge_language=str(defaults["language"]),
        voice=defaults.get("voice"),
        model_source=raw_source,
        model_variant=raw_variant,
        model_quality=raw_quality,
        provider=provider,
    )
    fmt = str(request.get("output_format") or config.get("default_format", "m4b"))
    output_value = request.get("output")
    output = (
        Path(output_value).expanduser()
        if output_value
        else source_path.with_suffix(f".{fmt}")
    )
    if output.is_dir():
        output = output / f"{source_path.stem}.{fmt}"
    if output.suffix:
        fmt = output.suffix.lstrip(".") or fmt
    conversion_unit = str(request.get("conversion_unit") or "chapter")
    if conversion_unit not in {"chapter", "paragraph"}:
        raise ValueError("conversion_unit must be 'chapter' or 'paragraph'")

    def number(name: str, default: float) -> float:
        value = request.get(name)
        return float(value if value is not None else config.get(name, default))

    language_value = str(defaults["language"])
    decisions = (
        _decision(
            "language", language_value, raw_language is not None, "default_language"
        ),
        _decision(
            "voice", resolved.voice, request.get("voice") is not None, "default_voice"
        ),
        _decision(
            "provider", provider, request.get("provider") is not None, "onnx_provider"
        ),
        _decision(
            "output", str(output), output_value is not None, "output_filename_template"
        ),
        _decision(
            "conversion_unit",
            conversion_unit,
            request.get("conversion_unit") is not None,
            "conversion_unit",
        ),
    )
    prosody = {
        "method": (
            request.get("prosody_method")
            if request.get("prosody_method") is not None
            else config.get("prosody_method")
        ),
        "strict": (
            request.get("prosody_strict")
            if request.get("prosody_strict") is not None
            else config.get("prosody_strict")
        ),
    }
    ssmd = {
        "header": (
            request.get("ssmd_header")
            if request.get("ssmd_header") is not None
            else config.get("ssmd_header")
        ),
        "emphasis": (
            request.get("ssmd_emphasis")
            if request.get("ssmd_emphasis") is not None
            else config.get("ssmd_emphasis")
        ),
    }
    diagnostics = (
        PlanDiagnostic(
            "provider-availability-unknown",
            "info",
            "Provider availability is deferred to the rendering environment.",
        ),
    )
    pipeline = PipelinePlan(
        language=language_value,
        voice=resolved.voice,
        model_source=resolved.model_source,
        model_variant=resolved.model_variant,
        model_quality=resolved.model_quality,
        provider=provider,
        speed=float(defaults["speed"]),
        conversion_unit=conversion_unit,
        pause_mode=str(request.get("pause_mode") or config.get("pause_mode", "auto")),
        pause_clause=number("pause_clause", 0.3),
        pause_sentence=number("pause_sentence", 0.5),
        pause_paragraph=number("pause_paragraph", 0.9),
        pause_variance=number("pause_variance", 0.05),
        short_sentence=(
            request.get("short_sentence")
            if request.get("short_sentence") is not None
            else config.get("short_sentence")
        ),
        enable_short_sentence=(
            request.get("enable_short_sentence")
            if request.get("enable_short_sentence") is not None
            else config.get("enable_short_sentence")
        ),
        prosody=prosody,
        ssmd=ssmd,
    )
    return ConversionPlan(
        schema=PLAN_SCHEMA,
        ok=True,
        input=InputPlan(
            source_path=str(source_path),
            source_sha256=_sha256_file(source_path),
            source_type=source_path.suffix.lower().lstrip(".") or "text",
            title=title,
            author=author,
            chapter_count=chapter_count,
            selected_chapters=tuple(selected),
            extraction_mode=extraction_mode,
        ),
        pipeline=pipeline,
        output=OutputPlan(
            path=str(output.resolve(strict=False)),
            format=fmt,
            merge_at_end=True,
            keep_chapter_files=bool(request.get("keep_chapter_files", False)),
        ),
        environment=EnvironmentPlan(
            packages={
                "ttsforge": _version("ttsforge"),
                "pykokoro": _version("pykokoro"),
                "ssmd": _version("ssmd"),
                "epub2text": _version("epub2text"),
            }
        ),
        decisions=decisions,
        diagnostics=diagnostics,
    )


def plan_json(plan: ConversionPlan, *, pretty: bool = False) -> str:
    """Serialize a plan including its content hash."""
    return json.dumps(
        plan.to_dict(),
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=True,
    )
