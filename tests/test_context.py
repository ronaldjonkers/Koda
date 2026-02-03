"""Tests for context builder and language detection."""

import pytest
from pathlib import Path

from koda.core.context import ContextBuilder


class TestLanguageDetection:
    """Test language detection functionality."""
    
    @pytest.fixture
    def context(self, temp_workspace):
        """Create a context builder with temp workspace."""
        return ContextBuilder(
            workspace=temp_workspace,
            assistant_name="TestBot",
            user_name="TestUser",
            default_language="en"
        )
    
    def test_detect_dutch(self, context):
        """Test Dutch language detection."""
        dutch_texts = [
            "Ik wil een afspraak maken voor morgen",
            "Kun je me helpen met het plannen van een meeting?",
            "Wat heb ik vandaag op de agenda staan?",
            "Stuur een bericht naar Jan",
        ]
        for text in dutch_texts:
            assert context.detect_language(text) == "nl", f"Failed for: {text}"
    
    def test_detect_english(self, context):
        """Test English language detection."""
        english_texts = [
            "I would like to schedule a meeting tomorrow",
            "Can you help me with the calendar?",
            "What appointments do I have today?",
            "Please send a message to John",
        ]
        for text in english_texts:
            assert context.detect_language(text) == "en", f"Failed for: {text}"
    
    def test_detect_german(self, context):
        """Test German language detection."""
        german_texts = [
            "Ich möchte einen Termin für morgen machen",
            "Können Sie mir helfen mit dem Kalender?",
        ]
        for text in german_texts:
            assert context.detect_language(text) == "de", f"Failed for: {text}"
    
    def test_short_text_fallback(self, context):
        """Test that short text falls back to default language."""
        assert context.detect_language("Hi") == "en"
        assert context.detect_language("") == "en"
    
    def test_custom_default_language(self, temp_workspace):
        """Test custom default language."""
        context = ContextBuilder(
            workspace=temp_workspace,
            default_language="nl"
        )
        assert context.detect_language("Hi") == "nl"


class TestContextBuilder:
    """Test context builder functionality."""
    
    @pytest.fixture
    def context(self, temp_workspace):
        """Create a context builder."""
        return ContextBuilder(
            workspace=temp_workspace,
            assistant_name="Koda",
            user_name="Jan"
        )
    
    def test_system_prompt_contains_assistant_name(self, context):
        """Test that system prompt contains assistant name."""
        prompt = context.build_system_prompt()
        assert "Koda" in prompt
    
    def test_system_prompt_contains_language_instruction(self, context):
        """Test that system prompt contains language instruction."""
        prompt = context.build_system_prompt(detected_language="nl")
        assert "CRITICAL LANGUAGE RULES" in prompt
        assert "Nederlands" in prompt
    
    def test_build_messages_includes_system_prompt(self, context):
        """Test that build_messages includes system prompt."""
        messages = context.build_messages(
            history=[],
            current_message="Hallo, hoe gaat het?"
        )
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hallo, hoe gaat het?"
    
    def test_build_messages_detects_language(self, context):
        """Test that build_messages detects language from message."""
        messages = context.build_messages(
            history=[],
            current_message="Ik wil een afspraak maken"
        )
        # System prompt should contain Dutch language reference
        assert "Nederlands" in messages[0]["content"]
