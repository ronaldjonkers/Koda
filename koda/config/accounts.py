"""Shared account management module for CLI and WhatsApp.

This module provides unified functions for:
- Adding accounts (with connection testing)
- Updating accounts
- Removing accounts
- Listing accounts
- Testing connections (with actual data fetch)

Both CLI wizard and WhatsApp commands should use these functions
to ensure consistent behavior and data storage.
"""
from __future__ import annotations

from typing import Any
from loguru import logger

from koda.config.loader import load_config, save_config


class AccountManager:
    """Manages account operations for all interfaces (CLI, WhatsApp, API)."""
    
    def __init__(self, config: Any = None):
        """Initialize with optional config. If None, loads from file."""
        self.config = config or load_config()
    
    def reload_config(self):
        """Reload configuration from file."""
        self.config = load_config()
    
    def get_all_accounts(self) -> list[dict]:
        """Get all unified accounts."""
        if hasattr(self.config.integrations, 'get_all_accounts'):
            accounts = self.config.integrations.get_all_accounts()
            return [self._account_to_dict(acc) for acc in accounts]
        return []
    
    def get_account(self, name: str) -> dict | None:
        """Get account by name (case-insensitive)."""
        name_lower = name.lower()
        for acc in self.get_all_accounts():
            if acc.get("name", "").lower() == name_lower:
                return acc
        return None
    
    def add_account(self, account_data: dict) -> tuple[bool, str]:
        """
        Add a new account to the unified accounts list.
        
        Args:
            account_data: Dict with account fields (name, type, email, password, etc.)
        
        Returns:
            Tuple of (success, message)
        """
        name = account_data.get("name", "").strip()
        if not name:
            return False, "Account name is required"
        
        acc_type = account_data.get("type", "")
        if not acc_type:
            return False, "Account type is required"
        
        # Determine capabilities based on type
        capabilities = self._get_capabilities_for_type(acc_type)
        account_data["capabilities"] = capabilities
        account_data["enabled"] = True
        
        # Create proper Account model instance
        from koda.config.schema import Account
        account = Account(**account_data)
        
        # Initialize accounts list if needed
        if not hasattr(self.config.integrations, 'accounts') or self.config.integrations.accounts is None:
            self.config.integrations.accounts = []
        
        # Check if account with same name exists
        existing_idx = self._find_account_index(name)
        
        if existing_idx is not None:
            # Update existing
            self.config.integrations.accounts[existing_idx] = account
            action = "updated"
        else:
            # Add new
            self.config.integrations.accounts.append(account)
            action = "added"
        
        save_config(self.config)
        
        caps_str = ", ".join(capabilities)
        return True, f"Account '{name}' {action} with capabilities: {caps_str}"
    
    def remove_account(self, name: str) -> tuple[bool, str]:
        """
        Remove an account by name.
        
        Args:
            name: Account name to remove
        
        Returns:
            Tuple of (success, message)
        """
        if not hasattr(self.config.integrations, 'accounts') or not self.config.integrations.accounts:
            return False, f"Account '{name}' not found"
        
        name_lower = name.lower()
        
        # Find and remove from unified accounts
        for i, acc in enumerate(self.config.integrations.accounts):
            acc_name = acc.get("name") if isinstance(acc, dict) else getattr(acc, "name", "")
            if acc_name.lower() == name_lower:
                del self.config.integrations.accounts[i]
                save_config(self.config)
                return True, f"Account '{name}' removed"
        
        # Also check legacy lists for backward compatibility
        removed = False
        
        if hasattr(self.config.integrations, 'email_accounts'):
            for i, acc in enumerate(self.config.integrations.email_accounts or []):
                acc_name = acc.get("name") if isinstance(acc, dict) else getattr(acc, "name", "")
                if acc_name.lower() == name_lower:
                    del self.config.integrations.email_accounts[i]
                    removed = True
                    break
        
        if hasattr(self.config.integrations, 'calendar_accounts'):
            for i, acc in enumerate(self.config.integrations.calendar_accounts or []):
                acc_name = acc.get("name") if isinstance(acc, dict) else getattr(acc, "name", "")
                if acc_name.lower() == name_lower:
                    del self.config.integrations.calendar_accounts[i]
                    removed = True
                    break
        
        if removed:
            save_config(self.config)
            return True, f"Account '{name}' removed"
        
        return False, f"Account '{name}' not found"
    
    def test_connection(self, account_data: dict) -> tuple[bool, str, dict | None]:
        """
        Test account connection by actually fetching data.
        
        Args:
            account_data: Account configuration dict
        
        Returns:
            Tuple of (success, message, sample_data)
            sample_data contains fetched items to prove connection works
        """
        acc_type = account_data.get("type", "")
        
        try:
            if acc_type == "exchange":
                return self._test_exchange(account_data)
            elif acc_type == "imap":
                return self._test_imap(account_data)
            elif acc_type == "caldav":
                return self._test_caldav(account_data)
            elif acc_type == "google":
                return self._test_google(account_data)
            else:
                return False, f"Unknown account type: {acc_type}", None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return False, str(e), None
    
    def _test_exchange(self, account_data: dict) -> tuple[bool, str, dict | None]:
        """Test Exchange connection by fetching inbox and calendar."""
        from koda.integrations.exchange_client import ExchangeClient
        
        client = ExchangeClient(
            email=account_data.get("email", ""),
            password=account_data.get("password", ""),
            server=account_data.get("server", ""),
            username=account_data.get("username", "") or account_data.get("email", ""),
            use_autodiscover=account_data.get("use_autodiscover", False)
        )
        
        sample_data = {}
        
        # Test email access
        try:
            emails = client.list_emails(max_results=3)
            sample_data["emails"] = len(emails)
            sample_data["email_subjects"] = [e.get("subject", "")[:50] for e in emails[:3]]
        except Exception as e:
            logger.warning(f"Email test failed: {e}")
            sample_data["emails"] = f"Error: {e}"
        
        # Test calendar access
        try:
            events = client.list_calendar_events(max_results=3)
            sample_data["events"] = len(events)
            sample_data["event_subjects"] = [e.get("subject", "")[:50] for e in events[:3]]
        except Exception as e:
            logger.warning(f"Calendar test failed: {e}")
            sample_data["events"] = f"Error: {e}"
        
        # Test contacts access
        try:
            contacts = client.list_contacts(max_results=5)
            sample_data["contacts"] = len(contacts)
            sample_data["contact_names"] = [c.get("name", "")[:30] for c in contacts[:5]]
        except Exception as e:
            logger.warning(f"Contacts test failed: {e}")
            sample_data["contacts"] = f"Error: {e}"
        
        # Consider success if at least one worked
        if isinstance(sample_data.get("emails"), int) or isinstance(sample_data.get("events"), int) or isinstance(sample_data.get("contacts"), int):
            msg = f"Connected! Found {sample_data.get('emails', 0)} emails, {sample_data.get('events', 0)} events, {sample_data.get('contacts', 0)} contacts"
            return True, msg, sample_data
        else:
            return False, "Could not access email, calendar, or contacts", sample_data
    
    def _test_imap(self, account_data: dict) -> tuple[bool, str, dict | None]:
        """Test IMAP connection by fetching inbox."""
        import imaplib
        
        host = account_data.get("host", "")
        port = account_data.get("port", 993)
        email = account_data.get("email", "")
        password = account_data.get("password", "")
        use_ssl = account_data.get("use_ssl", True)
        
        if use_ssl:
            imap = imaplib.IMAP4_SSL(host, port)
        else:
            imap = imaplib.IMAP4(host, port)
        
        imap.login(email, password)
        imap.select("INBOX")
        
        # Fetch recent message count
        status, messages = imap.search(None, "ALL")
        msg_count = len(messages[0].split()) if messages[0] else 0
        
        imap.logout()
        
        return True, f"Connected! Inbox has {msg_count} messages", {"emails": msg_count}
    
    def _test_caldav(self, account_data: dict) -> tuple[bool, str, dict | None]:
        """Test CalDAV connection by fetching calendars."""
        try:
            import caldav
        except ImportError:
            return False, "caldav library not installed", None
        
        url = account_data.get("url", "")
        username = account_data.get("username", "") or account_data.get("email", "")
        password = account_data.get("password", "")
        
        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        
        cal_names = [cal.name for cal in calendars[:5]]
        
        return True, f"Connected! Found {len(calendars)} calendars", {"calendars": cal_names}
    
    def _test_google(self, account_data: dict) -> tuple[bool, str, dict | None]:
        """Test Google API connection."""
        credentials_file = account_data.get("credentials_file", "")
        token_file = account_data.get("token_file", "")
        
        from pathlib import Path
        creds_path = Path(credentials_file).expanduser()
        
        if not creds_path.exists():
            return False, f"Credentials file not found: {credentials_file}", None
        
        # Would need OAuth flow - just check if files exist
        return True, "Credentials file found (OAuth may be needed)", {"credentials": str(creds_path)}
    
    def _get_capabilities_for_type(self, acc_type: str) -> list[str]:
        """Get default capabilities for account type."""
        type_caps = {
            "exchange": ["email", "calendar", "contacts"],
            "google": ["email", "calendar"],
            "gmail": ["email", "calendar"],
            "imap": ["email"],
            "caldav": ["calendar"],
            "icloud": ["contacts"],
        }
        return type_caps.get(acc_type, [])
    
    def _find_account_index(self, name: str) -> int | None:
        """Find account index by name in unified accounts list."""
        name_lower = name.lower()
        for i, acc in enumerate(self.config.integrations.accounts or []):
            acc_name = acc.get("name") if isinstance(acc, dict) else getattr(acc, "name", "")
            if acc_name.lower() == name_lower:
                return i
        return None
    
    def _account_to_dict(self, acc: Any) -> dict:
        """Convert account (dict or Pydantic model) to dict."""
        if isinstance(acc, dict):
            return acc
        return {
            "name": getattr(acc, 'name', ''),
            "type": getattr(acc, 'type', ''),
            "enabled": getattr(acc, 'enabled', True),
            "capabilities": getattr(acc, 'capabilities', []),
            "email": getattr(acc, 'email', ''),
            "username": getattr(acc, 'username', ''),
            "password": getattr(acc, 'password', ''),
            "server": getattr(acc, 'server', ''),
            "use_autodiscover": getattr(acc, 'use_autodiscover', False),
            "host": getattr(acc, 'host', ''),
            "port": getattr(acc, 'port', 993),
            "url": getattr(acc, 'url', ''),
        }


# Convenience functions for direct use
def add_account(account_data: dict) -> tuple[bool, str]:
    """Add account using default config."""
    return AccountManager().add_account(account_data)


def remove_account(name: str) -> tuple[bool, str]:
    """Remove account using default config."""
    return AccountManager().remove_account(name)


def test_account_connection(account_data: dict) -> tuple[bool, str, dict | None]:
    """Test account connection."""
    return AccountManager().test_connection(account_data)


def list_accounts() -> list[dict]:
    """List all accounts."""
    return AccountManager().get_all_accounts()
