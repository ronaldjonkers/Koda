"""Base class for Koda plugins.

Plugins extend the assistant's capabilities by providing new tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class PluginMetadata:
    """Metadata about a plugin."""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    enabled: bool = True
    # Tags for categorization
    tags: list[str] = field(default_factory=list)
    # Dependencies (other plugin names)
    dependencies: list[str] = field(default_factory=list)


class Plugin(ABC):
    """
    Base class for all Koda plugins.
    
    A plugin provides one or more tools that the LLM can use.
    
    Example plugin structure:
    ```python
    # ~/.koda/plugins/my_plugin.py
    from koda.plugins import Plugin, PluginMetadata
    
    class MyPlugin(Plugin):
        metadata = PluginMetadata(
            name="my_plugin",
            description="Does something useful",
            version="1.0.0",
            author="user"
        )
        
        def get_tools(self) -> list[dict]:
            return [{
                "name": "my_tool",
                "description": "Does the thing",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "The input"}
                    },
                    "required": ["input"]
                }
            }]
        
        async def execute(self, tool_name: str, **kwargs) -> str:
            if tool_name == "my_tool":
                return f"Result: {kwargs.get('input')}"
            return "Unknown tool"
    ```
    """
    
    metadata: PluginMetadata
    
    def __init__(self):
        """Initialize the plugin."""
        pass
    
    @abstractmethod
    def get_tools(self) -> list[dict]:
        """
        Return list of tool definitions this plugin provides.
        
        Each tool should have:
        - name: Tool name (will be prefixed with plugin name)
        - description: What the tool does
        - parameters: JSON schema for parameters
        
        Returns:
            List of tool definition dicts
        """
        pass
    
    @abstractmethod
    async def execute(self, tool_name: str, **kwargs: Any) -> str:
        """
        Execute a tool provided by this plugin.
        
        Args:
            tool_name: Name of the tool to execute (without plugin prefix)
            **kwargs: Tool parameters
            
        Returns:
            Result string to return to the LLM
        """
        pass
    
    def on_load(self) -> None:
        """Called when the plugin is loaded. Override for initialization."""
        pass
    
    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""
        pass
