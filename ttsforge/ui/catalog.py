"""Compatibility alias for terminal catalog presentation."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("ttsforge.cli.catalog")
