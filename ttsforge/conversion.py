"""TTS conversion module for ttsforge - converts text/EPUB to audiobooks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
import soundfile as sf
from pykokoro.config_types import (
    DEFAULT_MODEL_SOURCE,
    DEFAULT_MODEL_VARIANT,
    ModelQuality,
    ModelSource,
    ModelVariant,
)

from .audio_merge import AudioMerger, ChapterBoundary, MergeMeta, OrderedAudioInput
from .constants import (
    DEFAULT_VOICE_FOR_LANG,
    ISO_TO_LANG_CODE,
    SAMPLE_RATE,
    SUPPORTED_OUTPUT_FORMATS,
    VOICE_PREFIX_TO_LANG,
)
from .kokoro_lang import get_onnx_lang_code
from .memory_diagnostics import log_snapshot
from .paragraph_output import (
    canonical_filename,
    ensure_owned_directory,
    finalize_wav,
    owned_path,
    paragraph_directory,
    rebuild_manifest_and_playlist,
    validate_wav,
)
from .prosody_support import ProsodyPolicy, prosody_policy_payload
from .render_units import (
    PARAGRAPH_MANIFEST_SCHEMA,
    PARAGRAPH_OUTPUT_SCHEMA,
    UNIT_FILENAME_SCHEMA,
    ConversionUnit,
    RenderUnitState,
    UnitRateEstimator,
    map_descriptors,
    reconcile_units,
    renderer_contract_payload,
    validate_conversion_unit,
)
from .short_sentence_config import resolve_short_sentence_config
from .short_sentence_stats import ShortSentenceStats
from .spacy_policy import (
    SPACY_POLICY_VERSION,
    SpacyModelRequest,
    SpacyPolicyError,
    ensure_model_loadable,
    normalize_language,
    report_selection,
    resolve_spacy_model_for_component,
)
from .ssmd_audio import LocalSSMDAudioResolver
from .ssmd_generator import (
    SSMDGenerationError,
    chapter_to_ssmd,
    load_ssmd_file,
    save_ssmd_file,
)
from .ssmd_support import (
    SSMDDocumentInfo,
    SSMDIssue,
    SSMDPolicy,
    validate_ssmd_document,
)
from .text_postprocessing import (
    TextPostprocessOptions,
    postprocess_extracted_text,
)
from .utils import (
    atomic_write_json,
    format_duration,
    format_filename_template,
    load_phoneme_dictionary,
    prevent_sleep_end,
    prevent_sleep_start,
    sanitize_filename,
)

if TYPE_CHECKING:
    from .kokoro_runner import KokoroRunner

DEFAULT_MODEL_QUALITY: ModelQuality = "fp32"


@dataclass
class Chapter:
    """Represents a chapter from an EPUB or text file."""

    title: str
    content: str
    index: int = 0
    markdown_body: str | None = None
    source_format: Literal["plain", "markdown", "ssmd"] = "plain"
    source_id: str | None = None
    parent_id: str | None = None
    level: int = 1
    extraction_schema: str | None = None
    extraction_diagnostics: tuple[str, ...] = ()
    is_ssmd: bool = False

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def text(self) -> str:
        """Alias for content to maintain compatibility with input_reader.Chapter."""
        return self.content


@dataclass
class ConversionProgress:
    """Progress information during conversion."""

    current_chapter: int = 0
    total_chapters: int = 0
    chapter_name: str = ""
    chars_processed: int = 0
    total_chars: int = 0
    current_text: str = ""
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    current_unit: int = 0
    total_units: int = 0
    current_paragraph: int = 0
    paragraphs_in_chapter: int = 0
    unit_kind: str = ""

    @property
    def percent(self) -> int:
        if self.total_chars == 0:
            return 0
        return min(int(self.chars_processed / self.total_chars * 100), 99)

    @property
    def etr_formatted(self) -> str:
        return format_duration(self.estimated_remaining)


@dataclass
class ConversionResult:
    """Result of a conversion operation."""

    success: bool
    output_path: Path | None = None
    subtitle_path: Path | None = None
    error_message: str | None = None
    chapters_dir: Path | None = None
    short_sentence_stats: ShortSentenceStats = field(default_factory=ShortSentenceStats)
    document_metadata: dict[str, Any] = field(default_factory=dict)
    ssmd_diagnostics: tuple[SSMDIssue, ...] = ()
    markers: list[dict[str, Any]] = field(default_factory=list)
    conversion_unit: str = "chapter"
    paragraphs_dir: Path | None = None
    unit_count: int = 0


@dataclass(slots=True)
class RenderedChapter:
    """Lightweight data retained after a chapter waveform is written."""

    duration: float
    rendered_path: Path
    sample_rate: int
    diagnostics: tuple[SSMDIssue, ...]
    markers: list[dict[str, Any]]
    document_metadata: dict[str, Any]


@dataclass
class ChapterState:
    """State of a single chapter conversion."""

    index: int
    title: str
    content_hash: str  # Hash of chapter content for integrity check
    source_format: str = "plain"
    source_id: str | None = None
    source_markup_hash: str = ""
    extraction_schema: str | None = None
    completed: bool = False
    audio_file: str | None = None  # Relative path to chapter audio
    duration: float = 0.0  # Duration in seconds
    char_count: int = 0
    ssmd_file: str | None = None  # Relative path to SSMD file
    ssmd_hash: str | None = None  # Hash of SSMD content for change detection
    render_fingerprint: str = ""  # Inputs that produced the audio artifact
    ssmd_diagnostics_file: str | None = None
    ssmd_markers_file: str | None = None
    ssmd_document_title: str | None = None
    units: list[RenderUnitState] = field(default_factory=list)


@dataclass
class ConversionState:
    """Persistent state for resumable conversions."""

    # Keep the constructor default compatible with callers that create legacy
    # records directly; conversion-created records explicitly use schema v3.
    version: int = 1
    source_file: str = ""
    source_hash: str = ""  # Hash of source file for change detection
    output_file: str = ""
    work_dir: str = ""
    voice: str = ""
    language: str = ""
    speed: float = 1.0
    split_mode: str = "auto"
    output_format: str = "m4b"
    model_quality: ModelQuality | None = DEFAULT_MODEL_QUALITY
    model_source: ModelSource = DEFAULT_MODEL_SOURCE
    model_variant: ModelVariant = DEFAULT_MODEL_VARIANT
    onnx_provider: str | None = None
    silence_between_chapters: float = 2.0
    pause_clause: float = 0.3
    pause_sentence: float = 0.5
    pause_paragraph: float = 0.9
    pause_variance: float = 0.05
    random_seed: int | None = None
    pause_mode: str = "auto"  # "tts", "manual", or "auto
    enable_short_sentence: bool | None = None
    short_sentence: str | None = None
    lang: str | None = None  # Language override for phonemization
    use_spacy: bool | None = None
    spacy_model: str | None = None
    spacy_model_size: str | None = None
    spacy_policy: str = "highest-installed-v1"
    resolved_sentence_models: dict[str, str] = field(default_factory=dict)
    resolved_g2p_models: dict[str, str] = field(default_factory=dict)
    chapters: list[ChapterState] = field(default_factory=list)
    source_selection: list[int] = field(default_factory=list)
    generation_fingerprint: str = ""
    ssmd_policy_fingerprint: str = ""
    started_at: str = ""
    last_updated: str = ""
    conversion_unit: ConversionUnit = "chapter"
    paragraphs_dir: str | None = None
    unit_filename_schema: int = UNIT_FILENAME_SCHEMA
    paragraph_manifest_schema: int = PARAGRAPH_MANIFEST_SCHEMA

    @classmethod
    def load(cls, state_file: Path) -> ConversionState | None:
        """Load state from a JSON file."""
        if not state_file.exists():
            return None
        try:
            with open(state_file, encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct ChapterState objects, retaining compatibility with
            # pre-schema-5 records that have no per-unit list.
            chapters = []
            chapter_fields = {
                field.name for field in ChapterState.__dataclass_fields__.values()
            }
            for chapter_data in data.get("chapters", []):
                chapter_values = {
                    key: value
                    for key, value in chapter_data.items()
                    if key in chapter_fields
                }
                chapter_values["units"] = [
                    RenderUnitState.from_dict(unit)
                    for unit in chapter_data.get("units", [])
                ]
                chapters.append(ChapterState(**chapter_values))
            data["chapters"] = chapters
            data.setdefault("source_selection", [])
            data.setdefault("generation_fingerprint", "")
            data.setdefault("ssmd_policy_fingerprint", "")

            # Handle missing fields for backward compatibility
            if "silence_between_chapters" not in data:
                data["silence_between_chapters"] = 2.0

            # Migrate old pause parameters to new system
            if "segment_pause_min" in data or "segment_pause_max" in data:
                seg_min = data.get("segment_pause_min", 0.1)
                seg_max = data.get("segment_pause_max", 0.3)
                data["pause_sentence"] = (seg_min + seg_max) / 2.0
                if "pause_variance" not in data:
                    data["pause_variance"] = max(0.01, (seg_max - seg_min) / 4.0)

            if "paragraph_pause_min" in data or "paragraph_pause_max" in data:
                para_min = data.get("paragraph_pause_min", 0.5)
                para_max = data.get("paragraph_pause_max", 1.0)
                data["pause_paragraph"] = (para_min + para_max) / 2.0

            for legacy_key in (
                "segment_pause_min",
                "segment_pause_max",
                "paragraph_pause_min",
                "paragraph_pause_max",
            ):
                data.pop(legacy_key, None)

            # Set defaults for new parameters
            if "pause_clause" not in data:
                data["pause_clause"] = 0.3
            if "pause_sentence" not in data:
                data["pause_sentence"] = 0.5
            if "pause_paragraph" not in data:
                data["pause_paragraph"] = 0.9
            if "pause_variance" not in data:
                data["pause_variance"] = 0.05
            if "random_seed" not in data:
                data["random_seed"] = None
            if "pause_mode" not in data:
                data["pause_mode"] = "auto"
            if "enable_short_sentence" not in data:
                data["enable_short_sentence"] = None
            if "short_sentence" not in data:
                data["short_sentence"] = None
            if "lang" not in data:
                data["lang"] = None
            if "use_spacy" not in data:
                data["use_spacy"] = None
            if "spacy_model" not in data:
                data["spacy_model"] = None
            if "spacy_model_size" not in data:
                data["spacy_model_size"] = None
            if "spacy_policy" not in data:
                data["spacy_policy"] = "highest-installed-v1"
            if "resolved_sentence_models" not in data:
                data["resolved_sentence_models"] = {}
            if "resolved_g2p_models" not in data:
                data["resolved_g2p_models"] = {}
            if "model_quality" not in data:
                data["model_quality"] = DEFAULT_MODEL_QUALITY
            if "model_source" not in data:
                data["model_source"] = DEFAULT_MODEL_SOURCE
            if "model_variant" not in data:
                data["model_variant"] = DEFAULT_MODEL_VARIANT
            data.setdefault("onnx_provider", None)
            data["conversion_unit"] = validate_conversion_unit(
                str(data.get("conversion_unit", "chapter"))
            )
            data.setdefault("paragraphs_dir", None)
            data.setdefault("unit_filename_schema", UNIT_FILENAME_SCHEMA)
            data.setdefault("paragraph_manifest_schema", PARAGRAPH_MANIFEST_SCHEMA)

            return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save(self, state_file: Path) -> None:
        """Save state to a JSON file."""
        self.last_updated = time.strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "version": self.version,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "output_file": self.output_file,
            "work_dir": self.work_dir,
            "voice": self.voice,
            "language": self.language,
            "speed": self.speed,
            "split_mode": self.split_mode,
            "output_format": self.output_format,
            "model_quality": self.model_quality,
            "model_source": self.model_source,
            "model_variant": self.model_variant,
            "onnx_provider": self.onnx_provider,
            "silence_between_chapters": self.silence_between_chapters,
            "pause_clause": self.pause_clause,
            "pause_sentence": self.pause_sentence,
            "pause_paragraph": self.pause_paragraph,
            "pause_variance": self.pause_variance,
            "random_seed": self.random_seed,
            "pause_mode": self.pause_mode,
            "enable_short_sentence": self.enable_short_sentence,
            "short_sentence": self.short_sentence,
            "lang": self.lang,
            "use_spacy": self.use_spacy,
            "spacy_model": self.spacy_model,
            "spacy_model_size": self.spacy_model_size,
            "spacy_policy": self.spacy_policy,
            "resolved_sentence_models": dict(
                sorted(self.resolved_sentence_models.items())
            ),
            "resolved_g2p_models": dict(sorted(self.resolved_g2p_models.items())),
            "chapters": [
                {
                    "index": ch.index,
                    "title": ch.title,
                    "content_hash": ch.content_hash,
                    "source_format": ch.source_format,
                    "source_id": ch.source_id,
                    "source_markup_hash": ch.source_markup_hash,
                    "extraction_schema": ch.extraction_schema,
                    "completed": ch.completed,
                    "audio_file": ch.audio_file,
                    "duration": ch.duration,
                    "char_count": ch.char_count,
                    "ssmd_file": ch.ssmd_file,
                    "ssmd_hash": ch.ssmd_hash,
                    "render_fingerprint": ch.render_fingerprint,
                    "ssmd_diagnostics_file": ch.ssmd_diagnostics_file,
                    "ssmd_markers_file": ch.ssmd_markers_file,
                    "ssmd_document_title": ch.ssmd_document_title,
                    "units": [unit.to_dict() for unit in ch.units],
                }
                for ch in self.chapters
            ],
            "started_at": self.started_at,
            "last_updated": self.last_updated,
            "source_selection": self.source_selection,
            "generation_fingerprint": self.generation_fingerprint,
            "ssmd_policy_fingerprint": self.ssmd_policy_fingerprint,
            "conversion_unit": self.conversion_unit,
            "paragraphs_dir": self.paragraphs_dir,
            "unit_filename_schema": self.unit_filename_schema,
            "paragraph_manifest_schema": self.paragraph_manifest_schema,
        }
        atomic_write_json(state_file, data, indent=2, ensure_ascii=True)

    def get_completed_count(self) -> int:
        """Get the number of completed chapters."""
        if self.conversion_unit == "paragraph":
            return self.get_completed_unit_count()
        return sum(1 for ch in self.chapters if ch.completed)

    def get_completed_unit_count(self) -> int:
        return sum(
            1 for chapter in self.chapters for unit in chapter.units if unit.completed
        )

    def get_total_unit_count(self) -> int:
        return sum(len(chapter.units) for chapter in self.chapters)

    def get_next_incomplete_index(self) -> int | None:
        """Get the index of the next incomplete chapter."""
        for ch in self.chapters:
            if not ch.completed:
                return ch.index
        return None

    def get_next_incomplete_unit(self) -> RenderUnitState | None:
        for chapter in self.chapters:
            for unit in chapter.units:
                if not unit.completed:
                    return unit
        return None

    def is_complete(self) -> bool:
        """Check if all chapters are completed."""
        if self.conversion_unit == "paragraph":
            return all(
                chapter.units and all(unit.completed for unit in chapter.units)
                for chapter in self.chapters
            )
        return all(ch.completed for ch in self.chapters)


@dataclass(frozen=True)
class ConversionWorkspace:
    """Centralized workspace identity for a resumable conversion."""

    source_hash: str
    work_dir: Path
    state_file: Path


@dataclass(frozen=True)
class ResumeValidation:
    """Structured result from resume state validation."""

    reusable: bool
    reason: str | None = None


@dataclass(frozen=True)
class ResumeCandidate:
    """A discovered resumable conversion state."""

    state: ConversionState
    workspace: ConversionWorkspace
    selected_positions: list[int]
    saved_output: Path


def resolve_conversion_workspace(
    *,
    output_dir: Path,
    book_title: str,
    source_file: Path,
) -> ConversionWorkspace:
    """Compute workspace identity from source and output directory.

    Uses the same naming scheme as the existing converter so current
    state files remain discoverable.
    """
    source_hash = _hash_file(source_file)
    safe_title = sanitize_filename(book_title)[:50]
    work_dir = output_dir / f".{safe_title}-{source_hash[:12]}_chapters"
    return ConversionWorkspace(
        source_hash=source_hash,
        work_dir=work_dir,
        state_file=work_dir / "state.json",
    )


def resolve_saved_output_path(
    state: ConversionState,
    state_file: Path,
) -> Path:
    """Resolve the saved output path from a conversion state.

    Handles both absolute and relative paths.  A conversion workspace is
    always a sibling of the final output, so for relative paths the output
    lives two directories up from the state file.
    """
    saved_text = state.output_file
    saved = Path(saved_text)
    if (
        saved.is_absolute()
        or PurePosixPath(saved_text).is_absolute()
        or PureWindowsPath(saved_text).is_absolute()
    ):
        return saved
    # Workspace is <output_dir>/.<title>-<hash>_chapters; output is in
    # <output_dir>, so two parents up from state_file.
    return state_file.parent.parent / saved.name


def discover_resume_candidate(
    *,
    source_file: Path,
    output_dir: Path,
    book_title: str,
    chapters: Sequence[Chapter],
    min_schema_version: int = 3,
) -> ResumeCandidate | None:
    """Discover a resumable conversion state without side effects.

    Returns a ResumeCandidate when a compatible saved state exists, or
    None when no usable state is found.  Never creates directories or
    mutates state.
    """
    workspace = resolve_conversion_workspace(
        output_dir=output_dir,
        book_title=book_title,
        source_file=source_file,
    )
    if not workspace.state_file.exists():
        return None

    state = ConversionState.load(workspace.state_file)
    if state is None:
        return None

    # Version check
    if state.version < min_schema_version:
        return None

    # Source hash must match
    if state.source_hash != workspace.source_hash:
        return None

    # source_selection must be present and non-empty
    if not state.source_selection:
        return None

    # Build position map from current chapters
    position_by_source_index: dict[int, int] = {
        chapter.index: position for position, chapter in enumerate(chapters)
    }

    # Every saved source index must exist in the current chapter list
    missing = [
        idx for idx in state.source_selection if idx not in position_by_source_index
    ]
    if missing:
        return None

    # Verify chapter order is preserved
    restored_positions = [
        position_by_source_index[idx] for idx in state.source_selection
    ]
    if restored_positions != sorted(restored_positions):
        return None

    # At least one chapter must be incomplete, or the output needs
    # rebuilding
    has_incomplete = any(not ch.completed for ch in state.chapters)
    output_path = resolve_saved_output_path(state, workspace.state_file)
    output_missing = not output_path.exists()
    if not has_incomplete and not output_missing:
        return None

    return ResumeCandidate(
        state=state,
        workspace=workspace,
        selected_positions=restored_positions,
        saved_output=output_path,
    )


def _hash_content(content: str) -> str:
    """Generate a hash of content for integrity checking."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def _hash_file(file_path: Path) -> str:
    """Generate a hash of a file for change detection."""
    if not file_path.exists():
        return ""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:12]


