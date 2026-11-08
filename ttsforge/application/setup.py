"""Deterministic setup merging and dependent-choice invalidation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .errors import SetupConflictError
from .models import AudiobookRequest, InputOverrides, SetupOrigins

_SETUP_FIELDS = (
    "chapters",
    "output",
    "language",
    "engine",
    "target",
    "voice",
    "engine_options",
    "speed",
    "bitrate",
    "target_lufs",
    "title",
    "author",
    "cover",
)

_DEPENDENT_FIELDS = {
    "language": ("engine", "target", "voice", "engine_options", "speed"),
    "engine": ("target", "voice", "engine_options", "speed"),
    "target": ("voice", "engine_options", "speed"),
}

_RESET_VALUES: dict[str, object] = {
    "engine": None,
    "target": None,
    "voice": None,
    "engine_options": {},
    "speed": None,
}


def _has_saved_value(request: AudiobookRequest, field_name: str) -> bool:
    value = getattr(request, field_name)
    if field_name == "engine_options":
        return bool(value)
    return value is not None


def invalidate_dependency_sources(
    origins: SetupOrigins, changed_field: str
) -> SetupOrigins:
    invalidated = frozenset(_DEPENDENT_FIELDS.get(changed_field, ()))
    return replace(origins, project=origins.project - invalidated)


def reset_dependency_choices(
    request: AudiobookRequest,
    changed_field: str,
    overrides: InputOverrides,
) -> AudiobookRequest:
    updates: dict[str, Any] = {
        field_name: value
        for field_name, value in _RESET_VALUES.items()
        if field_name in _DEPENDENT_FIELDS.get(changed_field, ())
        and not overrides.includes(field_name)
    }
    return replace(request, **updates)


def merge_saved_setup(
    request: AudiobookRequest,
    saved: AudiobookRequest,
    overrides: InputOverrides,
    *,
    interactive: bool = True,
) -> AudiobookRequest:
    """Apply explicit values over persisted setup, preserving derived defaults."""
    updates = {
        field_name: getattr(saved, field_name)
        for field_name in _SETUP_FIELDS
        if not overrides.includes(field_name) and _has_saved_value(saved, field_name)
    }
    merged = replace(request, **updates)
    if overrides.includes("engine_options"):
        selectors_changed = any(
            overrides.includes(name) and getattr(request, name) != getattr(saved, name)
            for name in ("language", "engine", "target")
        )
        options = {} if selectors_changed else dict(saved.engine_options)
        options.update(request.engine_options)
        merged = replace(merged, engine_options=options)

    for changed_field in ("language", "engine", "target"):
        if not overrides.includes(changed_field):
            continue
        if getattr(request, changed_field) == getattr(saved, changed_field):
            continue
        dependent = tuple(
            field_name
            for field_name in _DEPENDENT_FIELDS[changed_field]
            if not overrides.includes(field_name)
            and _has_saved_value(saved, field_name)
        )
        if dependent and not interactive:
            flags = ", ".join(f"--{name.replace('_', '-')}" for name in dependent)
            raise SetupConflictError(
                f"Changing --{changed_field.replace('_', '-')} conflicts with saved "
                f"project choices {flags}. Run interactively or pass compatible values."
            )
        merged = reset_dependency_choices(merged, changed_field, overrides)

    return merged
