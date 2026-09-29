"""Compact human rendering for catalog choices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from readio.api import EngineInfo, LexiconInfo, ModelInfo, VoiceInfo
from rich.console import Console
from rich.text import Text


@dataclass(frozen=True, slots=True)
class CatalogListItem:
    primary: str
    tags: tuple[str, ...] = ()
    details: tuple[str, ...] = ()


def _status_tags(
    *,
    status: str,
    experimental: bool,
    runtime_available: bool,
) -> tuple[str, ...]:
    tags = []
    if experimental:
        tags.append("experimental")
    if not runtime_available:
        tags.append("runtime unavailable")
    elif status and status != "ready":
        tags.append(status)
    return tuple(tags)


def _engine_features(engine: EngineInfo) -> str:
    capabilities = engine.capabilities
    if capabilities is None:
        return ""
    features = []
    if capabilities.supports_named_voices:
        features.append("voices")
    if capabilities.supports_lexicons:
        features.append("lexicons")
    if capabilities.supports_model_sources:
        features.append("model sources")
    if capabilities.supports_qualities:
        features.append("qualities")
    if capabilities.supports_voice_level_calibration:
        features.append("voice level")
    return " · ".join(features)


def engine_item(engine: EngineInfo, *, show_status: bool = False) -> CatalogListItem:
    primary = engine.id
    if engine.version:
        primary += f"  {engine.version}"
    tags = []
    details = []
    features = _engine_features(engine)
    if features:
        details.append(features)
    if show_status:
        if not engine.runnable:
            tags.append("not runnable")
        if not engine.installed:
            tags.append("not installed")
        if engine.missing_dependency:
            details.append(f"missing dependency: {engine.missing_dependency}")
    return CatalogListItem(primary, tuple(tags), tuple(details))


def model_item(model: ModelInfo, *, engine: str | None = None) -> CatalogListItem:
    details = []
    if engine is None:
        details.append(f"engine: {model.backend}")
    elif model.backend != engine:
        details.append(f"backend: {model.backend}")
    if model.source:
        details.append(f"source: {model.source}")
    if model.qualities:
        label = "quality" if len(model.qualities) == 1 else "qualities"
        details.append(f"{label}: {', '.join(model.qualities)}")
    if model.default_voice:
        details.append(f"default voice: {model.default_voice}")
    if model.g2p_backend:
        details.append(f"G2P: {model.g2p_backend}")
    if model.lexicons:
        details.append(f"lexicons: {', '.join(model.lexicons)}")
    tags = _status_tags(
        status=model.status,
        experimental=model.experimental,
        runtime_available=model.runtime_available,
    )
    return CatalogListItem(model.id, tags, tuple(details))


def voice_item(
    voice: VoiceInfo,
    *,
    engine: str | None = None,
    model: str | None = None,
) -> CatalogListItem:
    tags = list(
        _status_tags(
            status=voice.status,
            experimental=voice.experimental,
            runtime_available=voice.runtime_available,
        )
    )
    if voice.default:
        tags.insert(0, "model default")
    details = []
    identity = " · ".join(
        part for part in (voice.gender or "", voice.locale or "") if part
    )
    if identity:
        details.append(identity)
    if engine is None:
        details.append(f"engine: {voice.engine}")
    elif voice.engine != engine:
        details.append(f"engine: {voice.engine}")
    if voice.model and model is None:
        details.append(f"model: {voice.model}")
    elif model and voice.model != model and voice.model:
        details.append(f"model: {voice.model}")
    if voice.selector:
        details.append(f"selector: {voice.selector}")
    else:
        details.append(f"qualified ID: {voice.qualified_id}")
    return CatalogListItem(voice.id, tuple(tags), tuple(details))


def lexicon_item(lexicon: LexiconInfo) -> CatalogListItem:
    tags = ["installed" if lexicon.installed else "not installed"]
    if lexicon.default:
        tags.append("default")
    details = []
    if lexicon.display_name and lexicon.display_name != lexicon.selector:
        details.append(f"selector: {lexicon.selector}")
    if lexicon.data_backend:
        details.append(f"backend: {lexicon.data_backend}")
    if lexicon.models:
        details.append(f"models: {', '.join(lexicon.models)}")
    if lexicon.model_support:
        details.append(f"model support: {lexicon.model_support}")
    if lexicon.phoneme_encoding:
        details.append(f"encoding: {lexicon.phoneme_encoding}")
    if lexicon.data_version:
        details.append(f"version: {lexicon.data_version}")
    return CatalogListItem(
        lexicon.display_name or lexicon.selector,
        tuple(tags),
        tuple(details),
    )


def render_catalog_list(
    console: Console,
    *,
    title: str,
    items: Sequence[CatalogListItem],
) -> None:
    console.print(Text(f"{title} ({len(items)})", style="bold"))
    if not items:
        return

    for index, item in enumerate(items, 1):
        line = Text(f"  {index}. ")
        line.append(item.primary, style="bold")
        for tag in item.tags:
            line.append(f"  [{tag}]", style="dim")
        console.print(line)
        for detail in item.details:
            console.print(Text(f"     {detail}"))
