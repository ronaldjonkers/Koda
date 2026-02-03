"""Tests for tool registry and base tools."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from koda.core.tools.registry import ToolRegistry
from koda.core.tools.base import BaseTool


class MockTool(BaseTool):
    """Mock tool for testing."""
    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string"}
        },
        "required": ["message"]
    }
    
    async def execute(self, **kwargs) -> str:
        return f"Executed with: {kwargs.get('message', '')}"


class TestToolRegistry:
    """Test tool registry functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create an empty tool registry."""
        return ToolRegistry()
    
    def test_register_tool(self, registry):
        """Test registering a tool."""
        tool = MockTool()
        registry.register(tool)
        assert "mock_tool" in registry._tools
    
    def test_get_tool(self, registry):
        """Test getting a registered tool."""
        tool = MockTool()
        registry.register(tool)
        retrieved = registry.get("mock_tool")
        assert retrieved == tool
    
    def test_get_nonexistent_tool(self, registry):
        """Test getting a non-existent tool returns None."""
        result = registry.get("nonexistent")
        assert result is None
    
    def test_list_tools(self, registry):
        """Test listing all registered tools."""
        registry.register(MockTool())
        tools = registry.tool_names
        assert "mock_tool" in tools
    
    def test_get_schemas(self, registry):
        """Test getting tool schemas for LLM."""
        registry.register(MockTool())
        schemas = registry.get_definitions()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "mock_tool"
    
    @pytest.mark.asyncio
    async def test_execute_tool(self, registry):
        """Test executing a tool through the registry."""
        registry.register(MockTool())
        result = await registry.execute("mock_tool", {"message": "hello"})
        assert "hello" in result


class TestBaseTool:
    """Test base tool functionality."""
    
    def test_tool_schema_generation(self):
        """Test that tool generates correct schema."""
        tool = MockTool()
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert "parameters" in schema["function"]
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool execution."""
        tool = MockTool()
        result = await tool.execute(message="test")
        assert "test" in result
