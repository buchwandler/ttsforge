"""Strict JSON conversion for frontend-neutral application DTOs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


def json_value(value: object) -> JsonValue:
    """Convert supported application DTO values to JSON-compatible values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("Non-finite floats are not valid JSON values.")
        return value
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: json_value(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings.")
            result[key] = json_value(item)
        return result
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}.")
