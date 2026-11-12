from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

SPEECH_PROFILE_SCHEMA = "ssmdconvert-speech-profile"


def is_speech_replacement_profile(path: Path) -> bool:
    if path.suffix.casefold() != ".toml":
        return False

    try:
        if not path.is_file():
            return False
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return False

    schema = payload.get("schema")
    return isinstance(schema, str) and schema == SPEECH_PROFILE_SCHEMA


def discover_speech_replacement_profiles(directory: Path) -> tuple[Path, ...]:
    try:
        entries = tuple(directory.iterdir())
    except OSError:
        return ()

    candidates = [path for path in entries if is_speech_replacement_profile(path)]
    return tuple(sorted(candidates, key=lambda path: (path.name.casefold(), path.name)))
