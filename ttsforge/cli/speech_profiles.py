"""Compatibility exports for shared application speech-profile discovery."""

from ..application.speech_profiles import (
    SPEECH_PROFILE_SCHEMA,
    discover_speech_replacement_profiles,
    is_speech_replacement_profile,
)

__all__ = [
    "SPEECH_PROFILE_SCHEMA",
    "discover_speech_replacement_profiles",
    "is_speech_replacement_profile",
]
