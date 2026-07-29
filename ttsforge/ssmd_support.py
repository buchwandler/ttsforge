"""Stable ttsforge integration boundary for SSMD 0.8 documents.

The SSMD and pykokoro packages own parsing and rendering semantics.  This
module only translates their public APIs into ttsforge's stable policy and
diagnostic types so callers do not need to depend on backend dataclasses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

IssueSeverity = Literal["info", "warn", "error"]
UnknownHeaderPolicy = Literal["warn", "error", "ignore"]
MissingVoicePolicy = Literal["error", "use-default"]
EmphasisMode = Literal["approximate", "warn", "error"]


@dataclass(frozen=True, slots=True)
class SSMDIssue:
    """A normalized SSMD diagnostic suitable for logs and result objects."""

    code: str
    severity: IssueSeverity
    message: str
    line: int | None = None
    column: int | None = None

    def format(self, source: Path | None = None) -> str:
        location = ""
        if source is not None:
            location += str(source)
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        elif source is None:
            location = "SSMD"
        prefix = f"{location} " if location else ""
        return f"{prefix}[{self.code}] {self.message}"


@dataclass(frozen=True, slots=True)
class SSMDPauseOverrideOptions:
    """Explicit pause values supplied by an API or CLI caller.

    ``None`` means that the caller did not provide an override.  This
    distinction is important: persistent ttsforge configuration is a lower
    precedence pipeline default and must not mask a document header.
    """

    enabled: bool | None = None
    sentence: str | None = None
    paragraph: str | None = None
    voice_change: str | None = None


@dataclass(frozen=True, slots=True)
class SSMDPolicy:
    """ttsforge-owned SSMD rendering and validation policy."""

    parse_header: bool = True
    unknown_header: UnknownHeaderPolicy = "warn"
    missing_voice: MissingVoicePolicy = "error"
    validate_profile: bool = True
    emphasis_mode: EmphasisMode = "approximate"
    fail_on_warning: bool = False
    voice_bindings: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    pause_overrides: SSMDPauseOverrideOptions | None = None
    audio_root: Path | None = None
    allow_remote_audio: bool = False
    audio_timeout_s: float = 10.0
    audio_max_bytes: int = 20_000_000
    audio_max_duration_s: float = 120.0

    def __post_init__(self) -> None:
        if not isinstance(self.parse_header, bool):
            raise TypeError("parse_header must be a boolean")
        if self.unknown_header not in {"warn", "error", "ignore"}:
            raise ValueError("unknown_header must be 'warn', 'error', or 'ignore'")
        if self.missing_voice not in {"error", "use-default"}:
            raise ValueError("missing_voice must be 'error' or 'use-default'")
        if self.emphasis_mode not in {"approximate", "warn", "error"}:
            raise ValueError("emphasis_mode must be 'approximate', 'warn', or 'error'")
        if (
            isinstance(self.audio_max_bytes, bool)
            or not isinstance(self.audio_max_bytes, int)
            or self.audio_max_bytes <= 0
        ):
            raise ValueError("audio_max_bytes must be a positive integer")
        if (
            isinstance(self.audio_max_duration_s, bool)
            or not isinstance(self.audio_max_duration_s, (int, float))
            or self.audio_max_duration_s < 0
        ):
            raise ValueError("audio_max_duration_s must be non-negative")
        if not isinstance(self.allow_remote_audio, bool):
            raise TypeError("allow_remote_audio must be a boolean")
        if (
            isinstance(self.audio_timeout_s, bool)
            or not isinstance(self.audio_timeout_s, (int, float))
            or self.audio_timeout_s <= 0
        ):
            raise ValueError("audio_timeout_s must be positive")
        _validate_bindings(self.voice_bindings)
        if self.pause_overrides is not None and not isinstance(
            self.pause_overrides, SSMDPauseOverrideOptions
        ):
            raise TypeError("pause_overrides must be SSMDPauseOverrideOptions or None")


@dataclass(frozen=True, slots=True)
class SSMDDocumentInfo:
    """Parsed document metadata and all diagnostics discovered during inspection."""

    source: str
    body: str
    header: dict[str, Any]
    issues: tuple[SSMDIssue, ...]
    title: str | None

    @property
    def errors(self) -> tuple[SSMDIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[SSMDIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warn")


class SSMDValidationError(ValueError):
    """Raised after SSMD validation collected all available diagnostics."""

    def __init__(
        self,
        issues: Sequence[SSMDIssue],
        source: Path | None = None,
    ) -> None:
        self.issues = tuple(issues)
        self.source = source
        details = "\n".join(issue.format(source) for issue in self.issues)
        super().__init__(details or "SSMD validation failed")


def _validate_bindings(bindings: Mapping[str, Mapping[str, str]]) -> None:
    if not isinstance(bindings, Mapping):
        raise TypeError("voice_bindings must be a mapping")
    for provider, provider_bindings in bindings.items():
        if not isinstance(provider, str) or not provider:
            raise ValueError("voice binding providers must be non-empty strings")
        if not isinstance(provider_bindings, Mapping):
            raise TypeError(f"voice_bindings.{provider} must be a mapping")
        for reference, target in provider_bindings.items():
            if not isinstance(reference, str) or not reference:
                raise ValueError("voice binding references must be non-empty strings")
            if not isinstance(target, str) or not target:
                raise ValueError("voice binding targets must be non-empty strings")


def _line_column(text: str, offset: int | None) -> tuple[int | None, int | None]:
    if offset is None:
        return None, None
    bounded = max(0, min(offset, len(text)))
    line = text.count("\n", 0, bounded) + 1
    line_start = text.rfind("\n", 0, bounded) + 1
    return line, bounded - line_start + 1


def _normalize_issue(
    text: str,
    *,
    code: str,
    severity: str,
    message: str,
    line: int | None = None,
    column: int | None = None,
    offset: int | None = None,
) -> SSMDIssue:
    if severity not in {"info", "warn", "error"}:
        severity = "error"
    if line is None and offset is not None:
        line, column = _line_column(text, offset)
    return SSMDIssue(code, severity, message, line, column)  # type: ignore[arg-type]


def _deduplicate(issues: Sequence[SSMDIssue]) -> tuple[SSMDIssue, ...]:
    result: list[SSMDIssue] = []
    seen: set[tuple[str, str, int | None, int | None, str]] = set()
    for issue in issues:
        key = (issue.code, issue.severity, issue.line, issue.column, issue.message)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def _header_and_body(
    text: str, policy: SSMDPolicy
) -> tuple[dict[str, Any], str, list[SSMDIssue]]:
    if not policy.parse_header:
        return {}, text, []

    from ssmd import parse_front_matter
    from ssmd.frontmatter import FrontMatterError, validate_front_matter

    try:
        front_matter = parse_front_matter(text)
    except FrontMatterError as exc:
        return (
            {},
            text,
            [
                _normalize_issue(
                    text,
                    code=getattr(exc, "code", "header.yaml_invalid"),
                    severity="error",
                    message=str(exc),
                    line=getattr(exc, "line", None),
                    column=getattr(exc, "column", None),
                )
            ],
        )

    if not front_matter.present:
        return {}, text, []

    issues: list[SSMDIssue] = []
    for issue in validate_front_matter(front_matter.data):
        severity = issue.severity
        if issue.code == "header.unknown_key":
            if policy.unknown_header == "ignore":
                continue
            if policy.unknown_header == "error":
                severity = "error"
        issues.append(
            _normalize_issue(
                text,
                code=issue.code,
                severity=severity,
                message=issue.message,
                line=issue.line,
                column=issue.column,
            )
        )
    return dict(front_matter.data), front_matter.body, issues


def build_pykokoro_ssmd_config(
    policy: SSMDPolicy,
    *,
    audio_resolver: object | None = None,
) -> Any:
    """Translate a ttsforge policy at the pykokoro boundary."""

    from pykokoro import SSMDPauseOverrides, SSMDRenderConfig

    pause = policy.pause_overrides
    pause_defaults = (
        SSMDPauseOverrides(
            enabled=pause.enabled,
            sentence=pause.sentence,
            paragraph=pause.paragraph,
            voice_change=pause.voice_change,
        )
        if pause is not None
        else None
    )
    return SSMDRenderConfig(
        parse_header=policy.parse_header,
        provider="kokoro",
        voice_bindings=dict(policy.voice_bindings),
        pause_defaults=pause_defaults,
        strict_header=True,
        unknown_header=policy.unknown_header,
        missing_voice=policy.missing_voice,
        validate_profile=policy.validate_profile,
        emphasis_mode=policy.emphasis_mode,
        audio_source_resolver=audio_resolver,
        audio_max_bytes=policy.audio_max_bytes,
        audio_max_duration_s=policy.audio_max_duration_s,
    )


def inspect_ssmd_document(
    text: str,
    *,
    policy: SSMDPolicy | None = None,
    audio_resolver: object | None = None,
) -> SSMDDocumentInfo:
    """Inspect SSMD core and Kokoro-profile behavior without initializing ONNX.

    Inspection returns all diagnostics it can collect.  Call
    :func:`validate_ssmd_document` when the caller wants errors (or warnings in
    strict mode) promoted to :class:`SSMDValidationError`.
    """

    if not isinstance(text, str):
        raise TypeError("SSMD source must be a string")
    effective_policy = policy or SSMDPolicy()
    header, body, issues = _header_and_body(text, effective_policy)

    from ssmd import lint

    try:
        lint_issues = lint(
            text,
            profile="ssmd-core",
            parse_yaml_header=effective_policy.parse_header,
        )
    except Exception as exc:
        issues.append(
            _normalize_issue(
                text,
                code=getattr(exc, "code", "ssmd.lint_failed"),
                severity="error",
                message=str(exc),
                line=getattr(exc, "line", None),
                column=getattr(exc, "column", None),
            )
        )
        lint_issues = []

    for issue in lint_issues:
        issues.append(
            _normalize_issue(
                text,
                code=getattr(issue, "code", "diagnostic"),
                severity=getattr(issue, "severity", "error"),
                message=getattr(issue, "message", str(issue)),
                line=getattr(issue, "line", None),
                column=getattr(issue, "column", None),
                offset=getattr(issue, "char_start", None),
            )
        )

    try:
        from pykokoro.ssmd_parser import parse_ssmd_document

        parsed = parse_ssmd_document(
            text,
            render_config=build_pykokoro_ssmd_config(
                effective_policy, audio_resolver=audio_resolver
            ),
        )
    except Exception as exc:
        issues.append(
            _normalize_issue(
                text,
                code=getattr(exc, "code", "ssmd.profile_invalid"),
                severity="error",
                message=str(exc),
                line=getattr(exc, "line", None),
                column=getattr(exc, "column", None),
            )
        )
    else:
        for diagnostic in getattr(parsed, "diagnostics", ()):
            issues.append(
                _normalize_issue(
                    text,
                    code=getattr(diagnostic, "code", "ssmd.diagnostic"),
                    severity=getattr(diagnostic, "severity", "warn"),
                    message=getattr(diagnostic, "message", str(diagnostic)),
                    line=getattr(diagnostic, "line", None),
                    column=getattr(diagnostic, "column", None),
                )
            )

    return SSMDDocumentInfo(
        source=text,
        body=body,
        header=header,
        issues=_deduplicate(issues),
        title=header.get("title") if isinstance(header.get("title"), str) else None,
    )


def validate_ssmd_document(
    text: str,
    *,
    policy: SSMDPolicy | None = None,
    source: Path | None = None,
    audio_resolver: object | None = None,
) -> SSMDDocumentInfo:
    """Inspect and enforce the configured SSMD error/warning policy."""

    effective_policy = policy or SSMDPolicy()
    info = inspect_ssmd_document(
        text, policy=effective_policy, audio_resolver=audio_resolver
    )
    blocking = list(info.errors)
    if effective_policy.fail_on_warning:
        blocking.extend(info.warnings)
    if blocking:
        raise SSMDValidationError(blocking, source)
    return info


def format_issue(issue: SSMDIssue, source: Path | None = None) -> str:
    """Format one issue for CLI and compatibility APIs."""

    return issue.format(source)


__all__ = [
    "SSMDDocumentInfo",
    "SSMDIssue",
    "SSMDPauseOverrideOptions",
    "SSMDPolicy",
    "SSMDValidationError",
    "build_pykokoro_ssmd_config",
    "format_issue",
    "inspect_ssmd_document",
    "validate_ssmd_document",
]
