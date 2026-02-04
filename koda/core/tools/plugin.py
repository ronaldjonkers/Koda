"""
Plugin management tool for the LLM.

Allows the agent to:
- Create new plugins to solve problems
- List available plugins
- Enable/disable plugins
- View plugin source code
"""

import json
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from loguru import logger

from koda.core.tools.base import Tool

if TYPE_CHECKING:
    from koda.plugins.base import Plugin
    from koda.plugins.loader import PluginLoader


class PluginWrapperTool(Tool):
    """
    Wrapper that exposes a plugin's tools to the LLM.
    
    Each loaded plugin gets wrapped in this class to make its tools
    available as a single tool with multiple actions.
    """
    
    def __init__(self, plugin: "Plugin", loader: "PluginLoader"):
        self.plugin = plugin
        self.loader = loader
        self._name = f"plugin_{plugin.metadata.name}"
        self._description = self._build_description()
        self._parameters = self._build_parameters()
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def parameters(self) -> dict:
        return self._parameters
    
    def _build_description(self) -> str:
        """Build description from plugin metadata and tools."""
        tools = self.plugin.get_tools()
        tool_list = "\n".join([
            f"- {t['name']}: {t.get('description', '')[:60]}"
            for t in tools
        ])
        return f"""{self.plugin.metadata.description}

Available actions:
{tool_list}
"""
    
    def _build_parameters(self) -> dict:
        """Build parameters schema from plugin tools."""
        tools = self.plugin.get_tools()
        tool_names = [t["name"] for t in tools]
        
        # Merge all tool parameters
        all_properties = {
            "action": {
                "type": "string",
                "enum": tool_names,
                "description": "Which tool action to perform"
            }
        }
        
        for tool in tools:
            params = tool.get("parameters", {}).get("properties", {})
            for param_name, param_def in params.items():
                if param_name not in all_properties:
                    all_properties[param_name] = param_def
        
        return {
            "type": "object",
            "properties": all_properties,
            "required": ["action"]
        }
    
    async def execute(self, **kwargs: Any) -> str:
        """Execute a plugin tool."""
        action = kwargs.pop("action", "")
        if not action:
            return "Error: 'action' is required"
        
        try:
            return await self.plugin.execute(action, **kwargs)
        except Exception as e:
            logger.error(f"Plugin {self.plugin.metadata.name} error: {e}")
            return f"Error: {e}"


class PluginTool(Tool):
    """
    Tool for managing plugins.
    
    The LLM can use this to create new plugins when it needs functionality
    that doesn't exist, or to manage existing plugins.
    """
    
    name = "plugin"
    description = """Create and manage plugins to extend capabilities.

Use this when you need functionality that doesn't exist in the current tools.
You can write Python code to create new tools.

Actions:
- create: Create a new plugin with custom tools
- list: List all available plugins
- view: View a plugin's source code
- enable: Enable a disabled plugin
- disable: Disable a plugin
- delete: Delete a plugin

Example - Create a plugin:
{
    "action": "create",
    "name": "weather_alerts",
    "description": "Sends weather alerts for severe conditions",
    "code": "... python code ..."
}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "view", "enable", "disable", "delete"],
                "description": "Action to perform"
            },
            "name": {
                "type": "string",
                "description": "Plugin name (for create/view/enable/disable/delete)"
            },
            "description": {
                "type": "string",
                "description": "Plugin description (for create)"
            },
            "code": {
                "type": "string",
                "description": "Python code for the plugin (for create)"
            },
            "tools": {
                "type": "array",
                "description": "Tool definitions for the plugin (for create)",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "parameters": {"type": "object"}
                    }
                }
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        self.plugins_dir = plugins_dir or (Path.home() / ".koda" / "plugins")
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        
        try:
            if action == "create":
                return self._create_plugin(
                    name=kwargs.get("name", ""),
                    description=kwargs.get("description", ""),
                    code=kwargs.get("code", ""),
                    tools=kwargs.get("tools", [])
                )
            elif action == "list":
                return self._list_plugins()
            elif action == "view":
                return self._view_plugin(kwargs.get("name", ""))
            elif action == "enable":
                return self._enable_plugin(kwargs.get("name", ""))
            elif action == "disable":
                return self._disable_plugin(kwargs.get("name", ""))
            elif action == "delete":
                return self._delete_plugin(kwargs.get("name", ""))
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Plugin tool error: {e}")
            return f"Error: {e}"
    
    def _create_plugin(self, name: str, description: str, code: str, tools: list) -> str:
        """Create a new plugin."""
        if not name:
            return "Error: Plugin name is required"
        
        # Sanitize name
        name = name.lower().replace(" ", "_").replace("-", "_")
        if not name.isidentifier():
            return f"Error: Invalid plugin name '{name}' - must be a valid Python identifier"
        
        plugin_path = self.plugins_dir / f"{name}.py"
        
        if plugin_path.exists():
            return f"Error: Plugin '{name}' already exists. Delete it first or choose a different name."
        
        # If code is provided directly, use it
        if code and "class " in code and "Plugin" in code:
            # User provided full plugin code
            plugin_code = code
        else:
            # Generate plugin from tools definition
            if not tools:
                return "Error: Either 'code' (full plugin) or 'tools' (tool definitions) is required"
            
            plugin_code = self._generate_plugin_code(name, description, tools, code)
        
        # Validate the code can be parsed
        try:
            compile(plugin_code, plugin_path, "exec")
        except SyntaxError as e:
            return f"Error: Invalid Python syntax - {e}"
        
        # Write the plugin
        plugin_path.write_text(plugin_code)
        
        logger.info(f"Created plugin: {name}")
        
        return f"""✅ Plugin '{name}' created!

