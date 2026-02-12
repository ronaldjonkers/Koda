"""Tests for accounts context injection into system prompts."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from koda.core.context import ContextBuilder


class TestAccountsContext:
    """Test that configured accounts are injected into the system prompt."""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace."""
        (tmp_path / "memory").mkdir()
        (tmp_path / "skills").mkdir()
        return tmp_path

    def _make_config(self, accounts):
        """Create a mock config with the given accounts."""
        config = MagicMock()
        config.integrations.accounts = accounts
        config.integrations.get_all_accounts.return_value = accounts
        return config

    def _make_account(self, name, acc_type, email="", capabilities=None, enabled=True):
        """Create a mock account object."""
        acc = MagicMock()
        acc.name = name
        acc.type = acc_type
        acc.email = email
        acc.capabilities = capabilities or []
        acc.enabled = enabled
        return acc

    def test_no_config_returns_empty(self, temp_workspace):
        """Test that no config produces no accounts section."""
        builder = ContextBuilder(workspace=temp_workspace, config=None)
        section = builder._build_accounts_section()
        assert section == ""

    def test_empty_accounts_returns_empty(self, temp_workspace):
        """Test that empty accounts list produces no section."""
        config = self._make_config([])
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()
        assert section == ""

    def test_email_accounts_listed(self, temp_workspace):
        """Test that email accounts are listed in the section."""
        accounts = [
            self._make_account("Gmail", "imap", "user@gmail.com", ["email"]),
            self._make_account("Work Exchange", "exchange", "user@work.com", ["email", "calendar"]),
        ]
        config = self._make_config(accounts)
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()

        assert "Gmail" in section
        assert "user@gmail.com" in section
        assert "Work Exchange" in section
        assert "user@work.com" in section
        assert "Email accounts" in section

    def test_calendar_accounts_listed(self, temp_workspace):
        """Test that calendar accounts are listed in the section."""
        accounts = [
            self._make_account("Work Calendar", "exchange", "user@work.com", ["calendar"]),
            self._make_account("Personal", "caldav", "", ["calendar"]),
        ]
        config = self._make_config(accounts)
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()

        assert "Calendar accounts" in section
        assert "Work Calendar" in section
        assert "Personal" in section

    def test_disabled_accounts_excluded(self, temp_workspace):
        """Test that disabled accounts are not listed."""
        accounts = [
            self._make_account("Active", "imap", "a@b.com", ["email"], enabled=True),
            self._make_account("Disabled", "imap", "d@b.com", ["email"], enabled=False),
        ]
        config = self._make_config(accounts)
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()

        assert "Active" in section
        assert "Disabled" not in section

    def test_never_invent_warning_present(self, temp_workspace):
        """Test that the warning about not inventing accounts is present."""
        accounts = [
            self._make_account("Test", "imap", "t@b.com", ["email"]),
        ]
        config = self._make_config(accounts)
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()

        assert "NEVER make up account names" in section
        assert "ONLY accounts that exist" in section

    def test_accounts_in_system_prompt(self, temp_workspace):
        """Test that accounts section appears in the full system prompt."""
        accounts = [
            self._make_account("MyMail", "imap", "me@example.com", ["email"]),
        ]
        config = self._make_config(accounts)
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        prompt = builder.build_system_prompt()

        assert "MyMail" in prompt
        assert "me@example.com" in prompt

    def test_dict_accounts_supported(self, temp_workspace):
        """Test that dict-based accounts (not Pydantic models) also work."""
        config = MagicMock()
        config.integrations.accounts = [
            {"name": "DictMail", "type": "imap", "email": "dict@b.com", "capabilities": ["email"], "enabled": True},
        ]
        config.integrations.get_all_accounts.return_value = config.integrations.accounts
        builder = ContextBuilder(workspace=temp_workspace, config=config)
        section = builder._build_accounts_section()

        assert "DictMail" in section
        assert "dict@b.com" in section
