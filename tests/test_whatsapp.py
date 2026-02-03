"""Tests for WhatsApp channel functionality."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from koda.config.schema import WhatsAppConfig, WhatsAppContactRule
from koda.services.whatsapp import WhatsAppChannel


class TestWhatsAppChannel:
    """Test WhatsApp channel functionality."""
    
    @pytest.fixture
    def mock_bus(self):
        """Create a mock message bus."""
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()
        return bus
    
    @pytest.fixture
    def basic_config(self):
        """Create a basic WhatsApp config."""
        return WhatsAppConfig(
            enabled=True,
            bridge_url="ws://localhost:3001"
        )
    
    @pytest.fixture
    def bot_mode_config(self):
        """Create a bot mode WhatsApp config."""
        return WhatsAppConfig(
            enabled=True,
            bot_mode=True,
            bot_phone="+31612345678",
            owner_phone="+31687654321",
            owner_name="Jan",
            escalate_to_owner=True,
            escalation_keywords=["afspraak", "urgent", "bellen"],
            contact_rules=[
                WhatsAppContactRule(
                    phone="+31611111111",
                    name="VIP Klant",
                    instructions="Be extra helpful to this VIP customer",
                    auto_reply=True
                )
            ]
        )
    
    def test_is_allowed_bot_mode(self, bot_mode_config, mock_bus):
        """Test that bot mode allows all senders."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        assert channel.is_allowed("+31699999999") is True
        assert channel.is_allowed("+31688888888") is True
    
    def test_is_allowed_with_contact_rule(self, basic_config, mock_bus):
        """Test that contact rules allow specific numbers."""
        basic_config.contact_rules = [
            WhatsAppContactRule(phone="+31611111111", name="Test")
        ]
        channel = WhatsAppChannel(basic_config, mock_bus)
        assert channel.is_allowed("+31611111111") is True
    
    def test_is_allowed_with_allow_list(self, basic_config, mock_bus):
        """Test that allow_from list works."""
        basic_config.allow_from = ["+31622222222"]
        channel = WhatsAppChannel(basic_config, mock_bus)
        assert channel.is_allowed("+31622222222") is True
    
    def test_get_contact_rule(self, bot_mode_config, mock_bus):
        """Test getting contact rule by phone number."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        rule = channel._get_contact_rule("+31611111111")
        assert rule is not None
        assert rule.name == "VIP Klant"
    
    def test_get_contact_rule_normalized(self, bot_mode_config, mock_bus):
        """Test contact rule lookup with phone normalization."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        # Test with different formats
        rule = channel._get_contact_rule("31611111111")  # Without +
        assert rule is not None
        assert rule.name == "VIP Klant"
    
    def test_should_escalate_with_keyword(self, bot_mode_config, mock_bus):
        """Test escalation detection with keywords."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        
        assert channel._should_escalate("Ik wil een afspraak maken", None) is True
        assert channel._should_escalate("Dit is urgent!", None) is True
        assert channel._should_escalate("Kun je me terugbellen?", None) is True
        assert channel._should_escalate("Hallo, hoe gaat het?", None) is False
    
    def test_should_escalate_disabled(self, basic_config, mock_bus):
        """Test that escalation can be disabled."""
        basic_config.escalate_to_owner = False
        channel = WhatsAppChannel(basic_config, mock_bus)
        
        assert channel._should_escalate("Dit is urgent!", None) is False
    
    def test_get_greeting(self, bot_mode_config, mock_bus):
        """Test greeting message generation."""
        channel = WhatsAppChannel(
            bot_mode_config, 
            mock_bus,
            assistant_name="Koda"
        )
        greeting = channel._get_greeting()
        assert "Koda" in greeting
        assert "Jan" in greeting
    
    def test_get_instructions_for_known_contact(self, bot_mode_config, mock_bus):
        """Test getting custom instructions for known contact."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        instructions = channel._get_instructions_for_contact("+31611111111")
        assert "VIP" in instructions
    
    def test_get_instructions_for_unknown_contact(self, bot_mode_config, mock_bus):
        """Test getting default instructions for unknown contact."""
        channel = WhatsAppChannel(bot_mode_config, mock_bus)
        instructions = channel._get_instructions_for_contact("+31699999999")
        assert instructions == bot_mode_config.default_instructions
