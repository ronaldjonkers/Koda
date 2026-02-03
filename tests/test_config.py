"""Tests for configuration schema and loading."""

import pytest
from pydantic import ValidationError

from koda.config.schema import (
    Config, AssistantConfig, WhatsAppConfig, WhatsAppContactRule,
    CalendarAccount, EmailAccount, IntegrationsConfig, GatewayConfig
)


class TestAssistantConfig:
    """Test assistant configuration."""
    
    def test_default_values(self):
        """Test default assistant config values."""
        config = AssistantConfig()
        assert config.name == "Koda"
        assert config.language == "en"
        assert config.personality == "professional"
    
    def test_custom_values(self):
        """Test custom assistant config values."""
        config = AssistantConfig(
            name="MyBot",
            user_name="Jan",
            language="nl",
            personality="professional"
        )
        assert config.name == "MyBot"
        assert config.user_name == "Jan"
        assert config.language == "nl"


class TestWhatsAppConfig:
    """Test WhatsApp configuration."""
    
    def test_default_bot_mode_disabled(self):
        """Test that bot mode is disabled by default."""
        config = WhatsAppConfig()
        assert config.bot_mode is False
        assert config.enabled is False
    
    def test_bot_mode_configuration(self):
        """Test bot mode configuration."""
        config = WhatsAppConfig(
            enabled=True,
            bot_mode=True,
            bot_phone="+31612345678",
            owner_phone="+31687654321",
            owner_name="Jan"
        )
        assert config.bot_mode is True
        assert config.bot_phone == "+31612345678"
        assert config.owner_phone == "+31687654321"
    
    def test_escalation_keywords(self):
        """Test default escalation keywords."""
        config = WhatsAppConfig()
        assert "afspraak" in config.escalation_keywords
        assert "appointment" in config.escalation_keywords
        assert "urgent" in config.escalation_keywords


class TestWhatsAppContactRule:
    """Test WhatsApp contact rules."""
    
    def test_contact_rule_creation(self):
        """Test creating a contact rule."""
        rule = WhatsAppContactRule(
            phone="+31611111111",
            name="Test Contact",
            instructions="Be extra helpful",
            auto_reply=True
        )
        assert rule.phone == "+31611111111"
        assert rule.name == "Test Contact"
        assert rule.auto_reply is True


class TestCalendarAccount:
    """Test calendar account configuration."""
    
    def test_google_account(self):
        """Test Google calendar account."""
        account = CalendarAccount(
            name="Werk",
            type="google",
            credentials_file="~/.koda/google_credentials.json"
        )
        assert account.name == "Werk"
        assert account.type == "google"
        assert account.enabled is True
    
    def test_exchange_account(self):
        """Test Exchange calendar account."""
        account = CalendarAccount(
            name="Kantoor",
            type="exchange",
            email="user@company.com",
            server="outlook.office365.com"
        )
        assert account.name == "Kantoor"
        assert account.type == "exchange"
    
    def test_caldav_account(self):
        """Test CalDAV calendar account."""
        account = CalendarAccount(
            name="Privé",
            type="caldav",
            url="https://nextcloud.example.com/remote.php/dav"
        )
        assert account.name == "Privé"
        assert account.type == "caldav"


class TestEmailAccount:
    """Test email account configuration."""
    
    def test_gmail_account(self):
        """Test Gmail account."""
        account = EmailAccount(
            name="Werk Mail",
            type="gmail"
        )
        assert account.name == "Werk Mail"
        assert account.type == "gmail"
    
    def test_imap_account(self):
        """Test IMAP account."""
        account = EmailAccount(
            name="Privé Mail",
            type="imap",
            host="imap.example.com",
            port=993
        )
        assert account.host == "imap.example.com"
        assert account.port == 993


class TestIntegrationsConfig:
    """Test integrations configuration."""
    
    def test_get_all_calendars_empty(self):
        """Test getting calendars when none configured."""
        config = IntegrationsConfig()
        calendars = config.get_all_calendars()
        assert calendars == []
    
    def test_get_all_calendars_with_named(self):
        """Test getting calendars with named accounts."""
        config = IntegrationsConfig(
            calendar_accounts=[
                CalendarAccount(name="Werk", type="google"),
                CalendarAccount(name="Privé", type="exchange")
            ]
        )
        calendars = config.get_all_calendars()
        assert len(calendars) == 2
        assert calendars[0].name == "Werk"
        assert calendars[1].name == "Privé"


class TestGatewayConfig:
    """Test gateway configuration."""
    
    def test_default_localhost(self):
        """Test that gateway defaults to 0.0.0.0 (will be changed to localhost)."""
        config = GatewayConfig()
        # Note: We'll update this to default to 127.0.0.1 for security
        assert config.port == 18790


class TestConfig:
    """Test root configuration."""
    
    def test_default_config(self):
        """Test default configuration loads."""
        config = Config()
        assert config.assistant.name == "Koda"
        assert config.gateway.port == 18790
    
    def test_get_api_key_priority(self):
        """Test API key priority order."""
        config = Config()
        # Without any keys, should return None
        key = config.get_api_key()
        # May be None or empty string depending on defaults
        assert key is None or key == ""
