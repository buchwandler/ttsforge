"""Compatibility alias for terminal progress renderers."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("ttsforge.cli.progress")
