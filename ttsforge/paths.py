"""Provider-independent user paths used by the CLI and configuration code."""

from __future__ import annotations

import platform
from pathlib import Path

from platformdirs import user_config_dir

ADVANCED_CONFIG_FILENAME = "short_sentence_advanced.json"


def get_user_config_path() -> Path:
    """Return the path to the user's ttsforge configuration file."""
    if platform.system() != "Windows":
        custom_dir = Path.home() / ".config" / "ttsforge"
        if custom_dir.exists():
            config_dir = custom_dir
        else:
            config_dir = Path(
                user_config_dir(
                    "ttsforge", appauthor=False, roaming=True, ensure_exists=True
                )
            )
    else:
        config_dir = Path(
            user_config_dir(
                "ttsforge", appauthor=False, roaming=True, ensure_exists=True
            )
        )
    return config_dir / "config.json"


def get_advanced_short_sentence_config_path() -> Path:
    """Return the path to the advanced short-sentence JSON configuration."""
    from . import utils

    return utils.get_user_config_path().with_name(ADVANCED_CONFIG_FILENAME)
