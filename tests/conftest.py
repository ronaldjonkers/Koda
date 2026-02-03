"""Pytest configuration and fixtures."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir()
        (workspace / "skills").mkdir()
        yield workspace


@pytest.fixture
def sample_config():
    """Return a sample configuration dictionary."""
    return {
        "assistant": {
            "name": "TestBot",
            "user_name": "TestUser",
            "language": "nl",
            "personality": "friendly"
        },
        "agents": {
            "defaults": {
                "workspace": "~/.koda/workspace",
                "model": "anthropic/claude-3-sonnet",
                "max_tokens": 4096,
                "temperature": 0.7,
                "max_tool_iterations": 10
            }
        },
        "channels": {
            "whatsapp": {
                "enabled": False,
                "bot_mode": False
            },
            "telegram": {
                "enabled": False
            }
        },
        "providers": {
            "anthropic": {"api_key": "test-key"},
            "openrouter": {"api_key": ""}
        },
        "gateway": {
            "host": "127.0.0.1",
            "port": 18790
        },
        "integrations": {
            "calendar_accounts": [],
            "email_accounts": [],
            "google": {"enabled": False},
            "exchange": {"enabled": False},
            "caldav": {"enabled": False},
            "reminder": {"enabled": True}
        }
    }


@pytest.fixture
def mock_bus():
    """Create a mock message bus."""
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.consume_inbound = AsyncMock()
    return bus


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value={
        "content": "Test response",
        "tool_calls": None
    })
    return provider
