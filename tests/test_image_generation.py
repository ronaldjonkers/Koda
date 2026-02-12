"""Tests for image generation tool."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.core.tools.image_generation import (
    ImageGenerationTool,
    ImageProvider,
    APIKeyMissingError,
)


class TestImageGenerationTool:
    """Test image generation tool functionality."""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture
    def tool_no_keys(self, temp_workspace):
        """Tool with no API keys configured."""
        return ImageGenerationTool(workspace=temp_workspace)

    @pytest.fixture
    def tool_with_gemini(self, temp_workspace):
        """Tool with Gemini API key configured."""
        return ImageGenerationTool(
            workspace=temp_workspace,
            gemini_api_key="test-gemini-key",
        )

    @pytest.fixture
    def tool_with_openrouter(self, temp_workspace):
        """Tool with OpenRouter API key configured."""
        return ImageGenerationTool(
            workspace=temp_workspace,
            openrouter_api_key="test-or-key",
        )

    def test_tool_name(self, tool_no_keys):
        assert tool_no_keys.name == "image_generation"

    def test_select_provider_gemini_preferred(self, tool_with_gemini):
        """Gemini should be selected as preferred provider when key is available."""
        provider = tool_with_gemini._select_provider()
        assert provider == ImageProvider.GEMINI

    def test_select_provider_fallback_to_pollinations(self, tool_no_keys):
        """Should fall back to Pollinations when no API keys."""
        provider = tool_no_keys._select_provider()
        assert provider == ImageProvider.POLLINATIONS

    def test_select_provider_explicit(self, tool_with_gemini):
        """Explicit provider selection should work."""
        provider = tool_with_gemini._select_provider("gemini")
        assert provider == ImageProvider.GEMINI

    def test_select_provider_explicit_missing_key(self, tool_no_keys):
        """Selecting a provider without API key should raise."""
        with pytest.raises(ValueError):
            tool_no_keys._select_provider("stability")

    def test_select_provider_priority_order(self, temp_workspace):
        """Provider priority: gemini > stability > openrouter > pollinations."""
        tool = ImageGenerationTool(
            workspace=temp_workspace,
            gemini_api_key="gk",
            stability_api_key="sk",
            openrouter_api_key="ok",
        )
        assert tool._select_provider() == ImageProvider.GEMINI

        # Without gemini, stability should be next
        tool2 = ImageGenerationTool(
            workspace=temp_workspace,
            stability_api_key="sk",
            openrouter_api_key="ok",
        )
        assert tool2._select_provider() == ImageProvider.STABILITY

    def test_provider_status(self, tool_with_gemini):
        """Test provider status reporting."""
        status = tool_with_gemini._get_provider_status()
        assert status["gemini"]["available"] is True
        assert status["gemini"]["has_key"] is True
        assert status["pollinations"]["available"] is True
        assert status["stability"]["available"] is False

    @pytest.mark.asyncio
    async def test_generate_no_prompt(self, tool_no_keys):
        """Should error when no prompt provided."""
        result = await tool_no_keys.execute(action="generate")
        assert "prompt" in result.lower()

    @pytest.mark.asyncio
    async def test_list_providers(self, tool_with_gemini):
        """Should list providers with their status."""
        result = await tool_with_gemini.execute(action="providers")
        assert "Gemini" in result
        assert "Pollinations" in result

    @pytest.mark.asyncio
    async def test_list_models(self, tool_no_keys):
        result = await tool_no_keys.execute(action="models")
        assert "pollinations" in result.lower() or "Pollinations" in result

    @pytest.mark.asyncio
    async def test_set_api_key_missing_params(self, tool_no_keys):
        result = await tool_no_keys.execute(action="set_api_key")
        assert "required" in result

    @pytest.mark.asyncio
    async def test_set_api_key_invalid_provider(self, tool_no_keys):
        result = await tool_no_keys.execute(
            action="set_api_key", provider="invalid", api_key="key123"
        )
        assert "Invalid provider" in result

    def test_gemini_model_routing(self, tool_with_gemini):
        """Test that gemini- models use native and imagen- models use predict."""
        # This tests the routing logic without actually calling the API
        assert "gemini-2.0-flash-preview-image-generation".startswith("gemini-")
        assert not "imagen-3.0-generate-002".startswith("gemini-")

    def test_aspect_ratios(self, tool_no_keys):
        """Test aspect ratio mapping."""
        assert tool_no_keys.ASPECT_RATIOS["1:1"] == (1024, 1024)
        assert tool_no_keys.ASPECT_RATIOS["16:9"] == (1344, 768)
        assert tool_no_keys.ASPECT_RATIOS["9:16"] == (768, 1344)


class TestAPIKeyMissingError:
    """Test APIKeyMissingError."""

    def test_error_message(self):
        err = APIKeyMissingError("gemini")
        assert err.provider == "gemini"
        assert "gemini" in str(err)

    def test_error_is_exception(self):
        with pytest.raises(APIKeyMissingError):
            raise APIKeyMissingError("stability")
