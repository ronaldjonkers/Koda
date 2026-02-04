"""
Koda Plugin System

Allows dynamic loading of plugins from:
- ~/.koda/plugins/ (user plugins)
- Built-in plugins

Plugins can be:
- Created by the LLM to solve problems
- Added manually by users
- Shared between users
"""

from koda.plugins.base import Plugin, PluginMetadata
from koda.plugins.loader import PluginLoader

__all__ = ["Plugin", "PluginMetadata", "PluginLoader"]