def _canonical_fingerprint(data: Any) -> str:
    """Hash JSON-compatible data using a stable representation."""
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chapter_source_markup_hash(chapter: Chapter) -> str:
    """Hash the exact source body supplied before SSMD title/front matter."""
    if chapter.source_format != "markdown":
        return ""
    return _hash_content(chapter.markdown_body or "")


def _chapter_render_fingerprint(chapter: Chapter, generation: str) -> str:
    """Fingerprint all chapter source representation inputs."""
    return _canonical_fingerprint(
        {
            "generation": generation,
            "source_index": chapter.index,
            "title": chapter.title,
            "content_sha256": _hash_content(chapter.content),
            "markdown_sha256": _chapter_source_markup_hash(chapter),
            "source_format": chapter.source_format,
            "source_id": chapter.source_id,
            "extraction_schema": chapter.extraction_schema,
        }
    )


def _path_identity(path: Path | str | None) -> dict[str, str] | None:
    """Return stable path/content identity without embedding file contents."""
    if path is None:
        return None
    resolved = Path(path)
    return {"path": str(resolved), "sha256": _hash_file(resolved)}


def _ssmd_policy_payload(policy: SSMDPolicy) -> dict[str, Any]:
    """Return a canonical, JSON-safe representation of SSMD render policy."""
    pause = policy.pause_overrides
    bindings = {
        str(provider): {
            str(reference): str(target)
            for reference, target in sorted(provider_bindings.items())
        }
        for provider, provider_bindings in sorted(policy.voice_bindings.items())
    }
    return {
        "parse_header": policy.parse_header,
        "unknown_header": policy.unknown_header,
        "missing_voice": policy.missing_voice,
        "validate_profile": policy.validate_profile,
        "emphasis_mode": policy.emphasis_mode,
        "fail_on_warning": policy.fail_on_warning,
        "voice_bindings": bindings,
        "pause_overrides": (
            {
                "enabled": pause.enabled,
                "sentence": pause.sentence,
                "paragraph": pause.paragraph,
                "voice_change": pause.voice_change,
            }
            if pause is not None
            else None
        ),
        "audio_root": _path_identity(policy.audio_root),
        "allow_remote_audio": policy.allow_remote_audio,
        "audio_timeout_s": policy.audio_timeout_s,
        "audio_max_bytes": policy.audio_max_bytes,
        "audio_max_duration_s": policy.audio_max_duration_s,
        # This changes when the public renderer contract changes and prevents
        # older artifacts from being reused under a different policy model.
        "renderer_contract": renderer_contract_payload(),
    }


def _result_issues(result: Any) -> tuple[SSMDIssue, ...]:
    """Normalize pykokoro trace warnings into ttsforge issues."""
    issues: list[SSMDIssue] = []
    for warning in getattr(getattr(result, "trace", None), "warnings", ()):
        message = str(warning)
        code, _, detail = message.partition(":")
        if not detail:
            code, detail = "ssmd.renderer_warning", message
        issues.append(SSMDIssue(code, "warn", detail.strip()))
    return tuple(issues)


def _marker_records(result: Any) -> list[dict[str, Any]]:
    sample_rate = int(getattr(result, "sample_rate", SAMPLE_RATE) or SAMPLE_RATE)
    records: list[dict[str, Any]] = []
    for marker in getattr(result, "markers", ()):
        sample_offset = int(marker.get("sample_offset", 0))
        records.append(
            {
                "name": str(marker.get("name", "")),
                "char_offset": int(marker.get("char_offset", 0)),
                "sample_offset": sample_offset,
                "time_s": sample_offset / sample_rate,
            }
        )
    return records


def _write_marker_sidecar(path: Path, result: Any) -> list[dict[str, Any]]:
    markers = _marker_records(result)
    sample_rate = int(getattr(result, "sample_rate", SAMPLE_RATE) or SAMPLE_RATE)
    _write_marker_records_sidecar(
        path,
        sample_rate=sample_rate,
        markers=markers,
    )
    return markers


