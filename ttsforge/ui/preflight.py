"""Compatibility alias for terminal preflight presentation."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("ttsforge.cli.preflight")
