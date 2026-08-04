"""Shared spaCy model policy and public resolver adapter.

TTSForge deliberately delegates installed-model discovery to :mod:`phrasplit`.
This module owns only request normalization, capability checks, stable policy
identity, and diagnostics needed by TTSForge's three spaCy integrations.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from phrasplit import SpacyModelSize, resolve_spacy_model

logger = logging.getLogger(__name__)

SPACY_POLICY_VERSION = "highest-installed-v1"
SPACY_MODEL_SIZES: tuple[SpacyModelSize, ...] = ("sm", "md", "lg", "trf")
SpacyComponent = Literal["sentence", "g2p", "name"]


class SpacyPolicyError(RuntimeError):
    """Base error for TTSForge spaCy policy failures."""


class SpacyCapabilityError(SpacyPolicyError):
    """Raised when a selected model cannot perform the requested operation."""


@dataclass(frozen=True, slots=True)
class SpacyModelRequest:
    """Normalized, availability-independent spaCy selection request."""

    use_spacy: bool | None = None
    model: str | None = None
    size: SpacyModelSize | None = None

    def __post_init__(self) -> None:
        model = normalize_spacy_model(self.model)
        size = normalize_spacy_model_size(self.size)
        if self.use_spacy is False:
            model = None
            size = None
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "size", size)

    @property
    def is_automatic(self) -> bool:
        return self.use_spacy is None and self.model is None and self.size is None

    @property
    def strict(self) -> bool:
        """Whether this request must resolve a loadable concrete model."""
        return self.use_spacy is True or self.model is not None or self.size is not None

    @property
    def disabled(self) -> bool:
        """Whether this request explicitly disables spaCy."""
        return self.use_spacy is False

    def as_dict(self) -> dict[str, Any]:
        return {
            "use_spacy": self.use_spacy,
            "model": self.model,
            "size": self.size,
        }


@dataclass(frozen=True, slots=True)
class ResolvedSpacyModel:
    """Concrete model selection and provenance for one language/component."""

    language: str
    model: str | None
    requested_model: str | None
    requested_size: SpacyModelSize | None
    component: SpacyComponent
    policy: str = SPACY_POLICY_VERSION
    available: bool = True
    diagnostics: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "model": self.model,
            "requested_model": self.requested_model,
            "requested_size": self.requested_size,
            "component": self.component,
            "policy": self.policy,
            "available": self.available,
            "diagnostics": list(self.diagnostics),
        }


def normalize_spacy_model(model: str | None) -> str | None:
    """Normalize empty and ``auto`` model values to automatic selection."""
    if model is None:
        return None
    normalized = model.strip()
    if not normalized or normalized.lower() == "auto":
        return None
    return normalized


def normalize_spacy_model_size(
    size: SpacyModelSize | str | None,
) -> SpacyModelSize | None:
    """Normalize and validate an exact spaCy tier without model discovery."""
    if size is None:
        return None
    normalized = str(size).strip().lower()
    if not normalized or normalized == "auto":
        return None
    if normalized not in SPACY_MODEL_SIZES:
        raise ValueError(
            "spaCy model size must be one of: " + ", ".join(SPACY_MODEL_SIZES)
        )
    return normalized  # type: ignore[return-value]


def normalize_language(language: str | None) -> str:
    """Normalize a language for phrasplit and diagnostic map keys."""
    value = (language or "en").strip().lower().replace("_", "-")
    # TTSForge's single-letter voice/language codes are converted before they
    # reach phrasplit, whose resolver requires ISO-like spaCy language codes.
    value = {
        "a": "en-us",
        "b": "en-gb",
        "d": "de",
        "e": "es",
        "f": "fr",
        "h": "hi",
        "i": "it",
        "j": "ja",
        "p": "pt",
        "z": "zh",
    }.get(value, value)
    return value or "en"


def _has_capability(nlp: Any, capability: str) -> bool:
    # Lightweight test doubles and provider facades may intentionally omit
    # spaCy's ``pipe_names``. Real spaCy Language objects always expose it;
    # leave capability validation to those concrete objects.
    if not hasattr(nlp, "pipe_names"):
        return True
    pipe_names = set(getattr(nlp, "pipe_names", ()))
    if capability == "ner":
        return "ner" in pipe_names
    if capability == "pos":
        return bool(pipe_names.intersection({"tagger", "morphologizer"}))
    return capability in pipe_names


@functools.lru_cache(maxsize=64)
def _load_model(model: str) -> Any:
    """Load a concrete package once; the cache key is the package identity."""
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - exercised via integration
        raise SpacyPolicyError(
            "spaCy is required for this operation. Install spaCy and a compatible "
            "local model."
        ) from exc
    try:
        return spacy.load(model)
    except OSError as exc:
        raise SpacyPolicyError(
            f"spaCy model '{model}' is unavailable or cannot be loaded. "
            f"Install that exact package locally; TTSForge never downloads models."
        ) from exc


def load_resolved_model(selection: ResolvedSpacyModel) -> Any:
    """Load a resolved concrete package, or fail clearly for disabled/fallback mode."""
    if selection.model is None:
        raise SpacyPolicyError(
            "No compatible spaCy model is available for language "
            f"'{selection.language}'."
        )
    return _load_model(selection.model)


def ensure_model_loadable(model: str) -> None:
    """Verify a stored concrete package remains installed and loadable."""
    _load_model(model)


def _required_capabilities(
    component: SpacyComponent,
    *,
    include_all: bool,
) -> tuple[str, ...]:
    if component == "name":
        return ("ner", "pos") if include_all else ("ner",)
    return ()


def _candidate_models(language: str, request: SpacyModelRequest) -> tuple[str, ...]:
    """Get candidate identities from phrasplit, without reimplementing discovery."""
    resolution = resolve_spacy_model(
        language=language,
        model=request.model,
        size=request.size,
        require=False,
    )
    candidates = tuple(getattr(resolution, "candidates", ()))
    if request.model:
        return (request.model,)
    return candidates


def resolve_spacy_model_for_component(
    *,
    language: str | None,
    request: SpacyModelRequest,
    component: SpacyComponent,
    include_all: bool = False,
    require: bool | None = None,
) -> ResolvedSpacyModel:
    """Resolve a loadable model with the capabilities required by a component.

    Candidate discovery and tier ranking remain phrasplit's responsibility.
    TTSForge only asks phrasplit for candidates, loads them through spaCy, and
    filters for the component's public capability contract.
    """
    normalized_language = normalize_language(language)
    if request.disabled:
        return ResolvedSpacyModel(
            language=normalized_language,
            model=None,
            requested_model=request.model,
            requested_size=request.size,
            component=component,
            available=False,
            diagnostics=("spaCy disabled by request",),
        )

    capabilities = _required_capabilities(component, include_all=include_all)
    # Explicit model/tier requests and ``use_spacy=True`` are always strict.
    # Automatic ``None`` requests may fall back unless the caller explicitly
    # asks for a required model.
    must_require = request.strict or bool(require)
    candidates = _candidate_models(normalized_language, request)
    attempts: list[str] = []
    for candidate in candidates:
        try:
            nlp = _load_model(candidate)
        except SpacyPolicyError as exc:
            attempts.append(str(exc))
            if request.model:
                raise
            continue
        missing = [
            capability
            for capability in capabilities
            if not _has_capability(nlp, capability)
        ]
        if missing:
            attempts.append(f"{candidate}: missing {', '.join(missing)}")
            if request.model:
                raise SpacyCapabilityError(
                    f"spaCy model '{candidate}' lacks required {', '.join(missing)} "
                    f"capability for {component} extraction."
                )
            continue
        selection = "explicit model" if request.model else (
            f"exact {request.size} tier" if request.size else "highest installed"
        )
        return ResolvedSpacyModel(
            language=normalized_language,
            model=candidate,
            requested_model=request.model,
            requested_size=request.size,
            component=component,
            diagnostics=(f"selected {selection} model '{candidate}'",),
        )

    if must_require:
        detail = f" Tried: {'; '.join(attempts)}" if attempts else ""
        raise SpacyPolicyError(
            f"No compatible loadable spaCy model is installed for language "
            f"'{normalized_language}' and component '{component}'.{detail}"
        )
    return ResolvedSpacyModel(
        language=normalized_language,
        model=None,
        requested_model=request.model,
        requested_size=request.size,
        component=component,
        available=False,
        diagnostics=(
            f"no compatible model found for '{normalized_language}'/{component}",
        ),
    )


def report_selection(
    selection: ResolvedSpacyModel,
    *,
    log: Callable[[str, str], None] | None = None,
) -> None:
    """Report one selection; callers can provide a run-local deduping logger."""
    if selection.model:
        message = (
            f"Using spaCy model {selection.model} for {selection.language} "
            f"{selection.component}"
        )
        if log:
            log(message, "info")
        else:
            logger.info(message)
    elif log:
        log(
            f"No compatible spaCy model found for {selection.language} "
            f"{selection.component}; quality may be reduced by fallback.",
            "warning",
        )


def clear_model_cache() -> None:
    """Clear test/runtime model cache after an environment change."""
    _load_model.cache_clear()
