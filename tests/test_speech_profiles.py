from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ttsforge.cli.speech_profiles import (
    discover_speech_replacement_profiles,
    is_speech_replacement_profile,
)


def _write_profile(
    path: Path,
    *,
    schema: str = "ssmdconvert-speech-profile",
    version: int = 1,
) -> Path:
    path.write_text(f'schema = "{schema}"\nversion = {version}\n', encoding="utf-8")
    return path


def test_is_speech_replacement_profile_checks_schema_and_case_insensitive_suffix(
    tmp_path: Path,
) -> None:
    profile = _write_profile(tmp_path / "profile.TOML")

    assert is_speech_replacement_profile(profile)


def test_discover_speech_profiles_finds_matching_schema(tmp_path: Path) -> None:
    profile = _write_profile(tmp_path / "speech-replacements.toml")

    assert discover_speech_replacement_profiles(tmp_path) == (profile,)


def test_discover_speech_profiles_ignores_unrelated_toml(tmp_path: Path) -> None:
    unrelated = _write_profile(tmp_path / "settings.toml", schema="something-else")

    assert discover_speech_replacement_profiles(tmp_path) == ()
    assert unrelated.exists()


def test_discover_speech_profiles_ignores_malformed_toml(tmp_path: Path) -> None:
    (tmp_path / "broken.toml").write_text('schema = "unterminated', encoding="utf-8")

    assert discover_speech_replacement_profiles(tmp_path) == ()


def test_discover_speech_profiles_is_non_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "profiles"
    nested.mkdir()
    _write_profile(nested / "speech-replacements.toml")

    assert discover_speech_replacement_profiles(tmp_path) == ()


def test_discover_speech_profiles_sorts_case_insensitively_with_stable_ties(
    tmp_path: Path, monkeypatch
) -> None:
    names = ("zeta.toml", "beta.TOML", "alpha.toml", "Alpha.toml")
    entries = tuple(tmp_path / name for name in names)
    original_iterdir = Path.iterdir

    def iterdir(path: Path) -> Iterator[Path]:
        if path == tmp_path:
            return iter(entries)
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    monkeypatch.setattr(
        "ttsforge.cli.speech_profiles.is_speech_replacement_profile", lambda _: True
    )

    assert discover_speech_replacement_profiles(tmp_path) == (
        entries[3],
        entries[2],
        entries[1],
        entries[0],
    )


def test_discover_speech_profiles_does_not_require_version_one(tmp_path: Path) -> None:
    profile = _write_profile(tmp_path / "future.toml", version=7)

    assert discover_speech_replacement_profiles(tmp_path) == (profile,)


def test_discover_speech_profiles_skips_unreadable_profile(
    tmp_path: Path, monkeypatch
) -> None:
    unreadable = _write_profile(tmp_path / "unreadable.toml")
    readable = _write_profile(tmp_path / "readable.toml")
    original_open = Path.open

    def open_profile(path: Path, *args: object, **kwargs: object):
        if path == unreadable:
            raise PermissionError("profile cannot be read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_profile)

    assert discover_speech_replacement_profiles(tmp_path) == (readable,)


def test_discover_speech_profiles_returns_empty_when_directory_cannot_be_listed(
    tmp_path: Path,
) -> None:
    assert discover_speech_replacement_profiles(tmp_path / "missing") == ()
