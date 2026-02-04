"""Tool for listing available accounts (email and calendar)."""

from typing import Any
from koda.core.tools.base import Tool


class AccountsTool(Tool):
    """Tool for the LLM to discover available accounts."""
    
    name = "accounts"
    description = """List all available email and calendar accounts.
    
Use this tool to discover which accounts are configured before using email or calendar tools.
This helps you know exactly which accounts you can access.

Actions:
- list: List all accounts (email and calendar)
- calendars: List only calendar accounts
- emails: List only email accounts

Examples:
- List all: {"action": "list"}
- List calendars: {"action": "calendars"}
- List emails: {"action": "emails"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "calendars", "emails"],
                "description": "What to list",
                "default": "list"
            }
        },
        "required": []
    }
    
    def __init__(self, config: Any = None):
        """
        Initialize with the app config.
        
        Args:
            config: The KodaConfig object with integrations
        """
        self.config = config
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        
        if not self.config:
            return "No configuration available. Cannot list accounts."
        
        integrations = getattr(self.config, 'integrations', None)
        if not integrations:
            return "No integrations configured."
        
        output = []
        
        if action in ("list", "calendars"):
            output.append("**📅 Calendar Accounts:**\n")
            calendars = self._get_calendar_accounts(integrations)
            if calendars:
                for cal in calendars:
                    status = "✅" if cal.get("enabled", True) else "❌"
                    output.append(f"{status} **{cal['name']}** ({cal['type']})")
                    if cal.get("email"):
                        output.append(f"   📧 {cal['email']}")
            else:
                output.append("_No calendar accounts configured_")
            output.append("")
        
        if action in ("list", "emails"):
            output.append("**📧 Email Accounts:**\n")
            emails = self._get_email_accounts(integrations)
            if emails:
                for email in emails:
                    status = "✅" if email.get("enabled", True) else "❌"
                    output.append(f"{status} **{email['name']}** ({email['type']})")
                    if email.get("email"):
                        output.append(f"   📧 {email['email']}")
            else:
                output.append("_No email accounts configured_")
        
        if not output:
            return "No accounts found."
        
        return "\n".join(output)
    
    def _get_calendar_accounts(self, integrations) -> list[dict]:
        """Get all calendar accounts from config."""
        accounts = []
        
        # New style: calendar_accounts list
        cal_accounts = getattr(integrations, 'calendar_accounts', []) or []
        for acc in cal_accounts:
            if isinstance(acc, dict):
                accounts.append(acc)
            else:
                # Pydantic model
                accounts.append({
                    "name": getattr(acc, 'name', 'Unknown'),
                    "type": getattr(acc, 'type', 'unknown'),
                    "enabled": getattr(acc, 'enabled', True),
                    "email": getattr(acc, 'email', ''),
                })
        
        # Legacy: check individual configs
        google = getattr(integrations, 'google', None)
        if google and getattr(google, 'enabled', False):
            accounts.append({
                "name": "Google",
                "type": "google",
                "enabled": True,
            })
        
        exchange = getattr(integrations, 'exchange', None)
        if exchange and getattr(exchange, 'enabled', False):
            accounts.append({
                "name": "Exchange",
                "type": "exchange",
                "enabled": True,
                "email": getattr(exchange, 'email', ''),
            })
        
        caldav = getattr(integrations, 'caldav', None)
        if caldav and getattr(caldav, 'enabled', False):
            accounts.append({
                "name": "CalDAV",
                "type": "caldav",
                "enabled": True,
            })
        
        return accounts
    
    def _get_email_accounts(self, integrations) -> list[dict]:
        """Get all email accounts from config."""
        accounts = []
        
        # New style: email_accounts list
        email_accounts = getattr(integrations, 'email_accounts', []) or []
        for acc in email_accounts:
            if isinstance(acc, dict):
                accounts.append(acc)
            else:
                # Pydantic model
                accounts.append({
                    "name": getattr(acc, 'name', 'Unknown'),
                    "type": getattr(acc, 'type', 'unknown'),
                    "enabled": getattr(acc, 'enabled', True),
                    "email": getattr(acc, 'email', ''),
                })
        
        # Legacy: check individual configs
        google = getattr(integrations, 'google', None)
        if google and getattr(google, 'enabled', False):
            accounts.append({
                "name": "Gmail",
                "type": "gmail",
                "enabled": True,
            })
        
        exchange = getattr(integrations, 'exchange', None)
        if exchange and getattr(exchange, 'enabled', False):
            accounts.append({
                "name": "Exchange",
                "type": "exchange",
                "enabled": True,
                "email": getattr(exchange, 'email', ''),
            })
        
        imap = getattr(integrations, 'imap', None)
        if imap and getattr(imap, 'enabled', False):
            accounts.append({
                "name": "IMAP",
                "type": "imap",
                "enabled": True,
            })
        
        return accounts
