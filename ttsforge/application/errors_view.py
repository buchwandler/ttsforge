"""Frontend-neutral structured error views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import ApplicationError
from .serialization import JsonValue, json_value


@dataclass(frozen=True, slots=True)
class ErrorView:
    type: str
    message: str
    category: str | None = None
    code: str | None = None
    stage: str | None = None
    package: str | None = None
    selector: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible structured error payload."""
        return json_value(self)  # type: ignore[return-value]


def error_view(error: Exception) -> ErrorView:
    """Normalize application failures without exposing unexpected internals."""
    expected = isinstance(error, ApplicationError)
    details = getattr(error, "details", {}) if expected else {}
    if not isinstance(details, Mapping):
        details = {}
    return ErrorView(
        type=type(error).__name__,
        message=str(error) if expected else "An unexpected error occurred.",
        category=_optional_string(getattr(error, "category", None)),
        code=_optional_string(getattr(error, "code", None)),
        stage=_optional_string(getattr(error, "stage", None)),
        package=_optional_string(getattr(error, "package", None)),
        selector=_optional_string(getattr(error, "selector", None)),
        details=dict(details),
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
