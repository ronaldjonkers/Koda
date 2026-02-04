"""Plugin loader for dynamically loading plugins from disk."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from koda.plugins.base import Plugin, PluginMetadata


class PluginLoader:
    """
    Loads and manages plugins from the plugins directory.
    
    Default plugin directory: ~/.koda/plugins/
    """
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        self.plugins_dir = plugins_dir or (Path.home() / ".koda" / "plugins")
        self._plugins: dict[str, Plugin] = {}
        self._disabled: set[str] = set()
    
    def ensure_plugins_dir(self) -> None:
        """Create plugins directory if it doesn't exist."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # Create example plugin if directory is empty
        example_path = self.plugins_dir / "_example_plugin.py.disabled"
        if not any(self.plugins_dir.glob("*.py")):
            example_path.write_text(EXAMPLE_PLUGIN)
            logger.debug(f"Created example plugin at {example_path}")
    
    def load_all(self) -> dict[str, Plugin]:
        """
        Load all plugins from the plugins directory.
        
        Returns:
            Dict of plugin_name -> Plugin instance
        """
        self.ensure_plugins_dir()
        
        for plugin_file in self.plugins_dir.glob("*.py"):
            # Skip disabled plugins (ending in .disabled or starting with _)
            if plugin_file.name.startswith("_"):
                continue
            
            try:
                plugin = self._load_plugin_file(plugin_file)
                if plugin:
                    self._plugins[plugin.metadata.name] = plugin
                    plugin.on_load()
                    logger.info(f"Loaded plugin: {plugin.metadata.name} v{plugin.metadata.version}")
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file.name}: {e}")
        
        return self._plugins
    
    def _load_plugin_file(self, path: Path) -> Optional[Plugin]:
        """Load a single plugin from a Python file."""
        module_name = f"koda_plugin_{path.stem}"
        
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # Find Plugin subclass in module
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and 
                issubclass(obj, Plugin) and 
                obj is not Plugin and
                hasattr(obj, 'metadata')):
                return obj()
        
        return None
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)
    
    def list_plugins(self) -> list[PluginMetadata]:
        """List all loaded plugins."""
        return [p.metadata for p in self._plugins.values()]
    
    def reload_plugin(self, name: str) -> bool:
        """Reload a plugin from disk."""
        plugin_file = self.plugins_dir / f"{name}.py"
        if not plugin_file.exists():
            return False
        
        # Unload if loaded
        if name in self._plugins:
            self._plugins[name].on_unload()
            del self._plugins[name]
        
        # Reload
        try:
            plugin = self._load_plugin_file(plugin_file)
            if plugin:
                self._plugins[name] = plugin
                plugin.on_load()
                return True
        except Exception as e:
            logger.error(f"Failed to reload plugin {name}: {e}")
        
        return False
    
    def enable_plugin(self, name: str) -> bool:
        """Enable a disabled plugin."""
        disabled_path = self.plugins_dir / f"_{name}.py"
        enabled_path = self.plugins_dir / f"{name}.py"
        
        if disabled_path.exists():
            disabled_path.rename(enabled_path)
            self.reload_plugin(name)
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """Disable an enabled plugin."""
        enabled_path = self.plugins_dir / f"{name}.py"
        disabled_path = self.plugins_dir / f"_{name}.py"
        
        if enabled_path.exists():
            # Unload first
            if name in self._plugins:
                self._plugins[name].on_unload()
                del self._plugins[name]
            
            enabled_path.rename(disabled_path)
            return True
        return False
    
    def get_all_tools(self) -> list[dict]:
        """
        Get all tools from all loaded plugins.
        
        Tool names are prefixed with plugin name to avoid conflicts.
        """
        all_tools = []
        for plugin in self._plugins.values():
            if not plugin.metadata.enabled:
                continue
            
            for tool in plugin.get_tools():
                # Prefix tool name with plugin name
                prefixed_tool = tool.copy()
                prefixed_tool["name"] = f"{plugin.metadata.name}.{tool['name']}"
                prefixed_tool["_plugin"] = plugin.metadata.name
                all_tools.append(prefixed_tool)
        
        return all_tools
    
    async def execute_tool(self, full_tool_name: str, **kwargs: Any) -> str:
        """
        Execute a plugin tool.
        
        Args:
            full_tool_name: Plugin-prefixed tool name (e.g., "my_plugin.my_tool")
            **kwargs: Tool parameters
            
        Returns:
            Tool result string
        """
        if "." not in full_tool_name:
            return f"Error: Invalid tool name '{full_tool_name}' - must be plugin.tool format"
        
        plugin_name, tool_name = full_tool_name.split(".", 1)
        
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return f"Error: Plugin '{plugin_name}' not found"
        
        if not plugin.metadata.enabled:
            return f"Error: Plugin '{plugin_name}' is disabled"
        
        try:
            return await plugin.execute(tool_name, **kwargs)
        except Exception as e:
            logger.error(f"Plugin {plugin_name} tool {tool_name} error: {e}")
            return f"Error: {e}"


EXAMPLE_PLUGIN = '''"""
Example Koda Plugin

Rename this file (remove leading underscore and .disabled) to enable it.
"""

from koda.plugins import Plugin, PluginMetadata


class ExamplePlugin(Plugin):
    """An example plugin that demonstrates the plugin structure."""
    
    metadata = PluginMetadata(
        name="example",
        description="An example plugin showing how to create plugins",
        version="1.0.0",
        author="Koda",
        tags=["example", "demo"]
    )
    
    def get_tools(self) -> list[dict]:
        """Define the tools this plugin provides."""
        return [
            {
                "name": "hello",
                "description": "Says hello to someone",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name to greet"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "calculate",
                "description": "Performs a simple calculation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Math expression to evaluate (e.g., '2 + 2')"
                        }
                    },
                    "required": ["expression"]
                }
            }
        ]
    
    async def execute(self, tool_name: str, **kwargs) -> str:
        """Execute one of our tools."""
        if tool_name == "hello":
            name = kwargs.get("name", "World")
            return f"Hello, {name}! 👋"
        
        elif tool_name == "calculate":
            expr = kwargs.get("expression", "")
            try:
                # Safe evaluation of simple math
                allowed = set("0123456789+-*/.() ")
                if all(c in allowed for c in expr):
                    result = eval(expr)
                    return f"{expr} = {result}"
                else:
                    return "Error: Only simple math expressions allowed"
            except Exception as e:
                return f"Error: {e}"
        
        return f"Unknown tool: {tool_name}"
'''