Location: {plugin_path}

The plugin will be loaded on next gateway restart, or you can ask me to reload plugins.

Tools provided:
{self._format_tools(tools) if tools else '(custom - see code)'}
"""
    
    def _generate_plugin_code(self, name: str, description: str, tools: list, execute_code: str = "") -> str:
        """Generate plugin code from tool definitions."""
        class_name = "".join(word.title() for word in name.split("_")) + "Plugin"
        
        # Generate tool definitions
        tools_code = json.dumps(tools, indent=12)
        
        # Generate execute method
        if execute_code:
            execute_body = execute_code
        else:
            # Generate basic execute stubs
            cases = []
            for tool in tools:
                tool_name = tool.get("name", "unknown")
                cases.append(f'''        if tool_name == "{tool_name}":
            # TODO: Implement {tool_name}
            return f"{tool_name} called with: {{kwargs}}"
''')
            execute_body = "\n".join(cases) + '        return f"Unknown tool: {tool_name}"'
        
        return f'''"""
{description or f'{name} plugin'}

Auto-generated plugin for Koda.
"""

from koda.plugins import Plugin, PluginMetadata


class {class_name}(Plugin):
    """{description or name}"""
    
    metadata = PluginMetadata(
        name="{name}",
        description="""{description or name}""",
        version="1.0.0",
        author="Koda AI",
        tags=["auto-generated"]
    )
    
    def get_tools(self) -> list[dict]:
        return {tools_code}
    
    async def execute(self, tool_name: str, **kwargs) -> str:
{execute_body}
'''
    
    def _list_plugins(self) -> str:
        """List all plugins."""
        enabled = list(self.plugins_dir.glob("*.py"))
        disabled = list(self.plugins_dir.glob("_*.py"))
        
        # Filter out __init__.py etc
        enabled = [p for p in enabled if not p.name.startswith("__")]
        
        if not enabled and not disabled:
            return "No plugins installed.\n\nUse `plugin create` to create a new plugin."
        
        lines = ["📦 **Installed Plugins:**\n"]
        
        if enabled:
            lines.append("**Enabled:**")
            for p in enabled:
                name = p.stem
                lines.append(f"  ✅ {name}")
        
        if disabled:
            lines.append("\n**Disabled:**")
            for p in disabled:
                name = p.stem.lstrip("_")
                lines.append(f"  ⏸️ {name}")
        
        lines.append(f"\nPlugin directory: {self.plugins_dir}")
        return "\n".join(lines)
    
    def _view_plugin(self, name: str) -> str:
        """View plugin source code."""
        if not name:
            return "Error: Plugin name is required"
        
        # Try enabled first, then disabled
        plugin_path = self.plugins_dir / f"{name}.py"
        if not plugin_path.exists():
            plugin_path = self.plugins_dir / f"_{name}.py"
        
        if not plugin_path.exists():
            return f"Error: Plugin '{name}' not found"
        
        code = plugin_path.read_text()
        return f"```python\n# {plugin_path}\n{code}\n```"
    
    def _enable_plugin(self, name: str) -> str:
        """Enable a disabled plugin."""
        if not name:
            return "Error: Plugin name is required"
        
        disabled_path = self.plugins_dir / f"_{name}.py"
        enabled_path = self.plugins_dir / f"{name}.py"
        
        if enabled_path.exists():
            return f"Plugin '{name}' is already enabled"
        
        if not disabled_path.exists():
            return f"Error: Plugin '{name}' not found"
        
        disabled_path.rename(enabled_path)
        return f"✅ Plugin '{name}' enabled. Restart gateway to load it."
    
    def _disable_plugin(self, name: str) -> str:
        """Disable a plugin."""
        if not name:
            return "Error: Plugin name is required"
        
        enabled_path = self.plugins_dir / f"{name}.py"
        disabled_path = self.plugins_dir / f"_{name}.py"
        
        if disabled_path.exists():
            return f"Plugin '{name}' is already disabled"
        
        if not enabled_path.exists():
            return f"Error: Plugin '{name}' not found"
        
        enabled_path.rename(disabled_path)
        return f"✅ Plugin '{name}' disabled."
    
    def _delete_plugin(self, name: str) -> str:
        """Delete a plugin."""
        if not name:
            return "Error: Plugin name is required"
        
        # Try both enabled and disabled
        for pattern in [f"{name}.py", f"_{name}.py"]:
            path = self.plugins_dir / pattern
            if path.exists():
                path.unlink()
                return f"✅ Plugin '{name}' deleted."
        
        return f"Error: Plugin '{name}' not found"
    
    def _format_tools(self, tools: list) -> str:
        """Format tools list for display."""
        if not tools:
            return "(none)"
        
        lines = []
        for tool in tools:
            name = tool.get("name", "?")
            desc = tool.get("description", "")[:50]
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)
