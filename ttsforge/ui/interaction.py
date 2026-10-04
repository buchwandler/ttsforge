"""Compatibility alias for terminal interaction policy."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("ttsforge.cli.interaction")
