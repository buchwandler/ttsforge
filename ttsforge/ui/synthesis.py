"""Compatibility alias for terminal synthesis prompts."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("ttsforge.cli.synthesis")