def _write_marker_records_sidecar(
    path: Path,
    *,
    sample_rate: int,
    markers: list[dict[str, Any]],
) -> None:
    """Write marker records without retaining a PyKokoro result."""
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "sample_rate": sample_rate,
            "markers": markers,
        },
        indent=2,
        ensure_ascii=True,
    )


# Split mode options
SPLIT_MODES = ["auto", "line", "paragraph", "sentence", "clause"]


def validate_generation_ranges(
    *,
    speed: float,
    mixed_language_confidence: float | None = None,
    silence_between_chapters: float | None = None,
    pause_clause: float | None = None,
    pause_sentence: float | None = None,
    pause_paragraph: float | None = None,
    pause_variance: float | None = None,
    chapter_pause_after_title: float | None = None,
) -> None:
    """Validate numeric generation settings shared by CLI and library APIs."""
    if not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")
    if (
        mixed_language_confidence is not None
        and not 0.0 <= mixed_language_confidence <= 1.0
    ):
        raise ValueError("mixed_language_confidence must be between 0.0 and 1.0")
    for name, value in (
        ("silence_between_chapters", silence_between_chapters),
        ("pause_clause", pause_clause),
        ("pause_sentence", pause_sentence),
        ("pause_paragraph", pause_paragraph),
        ("pause_variance", pause_variance),
        ("chapter_pause_after_title", chapter_pause_after_title),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")


@dataclass
class ConversionOptions:
    """Options for TTS conversion."""

    voice: str = "af_bella"
    language: str = "a"
    speed: float = 1.0
    output_format: str = "m4b"
    output_dir: Path | None = None
    use_gpu: bool = False  # Legacy compatibility; use onnx_provider instead.
    onnx_provider: str | None = None
    silence_between_chapters: float = 2.0
    # Language override for phonemization (e.g., 'de', 'en-us', 'fr')
    # If None, language is determined from voice prefix
    lang: str | None = None
    # spaCy model policy. None means highest installed compatible model.
    use_spacy: bool | None = None
    spacy_model: str | None = None
    spacy_model_size: str | None = None
    # Mixed-language support (auto-detect and handle multiple languages)
    use_mixed_language: bool = False
    mixed_language_primary: str | None = None
    mixed_language_allowed: list[str] | None = None
    mixed_language_confidence: float = 0.7
    # Custom phoneme dictionary for pronunciation overrides
    phoneme_dictionary_path: str | None = None
    phoneme_dict_case_sensitive: bool = False
    # Pause settings (pykokoro built-in pause handling)
    pause_clause: float = 0.3  # For clause boundaries (commas)
    pause_sentence: float = 0.5  # For sentence boundaries
    pause_paragraph: float = 0.9  # For paragraph boundaries
    pause_variance: float = 0.05  # Standard deviation for natural variation
    random_seed: int | None = None  # Random seed for reproducible pause variance
    pause_mode: str = "auto"  # "tts", "manual", or "auto
    enable_short_sentence: bool | None = None  # Enable short sentence handling
    short_sentence: str | None = None  # Short-sentence handling config
    # Chapter announcement settings
    announce_chapters: bool = True  # Read chapter titles aloud before content
    chapter_pause_after_title: float = 2.0  # Pause after chapter title (seconds)
    save_chapters_separately: bool = False
    merge_at_end: bool = True
    # Split mode: auto, line, paragraph, sentence, clause
    split_mode: str = "auto"
    # Output/resume unit; independent from internal split_mode.
    conversion_unit: ConversionUnit = "chapter"
    # Resume capability
    resume: bool = True  # Enable resume by default for long conversions
    keep_chapter_files: bool = False  # Keep individual chapter files after merge
    # Metadata for m4b
    title: str | None = None
    author: str | None = None
    cover_image: Path | None = None
    # Voice blending (e.g., "af_nicole:50,am_michael:50")
    voice_blend: str | None = None
    # Voice database for custom/synthetic voices
    voice_database: Path | None = None
    # Filename template for chapter files
    chapter_filename_template: str = "{chapter_num:03d}_{book_title}_{chapter_title}"
    # Custom ONNX model path (None = use default downloaded model)
    model_quality: ModelQuality | None = DEFAULT_MODEL_QUALITY
    model_source: ModelSource = DEFAULT_MODEL_SOURCE
    model_variant: ModelVariant = DEFAULT_MODEL_VARIANT
    model_path: Path | None = None
    # Custom voices.bin path (None = use default downloaded voices)
    voices_path: Path | None = None
    # SSMD generation control
    generate_ssmd_only: bool = False  # If True, only generate SSMD files, no audio
    detect_emphasis: bool = True
    epub_content_mode: Literal["markdown", "plain"] = "markdown"
    text_postprocess_options: TextPostprocessOptions = field(
        default_factory=TextPostprocessOptions
    )
    # SSMD rendering policy.  Explicit CLI/API values are represented inside
    # this object; persistent config is translated separately by the CLI.
    ssmd_policy: SSMDPolicy = field(default_factory=SSMDPolicy)
    prosody_policy: ProsodyPolicy = field(default_factory=ProsodyPolicy)

    def effective_onnx_provider(self) -> str:
        """Return the provider requested by this option set."""
        if self.onnx_provider is not None:
            return self.onnx_provider
        return "auto" if self.use_gpu else "cpu"

    def __post_init__(self) -> None:
        from .spacy_policy import normalize_spacy_model, normalize_spacy_model_size

        self.spacy_model = normalize_spacy_model(self.spacy_model)
        self.spacy_model_size = normalize_spacy_model_size(self.spacy_model_size)
        if self.use_spacy is False:
            self.spacy_model = None
            self.spacy_model_size = None
        self.conversion_unit = validate_conversion_unit(self.conversion_unit)
        validate_generation_ranges(
            speed=self.speed,
            mixed_language_confidence=self.mixed_language_confidence,
            silence_between_chapters=self.silence_between_chapters,
            pause_clause=self.pause_clause,
            pause_sentence=self.pause_sentence,
            pause_paragraph=self.pause_paragraph,
            pause_variance=self.pause_variance,
            chapter_pause_after_title=self.chapter_pause_after_title,
        )
        if not isinstance(self.ssmd_policy, SSMDPolicy):
            raise TypeError("ssmd_policy must be an SSMDPolicy")
        if not isinstance(self.prosody_policy, ProsodyPolicy):
            raise TypeError("prosody_policy must be a ProsodyPolicy")


# Pattern to detect chapter markers in text
CHAPTER_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:"
    r"(?:Chapter|CHAPTER|Ch\.?|Kapitel|Chapitre|Capitulo|Capitolo)\s*"
    r"(?:[IVXLCDM]+|\d+)"
    r"(?:\s*[:\-\.\s]\s*.*)?"
    r"|"
    r"(?:Prologue|PROLOGUE|Epilogue|EPILOGUE|Introduction|INTRODUCTION)"
    r"(?:\s*[:\-\.\s]\s*.*)?"
    r")\s*(?:\n|$)",
    re.MULTILINE | re.IGNORECASE,
)


def detect_language_from_iso(iso_code: str | None) -> str:
    """Convert ISO language code to ttsforge language code."""
    if not iso_code:
        return "a"  # Default to American English
    iso_lower = iso_code.lower().strip()
    return ISO_TO_LANG_CODE.get(iso_lower, ISO_TO_LANG_CODE.get(iso_lower[:2], "a"))


def get_voice_language(voice: str) -> str:
    """Get the language code from a voice name."""
    prefix = voice[:2] if len(voice) >= 2 else ""
    return VOICE_PREFIX_TO_LANG.get(prefix, "a")


def get_default_voice_for_language(lang_code: str) -> str:
    """Get the default voice for a language."""
    return DEFAULT_VOICE_FOR_LANG.get(lang_code, "af_bella")


class TTSConverter:
    """Converts text to speech using Kokoro ONNX TTS."""

    def __init__(
        self,
        options: ConversionOptions,
        progress_callback: Callable[[ConversionProgress], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        """
        Initialize the TTS converter.

        Args:
            options: Conversion options
            progress_callback: Called with progress updates
            log_callback: Called with log messages (message, level)
        """
        self.options = options
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self._cancel_event = threading.Event()
        self._runner: KokoroRunner | None = None
        self._merger = AudioMerger(log=self.log)
        self._resolved_sentence_models: dict[str, str] = {}
        self._resolved_g2p_models: dict[str, str] = {}
        self._spacy_reported: set[tuple[str, str]] = set()

    @property
    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def log(self, message: str, level: str = "info") -> None:
        """Log a message."""
        if self.log_callback:
            self.log_callback(message, level)

    def cancel(self) -> None:
        """Request cancellation of the conversion."""
        self._cancel_event.set()

    def close(self) -> None:
        """Close the lazily created TTS runner, if any."""
        provider = self.options.effective_onnx_provider()
        log_snapshot(self.log, "before converter close", provider=provider)
        runner, self._runner = self._runner, None
        try:
            if runner is not None:
                runner.close()
        finally:
            log_snapshot(self.log, "after converter close", provider=provider)

    def __enter__(self) -> TTSConverter:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _init_runner(self) -> None:
        """Initialize the Kokoro runner."""
        if self._runner is not None:
            return

        from .kokoro_runner import KokoroRunner, KokoroRunOptions

        self.log("Initializing ONNX TTS pipeline...")

        # Create TokenizerConfig from ConversionOptions (for mixed-language support)
        from pykokoro.tokenizer import TokenizerConfig

        tokenizer_config = TokenizerConfig(
            use_spacy=self.options.use_spacy,
            spacy_model=self.options.spacy_model,
            spacy_model_size=self.options.spacy_model_size,
            use_mixed_language=self.options.use_mixed_language,
            mixed_language_primary=self.options.mixed_language_primary,
            mixed_language_allowed=self.options.mixed_language_allowed,
            mixed_language_confidence=self.options.mixed_language_confidence,
            phoneme_dictionary_path=self.options.phoneme_dictionary_path,
            phoneme_dict_case_sensitive=self.options.phoneme_dict_case_sensitive,
        )

        opts = KokoroRunOptions(
            voice=self.options.voice,
            speed=self.options.speed,
            use_gpu=self.options.use_gpu,
            onnx_provider=self.options.effective_onnx_provider(),
            pause_clause=self.options.pause_clause,
            pause_sentence=self.options.pause_sentence,
            pause_paragraph=self.options.pause_paragraph,
            pause_variance=self.options.pause_variance,
            random_seed=self.options.random_seed,
            enable_short_sentence=self.options.enable_short_sentence,
            short_sentence_config=resolve_short_sentence_config(
                self.options.short_sentence,
                language_code=self.options.language,
                warn=lambda message: self.log(message, "warning"),
            ),
            model_quality=self.options.model_quality,
            model_source=self.options.model_source,
            model_variant=self.options.model_variant,
            model_path=self.options.model_path,
            voices_path=self.options.voices_path,
            voice_blend=self.options.voice_blend,
            voice_database=self.options.voice_database,
            tokenizer_config=tokenizer_config,
            use_spacy=self.options.use_spacy,
            spacy_model=self.options.spacy_model,
            spacy_model_size=self.options.spacy_model_size,
            spacy_policy=SPACY_POLICY_VERSION,
            resolved_sentence_models=dict(self._resolved_sentence_models),
            resolved_g2p_models=dict(self._resolved_g2p_models),
            ssmd_policy=self.options.ssmd_policy,
            prosody_policy=self.options.prosody_policy,
        )
        self._runner = KokoroRunner(opts, log=self.log)
        self._runner.ensure_ready()

    def _effective_spacy_languages(self) -> tuple[str, ...]:
        """Return deterministic known languages for conversion preflight."""
        values: list[str | None] = [self.options.lang or self.options.language]
        if self.options.use_mixed_language:
            values.extend(self.options.mixed_language_allowed or ())
            values.append(self.options.mixed_language_primary)
        return tuple(sorted({normalize_language(value) for value in values if value}))

    def _preflight_spacy_models(self) -> None:
        """Resolve and freeze sentence/G2P models before generation begins."""
        request = SpacyModelRequest(
            use_spacy=self.options.use_spacy,
            model=self.options.spacy_model,
            size=self.options.spacy_model_size,
        )
        sentence: dict[str, str] = {}
        g2p: dict[str, str] = {}
        for language in self._effective_spacy_languages():
            sentence_selection = resolve_spacy_model_for_component(
                language=language,
                request=request,
                component="sentence",
                require=request.strict,
            )
            g2p_selection = resolve_spacy_model_for_component(
                language=language,
                request=request,
                component="g2p",
                require=request.strict,
            )
            if sentence_selection.model:
                sentence[language] = sentence_selection.model
            if g2p_selection.model:
                g2p[language] = g2p_selection.model
            for component, selection in (
                ("sentence", sentence_selection),
                ("g2p", g2p_selection),
            ):
                marker = (component, language)
                if marker not in self._spacy_reported:
                    report_selection(selection, log=self.log)
                    self._spacy_reported.add(marker)
        self._resolved_sentence_models = dict(sorted(sentence.items()))
        self._resolved_g2p_models = dict(sorted(g2p.items()))

    @property
    def resolved_spacy_models(self) -> dict[str, dict[str, str]]:
        """Return frozen model maps for state/fingerprint consumers."""
        return {
            "sentence": dict(sorted(self._resolved_sentence_models.items())),
            "g2p": dict(sorted(self._resolved_g2p_models.items())),
        }

    def _build_ssmd_content(
        self,
        chapter: Chapter,
        phoneme_dict: dict[str, str] | None,
        mixed_language_config: dict[str, Any] | None,
    ) -> str:
        """Generate validated SSMD content for a chapter."""
        try:
            return chapter_to_ssmd(
                chapter_title=chapter.title,
                chapter_text=chapter.text,
                phoneme_dict=phoneme_dict,
                phoneme_dict_case_sensitive=self.options.phoneme_dict_case_sensitive,
                mixed_language_config=mixed_language_config,
                chapter_markdown=(
                    chapter.markdown_body
                    if chapter.source_format == "markdown"
                    else None
                ),
                source_format=(
                    "markdown" if chapter.source_format == "markdown" else "plain"
                ),
                include_title=self.options.announce_chapters,
            )
        except SSMDGenerationError as e:
            self.log(f"SSMD generation failed: {e}", "error")
            raise

    def _load_or_generate_ssmd(
        self,
        chapter: Chapter,
        ssmd_file: Path,
        phoneme_dict: dict[str, str] | None,
        mixed_language_config: dict[str, Any] | None,
    ) -> tuple[str, str, SSMDDocumentInfo]:
        """Load SSMD from disk or generate and save it."""
        ssmd_content: str | None = None
        ssmd_hash = ""

        if chapter.is_ssmd:
            if ssmd_file.exists():
                try:
                    ssmd_content, ssmd_hash = load_ssmd_file(ssmd_file)
                    info = validate_ssmd_document(
                        ssmd_content,
                        policy=self.options.ssmd_policy,
                        source=ssmd_file,
                    )
                    self.log(f"Loaded SSMD from {ssmd_file.name}")
                except SSMDGenerationError as e:
                    self.log(f"Failed to load SSMD: {e}", "error")
                    raise

            if ssmd_content is None:
                ssmd_content = chapter.text
                ssmd_hash = save_ssmd_file(
                    ssmd_content, ssmd_file, policy=self.options.ssmd_policy
                )
                info = validate_ssmd_document(
                    ssmd_content,
                    policy=self.options.ssmd_policy,
                    source=ssmd_file,
                )
                self.log(f"Saved SSMD to {ssmd_file.name}")

            assert info is not None
            return ssmd_content, ssmd_hash, info

        if ssmd_file.exists():
            try:
                ssmd_content, ssmd_hash = load_ssmd_file(ssmd_file)
                info = validate_ssmd_document(
                    ssmd_content,
                    policy=self.options.ssmd_policy,
                    source=ssmd_file,
                )
                self.log(f"Loaded SSMD from {ssmd_file.name}")
            except SSMDGenerationError as e:
                self.log(f"Failed to load SSMD: {e}", "error")
                raise

        if ssmd_content is None:
            self.log(f"Generating SSMD for chapter: {chapter.title}")
            ssmd_content = self._build_ssmd_content(
                chapter,
                phoneme_dict=phoneme_dict,
                mixed_language_config=mixed_language_config,
            )
            ssmd_hash = save_ssmd_file(
                ssmd_content, ssmd_file, policy=self.options.ssmd_policy
            )
            info = validate_ssmd_document(
                ssmd_content,
                policy=self.options.ssmd_policy,
                source=ssmd_file,
            )
            self.log(f"Saved SSMD to {ssmd_file.name}")

        assert info is not None
        return ssmd_content, ssmd_hash, info

    def _render_chapter_wav(
        self,
        chapter: Chapter,
        output_file: Path,
        ssmd_content: str,
        ssmd_file: Path,
    ) -> RenderedChapter:
        """Render SSMD content to a chapter WAV file."""
        effective_lang = (
            self.options.lang if self.options.lang else self.options.language
        )
        lang_code = get_onnx_lang_code(effective_lang)

        temp_path: Path | None = None
        result: Any | None = None
        samples: Any | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_file.name}.",
                suffix=".tmp.wav",
                dir=output_file.parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
            resolver = LocalSSMDAudioResolver(
                ssmd_file.parent,
                allowed_root=self.options.ssmd_policy.audio_root or ssmd_file.parent,
                allow_remote=self.options.ssmd_policy.allow_remote_audio,
                timeout_s=self.options.ssmd_policy.audio_timeout_s,
                max_bytes=self.options.ssmd_policy.audio_max_bytes,
                max_duration_s=self.options.ssmd_policy.audio_max_duration_s,
            )
            assert self._runner is not None
            log_snapshot(
                self.log,
                "before chapter synthesis",
                provider=self.options.effective_onnx_provider(),
            )
            result = self._runner.synthesize(
                ssmd_content,
                lang_code=lang_code,
                pause_mode=cast(
                    Literal["tts", "manual", "auto"], self.options.pause_mode
                ),
                is_phonemes=False,
                audio_resolver=resolver,
            )
            log_snapshot(
                self.log,
                "after synthesis",
                provider=self.options.effective_onnx_provider(),
            )
            samples = result.audio
            sample_rate = int(result.sample_rate or SAMPLE_RATE)
            duration = len(samples) / sample_rate
            diagnostics = _result_issues(result)
            markers = _marker_records(result)
            document_metadata = {
                key: value
                for key, value in (
                    getattr(result, "document_metadata", {}) or {}
                ).items()
                if key in {"title", "voice_bindings", "pause_defaults"}
            }
            with sf.SoundFile(
                str(temp_path),
                "w",
                samplerate=sample_rate,
                channels=1,
                format="wav",
            ) as out_file:
                out_file.write(samples)
            log_snapshot(
                self.log,
                "after WAV write",
                provider=self.options.effective_onnx_provider(),
            )
            rendered_path = temp_path
            temp_path = None
            return RenderedChapter(
                duration=duration,
                rendered_path=rendered_path,
                sample_rate=sample_rate,
                diagnostics=diagnostics,
                markers=markers,
                document_metadata=document_metadata,
            )
        finally:
            samples = None
            if result is not None:
                try:
                    result.release_audio()
                except Exception as exc:
                    self.log(
                        f"Failed to release PyKokoro audio buffers: {exc}",
                        "warning",
                    )
                log_snapshot(
                    self.log,
                    "after result.release_audio()",
                    provider=self.options.effective_onnx_provider(),
                )
            result = None
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _paragraph_ownership(
        self, *, state: ConversionState, output_path: Path, work_dir: Path
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "workspace_id": work_dir.name,
            "source_hash": state.source_hash,
            "output_path": str(output_path.resolve()),
            "conversion_unit": "paragraph",
        }

    def _paragraph_units_valid(
        self, units: Sequence[RenderUnitState], directory: Path
    ) -> bool:
        for unit in units:
            if not unit.completed or not unit.audio_file:
                return False
            try:
                path = owned_path(directory, unit.audio_file)
                validate_wav(
                    path,
                    sample_rate=unit.sample_rate,
                    expected_duration=unit.duration if unit.duration else None,
                )
                if (
                    unit.marker_file
                    and not owned_path(directory, unit.marker_file).is_file()
                ):
                    return False
            except (OSError, ValueError):
                return False
        return True

    def _paragraph_marker_records(
        self, state: ConversionState, directory: Path
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        base_samples = 0
        for chapter in state.chapters:
            for unit in sorted(chapter.units, key=lambda item: item.sequence_index):
                if unit.marker_file:
                    marker_path = owned_path(directory, unit.marker_file)
                    try:
                        marker_data = json.loads(
                            marker_path.read_text(encoding="utf-8")
                        )
                    except (OSError, json.JSONDecodeError):
                        marker_data = {}
                    for marker in marker_data.get("markers", []):
                        local_offset = int(marker.get("sample_offset", 0))
                        absolute_offset = base_samples + local_offset
                        records.append(
                            {
                                **marker,
                                "sample_offset": absolute_offset,
                                "time_s": absolute_offset / unit.sample_rate,
                                "unit_sequence": unit.sequence_index,
                                "unit_index": unit.unit_index,
                            }
                        )
                base_samples += int(round(unit.duration * unit.sample_rate))
        return records

    def _merge_paragraph_state(
        self,
        *,
        state: ConversionState,
        output_path: Path,
        work_dir: Path,
        paragraph_dir: Path,
        chapter_titles: Mapping[int, str],
        aggregate_metadata: dict[str, Any] | None = None,
    ) -> ConversionResult:
        all_units = [
            unit
            for chapter in state.chapters
            for unit in sorted(chapter.units, key=lambda item: item.sequence_index)
        ]
        if not all_units or not self._paragraph_units_valid(all_units, paragraph_dir):
            return ConversionResult(
                success=False,
                error_message="Paragraph output contains"
                " incomplete or invalid unit files",
                chapters_dir=work_dir,
                conversion_unit="paragraph",
                paragraphs_dir=paragraph_dir,
                unit_count=len(all_units),
            )

        ownership = self._paragraph_ownership(
            state=state, output_path=output_path, work_dir=work_dir
        )
        rebuild_manifest_and_playlist(
            paragraph_dir,
            ownership=ownership,
            units=all_units,
            chapter_titles=chapter_titles,
        )
        ordered = [
            OrderedAudioInput(
                path=owned_path(paragraph_dir, unit.audio_file or ""),
                sequence_index=unit.sequence_index,
                chapter_position=unit.chapter_position,
                chapter_title=chapter_titles.get(unit.chapter_position, "Untitled"),
                duration=unit.duration,
                content_duration=unit.content_duration,
                trailing_chapter_silence=unit.trailing_chapter_silence,
            )
            for unit in all_units
        ]
        boundaries: list[ChapterBoundary] = []
        timeline = 0.0
        for chapter in state.chapters:
            if not chapter.units:
                continue
            chapter_start = timeline
            content_end = timeline + sum(
                unit.content_duration for unit in chapter.units
            )
            timeline += sum(unit.duration for unit in chapter.units)
            boundaries.append(
                ChapterBoundary(
                    chapter_position=chapter.units[0].chapter_position,
                    title=chapter_titles.get(
                        chapter.units[0].chapter_position, chapter.title
                    ),
                    start=chapter_start,
                    end=content_end,
                )
            )
        meta = MergeMeta(
            fmt=self.options.output_format,
            silence_between_chapters=0.0,
            title=self.options.title,
            author=self.options.author,
            cover_image=self.options.cover_image,
        )
        self._merger.merge_ordered_wavs(
            ordered,
            output_path,
            chapter_boundaries=boundaries,
            meta=meta,
        )
        aggregate_markers = self._paragraph_marker_records(state, paragraph_dir)
        atomic_write_json(
            output_path.with_suffix(output_path.suffix + ".markers.json"),
            {
                "schema_version": 1,
                "sample_rate": SAMPLE_RATE,
                "markers": aggregate_markers,
            },
            indent=2,
            ensure_ascii=True,
        )
        return ConversionResult(
            success=True,
            output_path=output_path,
            chapters_dir=work_dir,
            paragraphs_dir=paragraph_dir,
            conversion_unit="paragraph",
            unit_count=len(all_units),
            document_metadata=aggregate_metadata or {},
            markers=aggregate_markers,
            short_sentence_stats=self._short_sentence_stats(),
        )

    def _convert_paragraph_chapters(
        self,
        *,
        chapters: list[Chapter],
        output_path: Path,
        work_dir: Path,
        state_file: Path,
        state: ConversionState,
        phoneme_dict: dict[str, str] | None,
        mixed_language_config: dict[str, Any] | None,
    ) -> ConversionResult:
        """Render selected chapters as independently resumable paragraph WAVs."""
        paragraph_dir = Path(state.paragraphs_dir or paragraph_directory(output_path))
        state.paragraphs_dir = str(paragraph_dir)
        ownership = self._paragraph_ownership(
            state=state, output_path=output_path, work_dir=work_dir
        )
        ensure_owned_directory(paragraph_dir, ownership=ownership)
        chapter_titles = {
            position: chapter.title for position, chapter in enumerate(chapters)
        }
        all_units = [unit for chapter in state.chapters for unit in chapter.units]

        # Merge-only recovery deliberately does not initialize PyKokoro.
        if (
            state.is_complete()
            and all_units
            and self._paragraph_units_valid(all_units, paragraph_dir)
        ):
            return self._merge_paragraph_state(
                state=state,
                output_path=output_path,
                work_dir=work_dir,
                paragraph_dir=paragraph_dir,
                chapter_titles=chapter_titles,
            )

        self._init_runner()
        assert self._runner is not None
        effective_lang = (
            self.options.lang if self.options.lang else self.options.language
        )
        lang_code = get_onnx_lang_code(effective_lang)
        resolver_root = work_dir
        resolver = LocalSSMDAudioResolver(
            resolver_root,
            allowed_root=self.options.ssmd_policy.audio_root or resolver_root,
            allow_remote=self.options.ssmd_policy.allow_remote_audio,
            timeout_s=self.options.ssmd_policy.audio_timeout_s,
            max_bytes=self.options.ssmd_policy.audio_max_bytes,
            max_duration_s=self.options.ssmd_policy.audio_max_duration_s,
        )
        estimator = UnitRateEstimator()
        aggregate_metadata: dict[str, Any] = {}
        sequence_start = 0
        total_chars = sum(chapter.char_count for chapter in chapters)
        chars_processed = sum(
            unit.char_count
            for saved_chapter in state.chapters
            for unit in saved_chapter.units
            if unit.completed
        )

        for chapter_position, chapter in enumerate(chapters):
            if self._cancelled:
                state.save(state_file)
                return ConversionResult(
                    success=False,
                    error_message="Cancelled",
                    chapters_dir=work_dir,
                    paragraphs_dir=paragraph_dir,
                    conversion_unit="paragraph",
                    unit_count=state.get_total_unit_count(),
                )
            chapter_state = state.chapters[chapter_position]
            ssmd_filename = f"chapter_{chapter_position + 1:06d}.ssmd"
            ssmd_file = work_dir / ssmd_filename
            ssmd_content, ssmd_hash, document_info = self._load_or_generate_ssmd(
                chapter,
                ssmd_file,
                phoneme_dict=phoneme_dict,
                mixed_language_config=mixed_language_config,
            )
            chapter_state.ssmd_file = ssmd_filename
            chapter_state.ssmd_hash = ssmd_hash
            chapter_state.ssmd_document_title = document_info.title
            if self._cancelled:
                state.save(state_file)
                return ConversionResult(success=False, error_message="Cancelled")

            with self._runner.prepare_paragraph_units(
                ssmd_content,
                lang_code=lang_code,
                pause_mode=cast(
                    Literal["tts", "manual", "auto"], self.options.pause_mode
                ),
                ssmd_policy=self.options.ssmd_policy,
                audio_resolver=resolver,
            ) as prepared:
                planned = map_descriptors(
                    prepared.units,
                    chapter_position=chapter_position,
                    source_chapter_index=chapter.index,
                    chapter_fingerprint=chapter_state.render_fingerprint,
                    sequence_start=sequence_start,
                    announced_title=(
                        self.options.announce_chapters and not chapter.is_ssmd
                    ),
                    sample_rate=SAMPLE_RATE,
                )
                for unit in planned:
                    filename = canonical_filename(
                        sequence_index=unit.sequence_index + 1,
                        source_chapter_index=unit.source_chapter_index,
                        paragraph_index=int(unit.chapter_unit_index or 0),
                        kind=unit.kind,
                        chapter_title=chapter.title,
                    )
                    unit.audio_file = filename
                    unit.marker_file = f"{filename}.markers.json"
                reconciled, stale = reconcile_units(chapter_state.units, planned)
                chapter_state.units = reconciled
                chapter_state.audio_file = None
                chapter_state.completed = not planned
                for old in stale:
                    for name in (old.audio_file, old.marker_file):
                        if name:
                            try:
                                owned_path(paragraph_dir, name).unlink(missing_ok=True)
                            except ValueError:
                                pass

                # Verify retained artifacts before asking PyKokoro to render.
                first_invalid: int | None = None
                for index, unit in enumerate(chapter_state.units):
                    if not unit.completed:
                        continue
                    try:
                        validate_wav(
                            owned_path(paragraph_dir, unit.audio_file or ""),
                            sample_rate=unit.sample_rate,
                            expected_duration=unit.duration if unit.duration else None,
                        )
                        if (
                            unit.marker_file
                            and not owned_path(
                                paragraph_dir, unit.marker_file
                            ).is_file()
                        ):
                            raise ValueError("marker sidecar missing")
                    except (OSError, ValueError):
                        first_invalid = index
                        break
                if first_invalid is not None:
                    for unit in chapter_state.units[first_invalid:]:
                        unit.completed = False
                        unit.duration = 0.0
                        unit.content_duration = 0.0
                chars_processed = sum(
                    unit.char_count
                    for saved_chapter in state.chapters
                    for unit in saved_chapter.units
                    if unit.completed
                )
                chapter_state.completed = not chapter_state.units or all(
                    unit.completed for unit in chapter_state.units
                )
                state.save(state_file)  # plan is durable before first inference

                skip_indices = {
                    unit.unit_index for unit in chapter_state.units if unit.completed
                }
                by_index = {unit.unit_index: unit for unit in chapter_state.units}
                for result in prepared.render(skip_indices=skip_indices):
                    if self._cancelled:
                        state.save(state_file)
                        try:
                            result.release_audio()
                        finally:
                            pass
                        return ConversionResult(
                            success=False,
                            error_message="Cancelled",
                            chapters_dir=work_dir,
                            paragraphs_dir=paragraph_dir,
                            conversion_unit="paragraph",
                            unit_count=state.get_total_unit_count(),
                        )
                    unit_index = int(result.descriptor.index)
                    unit = by_index[unit_index]
                    started = time.monotonic()
                    try:
                        samples = np.asarray(result.audio)
                        sample_rate = int(result.sample_rate or SAMPLE_RATE)
                        unit.sample_rate = sample_rate
                        unit.content_duration = len(samples) / sample_rate
                        trailing = (
                            self.options.silence_between_chapters
                            if unit is chapter_state.units[-1]
                            and chapter_position < len(chapters) - 1
                            else 0.0
                        )
                        unit.trailing_chapter_silence = trailing
                        destination = owned_path(paragraph_dir, unit.audio_file or "")
                        if self._cancelled:
                            state.save(state_file)
                            return ConversionResult(
                                success=False,
                                error_message="Cancelled",
                                chapters_dir=work_dir,
                                paragraphs_dir=paragraph_dir,
                                conversion_unit="paragraph",
                                unit_count=state.get_total_unit_count(),
                            )
                        unit.duration = finalize_wav(
                            samples=samples,
                            sample_rate=sample_rate,
                            destination=destination,
                            trailing_chapter_silence=trailing,
                        )
                        _write_marker_records_sidecar(
                            owned_path(paragraph_dir, unit.marker_file or ""),
                            sample_rate=sample_rate,
                            markers=_marker_records(result),
                        )
                        unit.render_wall_seconds = time.monotonic() - started
                        unit.completed = True
                        chapter_state.completed = all(
                            item.completed for item in chapter_state.units
                        )
                        state.save(state_file)
                        rebuild_manifest_and_playlist(
                            paragraph_dir,
                            ownership=ownership,
                            units=[
                                item
                                for saved_chapter in state.chapters
                                for item in saved_chapter.units
                            ],
                            chapter_titles=chapter_titles,
                        )
                        estimator.add(unit.render_wall_seconds, unit.char_count)
                        chars_processed += unit.char_count
                        progress = ConversionProgress(
                            current_chapter=chapter_position + 1,
                            total_chapters=len(chapters),
                            chapter_name=chapter.title,
                            chars_processed=chars_processed,
                            total_chars=total_chars,
                            current_unit=unit.sequence_index + 1,
                            total_units=state.get_total_unit_count(),
                            current_paragraph=int(unit.chapter_unit_index or 0),
                            paragraphs_in_chapter=len(chapter_state.units),
                            unit_kind=unit.kind,
                            estimated_remaining=estimator.estimate(
                                sum(
                                    1
                                    for saved_chapter in state.chapters
                                    for saved_unit in saved_chapter.units
                                    if not saved_unit.completed
                                ),
                                total_chars - chars_processed,
                            ),
                        )
                        if self.progress_callback:
                            self.progress_callback(progress)
                        if self._cancelled:
                            state.save(state_file)
                            return ConversionResult(
                                success=False,
                                error_message="Cancelled",
                                chapters_dir=work_dir,
                                paragraphs_dir=paragraph_dir,
                                conversion_unit="paragraph",
                                unit_count=state.get_total_unit_count(),
                            )
                    finally:
                        try:
                            result.release_audio()
                        except Exception as exc:
                            self.log(
                                f"Failed to release PyKokoro unit audio: {exc}",
                                "warning",
                            )
                aggregate_metadata.update(prepared.document_metadata)
            sequence_start += len(chapter_state.units)
            chapter_state.completed = not chapter_state.units or all(
                unit.completed for unit in chapter_state.units
            )
            state.save(state_file)

        state.save(state_file)
        return self._merge_paragraph_state(
            state=state,
            output_path=output_path,
            work_dir=work_dir,
            paragraph_dir=paragraph_dir,
            chapter_titles=chapter_titles,
            aggregate_metadata=aggregate_metadata,
        )

    def _generation_fingerprint(self) -> str:
        """Fingerprint every option that can affect generated audio."""
        options = self.options
        dictionary = _path_identity(options.phoneme_dictionary_path)
        payload = {
            "voice": options.voice,
            "voice_blend": options.voice_blend,
            "voice_database": _path_identity(options.voice_database),
            "language": options.language,
            "lang": options.lang,
            "speed": options.speed,
            "output_format": options.output_format,
            "use_gpu": options.use_gpu,
            "onnx_provider": options.effective_onnx_provider(),
            "model_quality": str(options.model_quality),
            "model_source": str(options.model_source),
            "model_variant": str(options.model_variant),
            "model_path": _path_identity(options.model_path),
            "voices_path": _path_identity(options.voices_path),
            "silence_between_chapters": options.silence_between_chapters,
            "pause_clause": options.pause_clause,
            "pause_sentence": options.pause_sentence,
            "pause_paragraph": options.pause_paragraph,
            "pause_variance": options.pause_variance,
            "random_seed": options.random_seed,
            "pause_mode": options.pause_mode,
            "enable_short_sentence": options.enable_short_sentence,
            "short_sentence": options.short_sentence,
            "use_mixed_language": options.use_mixed_language,
            "mixed_language_primary": options.mixed_language_primary,
            "mixed_language_allowed": options.mixed_language_allowed,
            "mixed_language_confidence": options.mixed_language_confidence,
            "phoneme_dictionary": dictionary,
            "phoneme_dict_case_sensitive": options.phoneme_dict_case_sensitive,
            "spacy": {
                "policy": SPACY_POLICY_VERSION,
                "use_spacy": options.use_spacy,
                "requested_model": options.spacy_model,
                "requested_size": options.spacy_model_size,
                "resolved_sentence_models": dict(
                    sorted(self._resolved_sentence_models.items())
                ),
                "resolved_g2p_models": dict(sorted(self._resolved_g2p_models.items())),
            },
            "announce_chapters": options.announce_chapters,
            "chapter_pause_after_title": options.chapter_pause_after_title,
            "split_mode": options.split_mode,
            "conversion_unit": options.conversion_unit,
            "paragraph_output_schema": PARAGRAPH_OUTPUT_SCHEMA,
            "paragraph_pause_ownership": "following-boundary-owned-by-previous-v1",
            "generate_ssmd_only": options.generate_ssmd_only,
            "detect_emphasis": options.detect_emphasis,
            "epub_content_mode": options.epub_content_mode,
            "epub_heading_policy": "minimum_body_heading_level=2",
            "epub_scene_break_policy": "preserve",
            "text_postprocess_options": vars(options.text_postprocess_options),
            "ssmd_policy": _ssmd_policy_payload(options.ssmd_policy),
            "prosody_policy": prosody_policy_payload(options.prosody_policy),
        }
        return _canonical_fingerprint(payload)

    def _resume_state_matches(
        self,
        state: ConversionState,
        chapters: list[Chapter],
        source_hash: str,
        generation_fingerprint: str,
        work_dir: Path,
        output_path: Path | None = None,
    ) -> ResumeValidation:
        """Validate resume state and return structured result."""
        result = self._resume_state_validation(
            state, chapters, source_hash, generation_fingerprint, work_dir, output_path
        )
        return result

    def _resume_state_matches_bool(
        self,
        state: ConversionState,
        chapters: list[Chapter],
        source_hash: str,
        generation_fingerprint: str,
        work_dir: Path,
        output_path: Path | None = None,
    ) -> bool:
        """Compatibility wrapper returning bool."""
        return self._resume_state_matches(
            state,
            chapters,
            source_hash,
            generation_fingerprint,
            work_dir,
            output_path,
        ).reusable

    def _resume_state_validation(
        self,
        state: ConversionState,
        chapters: list[Chapter],
        source_hash: str,
        generation_fingerprint: str,
        work_dir: Path,
        output_path: Path | None = None,
    ) -> ResumeValidation:
        """Allow reuse only when v2 inputs and completed artifacts still match."""
        has_markdown_source = any(
            chapter.source_format == "markdown" for chapter in chapters
        )
        if (
            self.options.epub_content_mode == "markdown"
            and has_markdown_source
            and state.version < 4
        ):
            self.log(
                "EPUB extraction format changed from plain to markdown; "
                "rebuilding chapter artifacts.",
                "warning",
            )
            return ResumeValidation(
                reusable=False,
                reason="epub-extraction-format-changed",
            )
        if state.version < 2:
            self.log(
                "Legacy resume state is unsafe; starting fresh conversion", "warning"
            )
            return ResumeValidation(reusable=False, reason="legacy-state-version")
        if state.source_hash != source_hash:
            self.log(
                "Source file or chapter inputs changed, starting fresh conversion",
                "warning",
            )
            return ResumeValidation(reusable=False, reason="source-hash-changed")
        if output_path is not None and state.output_file:
            saved_output = Path(state.output_file)
            if saved_output.resolve() != output_path.resolve():
                self.log(
                    "Output path changed, use --fresh to start a new conversion",
                    "warning",
                )
                return ResumeValidation(reusable=False, reason="output-path-changed")
        if state.onnx_provider is None:
            self.log(
                "Resume state predates provider-aware fingerprints; "
                "starting fresh conversion",
                "warning",
            )
            return ResumeValidation(
                reusable=False, reason="missing-provider-fingerprint"
            )
        if state.onnx_provider != self.options.effective_onnx_provider():
            self.log("ONNX provider changed, starting fresh conversion", "warning")
            return ResumeValidation(reusable=False, reason="provider-changed")
        if state.conversion_unit != self.options.conversion_unit:
            self.log(
                "Conversion unit changed, use --fresh to start a new conversion",
                "warning",
            )
            return ResumeValidation(reusable=False, reason="conversion-unit-changed")
        if state.source_selection != [chapter.index for chapter in chapters]:
            self.log("Chapter selection changed, starting fresh conversion", "warning")
            return ResumeValidation(reusable=False, reason="chapter-selection-changed")
        if state.spacy_policy != SPACY_POLICY_VERSION:
            self.log(
                "spaCy model policy changed; restart is required for resume safety",
                "warning",
            )
            return ResumeValidation(reusable=False, reason="spacy-policy-changed")
        if state.use_spacy != self.options.use_spacy:
            self.log("spaCy enablement changed, starting fresh conversion", "warning")
            return ResumeValidation(reusable=False, reason="spacy-enablement-changed")
        if (
            state.spacy_model != self.options.spacy_model
            or state.spacy_model_size != self.options.spacy_model_size
        ):
            self.log(
                "spaCy model request changed, starting fresh conversion",
                "warning",
            )
            return ResumeValidation(reusable=False, reason="spacy-request-changed")
        stored_sentence = dict(sorted(state.resolved_sentence_models.items()))
        stored_g2p = dict(sorted(state.resolved_g2p_models.items()))
        if (
            stored_sentence != self._resolved_sentence_models
            or stored_g2p != self._resolved_g2p_models
        ):
            self.log(
                "Resolved spaCy model set changed; restart is required to avoid "
                "mixing audio",
                "warning",
            )
            return ResumeValidation(
                reusable=False, reason="spacy-model-resolution-changed"
            )
        for component, models in (
            ("sentence", stored_sentence),
            ("G2P", stored_g2p),
        ):
            for language, model in models.items():
                try:
                    ensure_model_loadable(model)
                except SpacyPolicyError:
                    self.log(
                        f"Stored spaCy {component} model '{model}' for {language} "
                        "is unavailable; restart is required",
                        "warning",
                    )
                    return ResumeValidation(
                        reusable=False,
                        reason=f"spacy-model-unavailable:{language}:{model}",
                    )
        if state.generation_fingerprint != generation_fingerprint:
            self.log(
                "Generation settings changed, starting fresh conversion",
                "warning",
            )
            return ResumeValidation(
                reusable=False, reason="generation-fingerprint-changed"
            )
        if len(state.chapters) != len(chapters):
            self.log("Chapter count changed, starting fresh conversion", "warning")
            return ResumeValidation(reusable=False, reason="chapter-count-changed")

        for saved, chapter in zip(state.chapters, chapters, strict=True):
            content_hash = _hash_content(chapter.content)
            render_fingerprint = _chapter_render_fingerprint(
                chapter, generation_fingerprint
            )
            if (
                saved.index != chapter.index
                or saved.title != chapter.title
                or saved.content_hash != content_hash
                or saved.source_format != chapter.source_format
                or saved.source_id != chapter.source_id
                or saved.source_markup_hash != _chapter_source_markup_hash(chapter)
                or saved.extraction_schema != chapter.extraction_schema
                or saved.render_fingerprint != render_fingerprint
            ):
                self.log(
                    f"Chapter {chapter.index + 1} changed, starting fresh conversion",
                    "warning",
                )
                return ResumeValidation(
                    reusable=False, reason="chapter-content-changed"
                )
            if saved.completed and state.conversion_unit == "chapter":
                if not saved.audio_file:
                    return ResumeValidation(reusable=False, reason="missing-audio-file")
                audio_path = work_dir / saved.audio_file
                try:
                    if (
                        not audio_path.is_file()
                        or sf.info(str(audio_path)).duration <= 0
                    ):
                        return ResumeValidation(
                            reusable=False, reason="audio-file-invalid"
                        )
                except Exception:
                    return ResumeValidation(
                        reusable=False, reason="audio-file-unreadable"
                    )
                if (
                    saved.ssmd_markers_file
                    and not (work_dir / saved.ssmd_markers_file).is_file()
                ):
                    self.log(
                        "Marker sidecar is missing, starting fresh conversion",
                        "warning",
                    )
                    return ResumeValidation(
                        reusable=False, reason="marker-sidecar-missing"
                    )
                if (
                    saved.ssmd_diagnostics_file
                    and not (work_dir / saved.ssmd_diagnostics_file).is_file()
                ):
                    self.log(
                        "SSMD diagnostics sidecar is missing; "
                        "starting fresh conversion",
                        "warning",
                    )
                    return ResumeValidation(
                        reusable=False, reason="diagnostics-sidecar-missing"
                    )
        return ResumeValidation(reusable=True)

    def convert_chapters_resumable(  # noqa: C901 - Complex but necessary for resume logic
        self,
        chapters: list[Chapter],
        output_path: Path,
        source_file: Path | None = None,
        resume: bool = True,
    ) -> ConversionResult:
        """
        Convert chapters to audio with resume capability.

        Each chapter is saved as a separate WAV file, allowing conversion
        to be resumed if interrupted. A state file tracks progress.

        Args:
            chapters: List of Chapter objects
            output_path: Output file path
            source_file: Original source file (for state tracking)
            resume: Whether to resume from previous state

        Returns:
            ConversionResult with success status and paths
        """
        if not chapters:
            return ConversionResult(
                success=False, error_message="No chapters to convert"
            )

        if self.options.output_format not in SUPPORTED_OUTPUT_FORMATS:
            return ConversionResult(
                success=False,
                error_message=f"Unsupported format: {self.options.output_format}",
            )

        self._cancel_event.clear()
        prevent_sleep_start()

        try:
            # Compute workspace using shared helper when source_file is
            # available (CLI path); fall back to content-derived hash for
            # source-less API calls.
            if source_file is not None:
                workspace = resolve_conversion_workspace(
                    output_dir=output_path.parent,
                    book_title=self.options.title or output_path.stem,
                    source_file=source_file,
                )
                source_hash = workspace.source_hash
                work_dir = workspace.work_dir
                state_file = workspace.state_file
            else:
                safe_book_title = sanitize_filename(
                    self.options.title or output_path.stem
                )[:50]
                source_hash = _canonical_fingerprint(
                    [
                        {
                            "index": chapter.index,
                            "title": chapter.title,
                            "content": chapter.content,
                        }
                        for chapter in chapters
                    ]
                )
                source_key = source_hash[:12]
                work_dir = (
                    output_path.parent / f".{safe_book_title}-{source_key}_chapters"
                )
                state_file = work_dir / "state.json"
            work_dir.mkdir(parents=True, exist_ok=True)
            # SSMD-only generation does not initialize or use the TTS backend;
            # defer spaCy preflight until audio generation paths need it.
            if not self.options.generate_ssmd_only:
                self._preflight_spacy_models()
            generation_fingerprint = self._generation_fingerprint()

            # Load or create state
            state: ConversionState | None = None
            if resume and state_file.exists():
                state = ConversionState.load(state_file)
                if state:
                    validation = self._resume_state_matches(
                        state,
                        chapters,
                        source_hash,
                        generation_fingerprint,
                        work_dir,
                        output_path=output_path,
                    )
                    if not validation.reusable:
                        # Archive incompatible state before replacing it so
                        # evidence and completed artifacts are not silently lost.
                        import shutil

                        timestamp = time.strftime("%Y%m%dT%H%M%S")
                        archived_name = f"state.invalidated-{timestamp}.json"
                        archived_path = state_file.parent / archived_name
                        try:
                            shutil.copy2(state_file, archived_path)
                            self.log(
                                f"Archived incompatible state to {archived_name}",
                                "info",
                            )
                        except OSError:
                            pass
                        self.log(
                            f"Resume state incompatible: {validation.reason}",
                            "warning",
                        )
                        state = None

            if state is None:
                # Create new state
                state = ConversionState(
                    source_file=str(source_file) if source_file else "",
                    source_hash=source_hash,
                    version=5,
                    output_file=str(output_path.resolve()),
                    work_dir=str(work_dir),
                    voice=self.options.voice,
                    language=self.options.language,
                    speed=self.options.speed,
                    split_mode=self.options.split_mode,
                    conversion_unit=self.options.conversion_unit,
                    output_format=self.options.output_format,
                    model_quality=self.options.model_quality,
                    model_source=self.options.model_source,
                    model_variant=self.options.model_variant,
                    onnx_provider=self.options.effective_onnx_provider(),
                    silence_between_chapters=self.options.silence_between_chapters,
                    pause_clause=self.options.pause_clause,
                    pause_sentence=self.options.pause_sentence,
                    pause_paragraph=self.options.pause_paragraph,
                    pause_variance=self.options.pause_variance,
                    random_seed=self.options.random_seed,
                    pause_mode=self.options.pause_mode,
                    enable_short_sentence=self.options.enable_short_sentence,
                    short_sentence=self.options.short_sentence,
                    lang=self.options.lang,
                    use_spacy=self.options.use_spacy,
                    spacy_model=self.options.spacy_model,
                    spacy_model_size=self.options.spacy_model_size,
                    spacy_policy=SPACY_POLICY_VERSION,
                    resolved_sentence_models=dict(self._resolved_sentence_models),
                    resolved_g2p_models=dict(self._resolved_g2p_models),
                    chapters=[
                        ChapterState(
                            index=ch.index,
                            title=ch.title,
                            content_hash=_hash_content(ch.content),
                            source_format=ch.source_format,
                            source_id=ch.source_id,
                            source_markup_hash=_chapter_source_markup_hash(ch),
                            extraction_schema=ch.extraction_schema,
                            char_count=ch.char_count,
                            render_fingerprint=_chapter_render_fingerprint(
                                ch, generation_fingerprint
                            ),
                        )
                        for ch in chapters
                    ],
                    source_selection=[chapter.index for chapter in chapters],
                    generation_fingerprint=generation_fingerprint,
                    ssmd_policy_fingerprint=_canonical_fingerprint(
                        _ssmd_policy_payload(self.options.ssmd_policy)
                    ),
                    started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    paragraphs_dir=(
                        str(
                            output_path.with_suffix("").parent
                            / f"{output_path.stem}_paragraphs"
                        )
                        if self.options.conversion_unit == "paragraph"
                        else None
                    ),
                )
                state.save(state_file)
            else:
                completed = state.get_completed_count()
                total = len(chapters)
                self.log(f"Resuming conversion: {completed}/{total} chapters completed")

            if self.options.conversion_unit == "paragraph":
                phoneme_dict = None
                if self.options.phoneme_dictionary_path:
                    phoneme_dict = load_phoneme_dictionary(
                        self.options.phoneme_dictionary_path,
                        case_sensitive=self.options.phoneme_dict_case_sensitive,
                        log_callback=lambda message: self.log(message, "warning"),
                    )
                mixed_language_config = None
                if self.options.use_mixed_language:
                    mixed_language_config = {
                        "use_mixed_language": True,
                        "primary": self.options.mixed_language_primary,
                        "allowed": self.options.mixed_language_allowed,
                        "confidence": self.options.mixed_language_confidence,
                    }
                return self._convert_paragraph_chapters(
                    chapters=chapters,
                    output_path=output_path,
                    work_dir=work_dir,
                    state_file=state_file,
                    state=state,
                    phoneme_dict=phoneme_dict,
                    mixed_language_config=mixed_language_config,
                )

            phoneme_dict = None
            if self.options.phoneme_dictionary_path:
                phoneme_dict = load_phoneme_dictionary(
                    self.options.phoneme_dictionary_path,
                    case_sensitive=self.options.phoneme_dict_case_sensitive,
                    log_callback=lambda message: self.log(message, "warning"),
                )

            mixed_language_config = None
            if self.options.use_mixed_language:
                mixed_language_config = {
                    "use_mixed_language": True,
                    "primary": self.options.mixed_language_primary,
                    "allowed": self.options.mixed_language_allowed,
                    "confidence": self.options.mixed_language_confidence,
                }

            total_chars = sum(ch.char_count for ch in chapters)
            # Account for already completed chapters
            chars_already_done = sum(
                state.chapters[i].char_count
                for i in range(len(state.chapters))
                if state.chapters[i].completed
            )
            chars_processed = chars_already_done
            start_time = time.time()

            progress = ConversionProgress(
                total_chapters=len(chapters),
                total_chars=total_chars,
                chars_processed=chars_processed,
            )
            # Initialize progress from saved state so the progress bar
            # starts at the completion point rather than zero.
            if state and chars_already_done > 0:
                next_position = next(
                    (
                        pos
                        for pos, ch_state in enumerate(state.chapters)
                        if not ch_state.completed
                    ),
                    len(chapters),
                )
                progress.current_chapter = min(next_position + 1, len(chapters))
                if next_position < len(chapters):
                    progress.chapter_name = chapters[next_position].title
                if self.progress_callback:
                    self.progress_callback(progress)
            aggregate_markers: list[dict[str, Any]] = []
            aggregate_issues: list[SSMDIssue] = []
            aggregate_metadata: dict[str, Any] = {}

            # Convert each chapter
            for chapter_idx, chapter in enumerate(chapters):
                if self._cancel_event.is_set():
                    state.save(state_file)
                    return ConversionResult(
                        success=False,
                        error_message="Cancelled",
                        chapters_dir=work_dir,
                    )

                # Validate chapter index to prevent index errors
                if chapter_idx >= len(state.chapters):
                    error_msg = (
                        f"Chapter index {chapter_idx} out of range. "
                        f"State has {len(state.chapters)} chapters "
                        f"but trying to access "
                        f"chapter {chapter_idx + 1}/{len(chapters)}. "
                        "This usually means the state file is corrupted. "
                        "Try using --fresh to start a new conversion."
                    )
                    return ConversionResult(
                        success=False,
                        error_message=error_msg,
                    )

                chapter_state = state.chapters[chapter_idx]

                # Check if SSMD file was manually edited
                ssmd_edited = False
                if chapter_state.ssmd_file and chapter_state.ssmd_hash:
                    ssmd_path = work_dir / chapter_state.ssmd_file
                    if ssmd_path.exists():
                        try:
                            _, current_hash = load_ssmd_file(ssmd_path)
                            if current_hash != chapter_state.ssmd_hash:
                                self.log(
                                    f"Chapter {chapter_idx + 1} SSMD file was edited, "
                                    "will regenerate audio",
                                    "info",
                                )
                                ssmd_edited = True
                                chapter_state.completed = False
                        except SSMDGenerationError:
                            # SSMD file corrupted, will regenerate
                            ssmd_edited = True
                            chapter_state.completed = False

                # Skip already completed chapters (unless SSMD was edited)
                if (
                    chapter_state.completed
                    and chapter_state.audio_file
                    and not ssmd_edited
                ):
                    chapter_file = work_dir / chapter_state.audio_file
                    if chapter_file.exists():
                        ch_num = chapter_idx + 1
                        self.log(
                            f"Skipping completed chapter {ch_num}: {chapter.title}"
                        )
                        # Rehydrate aggregate sidecars from the completed
                        # chapter so the final output has complete navigation
                        # metadata.
                        chapter_offset = sum(
                            saved.duration
                            + (
                                self.options.silence_between_chapters
                                if saved.index < chapter_state.index
                                else 0.0
                            )
                            for saved in state.chapters
                            if saved.index < chapter_state.index
                        )
                        if chapter_state.ssmd_markers_file:
                            markers_path = work_dir / chapter_state.ssmd_markers_file
                            if markers_path.is_file():
                                try:
                                    markers_data = json.loads(
                                        markers_path.read_text(encoding="utf-8")
                                    )
                                    for marker in markers_data.get("markers", []):
                                        aggregate_markers.append(
                                            {
                                                **marker,
                                                "time_s": (
                                                    marker["time_s"] + chapter_offset
                                                ),
                                            }
                                        )
                                except (json.JSONDecodeError, OSError):
                                    pass
                        if chapter_state.ssmd_diagnostics_file:
                            diag_path = work_dir / chapter_state.ssmd_diagnostics_file
                            if diag_path.is_file():
                                try:
                                    diag_data = json.loads(
                                        diag_path.read_text(encoding="utf-8")
                                    )
                                    for issue in diag_data.get("issues", []):
                                        aggregate_issues.append(
                                            SSMDIssue(
                                                code=issue.get("code", ""),
                                                severity=issue.get("severity", "warn"),
                                                message=issue.get("message", ""),
                                            )
                                        )
                                except (json.JSONDecodeError, OSError):
                                    pass
                        if chapter_state.ssmd_document_title:
                            aggregate_metadata.setdefault(
                                "title", chapter_state.ssmd_document_title
                            )
                        continue
                    else:
                        # File missing, need to reconvert
                        chapter_state.completed = False

                progress.current_chapter = chapter_idx + 1
                progress.chapter_name = chapter.title

                ch_num = chapter_idx + 1
                self.log(
                    f"Converting chapter {ch_num}/{len(chapters)}: {chapter.title}"
                )

                # Generate chapter filename using template
                chapter_filename = (
                    format_filename_template(
                        self.options.chapter_filename_template,
                        book_title=self.options.title or "Untitled",
                        chapter_title=chapter.title,
                        chapter_num=chapter_idx + 1,
                    )
                    + ".wav"
                )
                chapter_file = work_dir / chapter_filename

                # Generate SSMD filename (same as WAV but with .ssmd extension)
                ssmd_filename = chapter_filename.replace(".wav", ".ssmd")
                ssmd_file = work_dir / ssmd_filename
                ssmd_content, ssmd_hash, document_info = self._load_or_generate_ssmd(
                    chapter,
                    ssmd_file,
                    phoneme_dict=phoneme_dict,
                    mixed_language_config=mixed_language_config,
                )

                # If generate_ssmd_only mode, just generate SSMD and skip audio
                if self.options.generate_ssmd_only:
                    chapter_state.completed = True
                    chapter_state.ssmd_file = ssmd_filename
                    chapter_state.ssmd_hash = ssmd_hash
                    chapter_state.ssmd_document_title = document_info.title
                    chapter_state.ssmd_diagnostics_file = ssmd_filename.replace(
                        ".ssmd", ".diagnostics.json"
                    )
                    atomic_write_json(
                        work_dir / chapter_state.ssmd_diagnostics_file,
                        {
                            "schema_version": 1,
                            "extraction_diagnostics": list(
                                chapter.extraction_diagnostics
                            ),
                            "issues": [
                                {
                                    "code": issue.code,
                                    "severity": issue.severity,
                                    "message": issue.message,
                                    "line": issue.line,
                                    "column": issue.column,
                                }
                                for issue in document_info.issues
                            ],
                        },
                        indent=2,
                        ensure_ascii=True,
                    )
                    aggregate_issues.extend(document_info.issues)
                    if document_info.title:
                        aggregate_metadata.setdefault("title", document_info.title)
                    state.save(state_file)

                    chars_processed += chapter.char_count
                    progress.chars_processed = chars_processed
                    if self.progress_callback:
                        self.progress_callback(progress)
                    continue

                # SSMD-only conversion is backend-independent. Initialize the
                # runner only when an audio artifact is actually rendered.
                self._init_runner()
                rendered = self._render_chapter_wav(
                    chapter,
                    chapter_file,
                    ssmd_content,
                    ssmd_file,
                )

                chapter_state.ssmd_diagnostics_file = ssmd_filename.replace(
                    ".ssmd", ".diagnostics.json"
                )
                diagnostics = tuple(document_info.issues) + rendered.diagnostics
                try:
                    atomic_write_json(
                        work_dir / chapter_state.ssmd_diagnostics_file,
                        {
                            "schema_version": 1,
                            "extraction_diagnostics": list(
                                chapter.extraction_diagnostics
                            ),
                            "issues": [
                                {
                                    "code": issue.code,
                                    "severity": issue.severity,
                                    "message": issue.message,
                                    "line": issue.line,
                                    "column": issue.column,
                                }
                                for issue in diagnostics
                            ],
                        },
                        indent=2,
                        ensure_ascii=True,
                    )
                    chapter_state.ssmd_markers_file = ssmd_filename.replace(
                        ".ssmd", ".markers.json"
                    )
                    _write_marker_records_sidecar(
                        work_dir / chapter_state.ssmd_markers_file,
                        sample_rate=rendered.sample_rate,
                        markers=rendered.markers,
                    )
                    os.replace(rendered.rendered_path, chapter_file)
                except Exception:
                    rendered.rendered_path.unlink(missing_ok=True)
                    raise
                chapter_markers = rendered.markers
                chapter_offset = sum(
                    saved.duration
                    + (
                        self.options.silence_between_chapters
                        if saved.index < chapter.index
                        else 0.0
                    )
                    for saved in state.chapters
                    if saved.index < chapter.index
                )
                aggregate_markers.extend(
                    {
                        **marker,
                        "time_s": marker["time_s"] + chapter_offset,
                    }
                    for marker in chapter_markers
                )
                aggregate_issues.extend(diagnostics)
                aggregate_metadata.update(rendered.document_metadata)

                if self._cancel_event.is_set():
                    # Remove incomplete files
                    chapter_file.unlink(missing_ok=True)
                    ssmd_file.unlink(missing_ok=True)
                    state.save(state_file)
                    return ConversionResult(
                        success=False,
                        error_message="Cancelled",
                        chapters_dir=work_dir,
                    )

                # Update state
                chapter_state.completed = True
                chapter_state.audio_file = chapter_filename
                chapter_state.ssmd_file = ssmd_filename
                chapter_state.ssmd_hash = ssmd_hash
                chapter_state.ssmd_document_title = document_info.title
                chapter_state.duration = rendered.duration
                state.save(state_file)
                log_snapshot(
                    self.log,
                    "after state save",
                    provider=self.options.effective_onnx_provider(),
                )

                # Update progress
                chars_processed += chapter.char_count
                progress.chars_processed = chars_processed
                progress.current_text = (
                    f"Completed chapter: {chapter.title or 'Untitled'}"
                )
                elapsed = time.time() - start_time
                if chars_processed > chars_already_done and elapsed > 0.5:
                    chars_in_session = chars_processed - chars_already_done
                    avg_time = elapsed / chars_in_session
                    remaining = total_chars - chars_processed
                    progress.estimated_remaining = avg_time * remaining
                progress.elapsed_time = elapsed

                if self.progress_callback:
                    self.progress_callback(progress)

            # If generate_ssmd_only mode, exit here without merging
            if self.options.generate_ssmd_only:
                self.log("SSMD generation complete!")
                self.log(f"SSMD files saved in: {work_dir}")
                return ConversionResult(
                    success=True,
                    chapters_dir=work_dir,
                    output_path=None,  # No audio output in SSMD-only mode
                    short_sentence_stats=self._short_sentence_stats(),
                )

            # All chapters completed, merge into final output
            self.log("Merging chapters into final audiobook...")

            chapter_files = [
                work_dir / ch.audio_file for ch in state.chapters if ch.audio_file
            ]
            chapter_durations = [ch.duration for ch in state.chapters]
            chapter_titles = [ch.title for ch in state.chapters]

            meta = MergeMeta(
                fmt=self.options.output_format,
                silence_between_chapters=self.options.silence_between_chapters,
                title=self.options.title,
                author=self.options.author,
                cover_image=self.options.cover_image,
            )
            log_snapshot(
                self.log,
                "before final merge",
                provider=self.options.effective_onnx_provider(),
            )
            self._merger.merge_chapter_wavs(
                # The merger reads already released chapter WAV files.
                chapter_files,
                chapter_durations,
                chapter_titles,
                output_path,
                meta,
            )
            log_snapshot(
                self.log,
                "after final merge",
                provider=self.options.effective_onnx_provider(),
            )

            aggregate_marker_path = output_path.with_suffix(
                output_path.suffix + ".markers.json"
            )
            atomic_write_json(
                aggregate_marker_path,
                {
                    "schema_version": 1,
                    "sample_rate": SAMPLE_RATE,
                    "markers": aggregate_markers,
                },
                indent=2,
                ensure_ascii=True,
            )

            self.log("Conversion complete!")

            return ConversionResult(
                success=True,
                output_path=output_path,
                chapters_dir=work_dir,
                short_sentence_stats=self._short_sentence_stats(),
                document_metadata=aggregate_metadata,
                ssmd_diagnostics=tuple(aggregate_issues),
                markers=aggregate_markers,
            )

        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            return ConversionResult(success=False, error_message=error_msg)
        finally:
            prevent_sleep_end()

    def _short_sentence_stats(self) -> ShortSentenceStats:
        if self._runner is None:
            return ShortSentenceStats()
        return self._runner.get_short_sentence_stats()

    def convert_chapters(
        self,
        chapters: list[Chapter],
        output_path: Path,
    ) -> ConversionResult:
        """Convert a list of chapters to audio using the SSMD pipeline."""
        result = self.convert_chapters_resumable(
            chapters=chapters,
            output_path=output_path,
            resume=self.options.resume,
        )
        self._cleanup_chapter_dir(result)
        return result

    def _cleanup_chapter_dir(self, result: ConversionResult) -> None:
        if self.options.generate_ssmd_only:
            return
        if (
            result.success
            and result.chapters_dir
            and not self.options.keep_chapter_files
        ):
            import shutil

            try:
                shutil.rmtree(result.chapters_dir)
            except OSError as exc:
                self.log(
                    f"Failed to clean up chapter dir {result.chapters_dir}: {exc}",
                    "warning",
                )

    def convert_text(self, text: str, output_path: Path) -> ConversionResult:
        """
        Convert plain text to audio.

        Args:
            text: Text to convert
            output_path: Output file path

        Returns:
            ConversionResult
        """
        content = postprocess_extracted_text(
            text,
            self.options.text_postprocess_options,
        )
        chapters = [Chapter(title="Text", content=content, index=0)]
        return self.convert_chapters(chapters, output_path)

    def convert_epub(
        self,
        epub_path: Path,
        output_path: Path,
        selected_chapters: list[int] | None = None,
    ) -> ConversionResult:
        """
        Convert an EPUB file to audio.

        Args:
            epub_path: Path to EPUB file
            output_path: Output file path
            selected_chapters: Optional list of chapter indices to convert

        Returns:
            ConversionResult
        """
        from epub2text import EPUBParser

        self.log(f"Parsing EPUB: {epub_path}")

        # Parse EPUB using epub2text
        try:
            parser = EPUBParser(str(epub_path))
            epub_chapters = parser.get_chapters()
        except Exception as e:
            return ConversionResult(
                success=False,
                error_message=f"Failed to parse EPUB: {e}",
            )

        if not epub_chapters:
            return ConversionResult(
                success=False,
                error_message="No chapters found in EPUB",
            )

        # Filter chapters if selection provided
        if selected_chapters:
            epub_chapters = [
                ch for i, ch in enumerate(epub_chapters) if i in selected_chapters
            ]

        # Convert to our Chapter format - epub2text Chapter has .text attribute
        chapters = []
        for i, ch in enumerate(epub_chapters):
            content = postprocess_extracted_text(
                ch.text,
                self.options.text_postprocess_options,
            )
            chapters.append(Chapter(title=ch.title, content=content, index=i))

        self.log(f"Found {len(chapters)} chapters")

        # Try to get metadata from EPUB for m4b
        if self.options.output_format == "m4b":
            try:
                metadata = parser.get_metadata()
                if metadata:
                    if not self.options.title and metadata.title:
                        self.options.title = metadata.title
                    if not self.options.author and metadata.authors:
                        self.options.author = metadata.authors[0]
            except (AttributeError, OSError, ValueError) as exc:
                self.log(f"Failed to read EPUB metadata: {exc}", "warning")

        result = self.convert_chapters_resumable(
            chapters,
            output_path,
            source_file=epub_path,
            resume=self.options.resume,
        )
        self._cleanup_chapter_dir(result)
        return result


def parse_text_chapters(text: str) -> list[Chapter]:
    """
    Parse text content into chapters based on chapter markers.

    Args:
        text: Text content

    Returns:
        List of Chapter objects
    """
    matches = list(CHAPTER_PATTERN.finditer(text))

    if not matches:
        return [Chapter(title="Text", content=text.strip(), index=0)]

    chapters = []

    # Add introduction if content before first marker
    first_start = matches[0].start()
    if first_start > 0:
        intro_text = text[:first_start].strip()
        if intro_text:
            chapters.append(Chapter(title="Introduction", content=intro_text, index=0))

    # Parse chapters
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)

        chapter_name = match.group().strip()
        chapter_text = text[start:end].strip()

        if chapter_text:
            chapters.append(
                Chapter(title=chapter_name, content=chapter_text, index=len(chapters))
            )

    return chapters
