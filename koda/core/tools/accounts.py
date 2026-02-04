"""Tool for listing available accounts (unified model with capabilities)."""

from typing import Any

from loguru import logger

from koda.core.tools.base import Tool


class AccountsTool(Tool):
    """Tool for the LLM to discover available accounts."""
    
    name = "accounts"
    description = """List all configured accounts with their capabilities.
    
Each account can have multiple capabilities: email, calendar, contacts.
For example, an Exchange account provides all three from a single configuration.

Actions:
- list: List all accounts with their capabilities
- calendars: List accounts with calendar capability
- emails: List accounts with email capability
- contacts: List accounts with contacts capability

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
                "enum": ["list", "calendars", "emails", "contacts"],
                "description": "What to list",
                "default": "list"
            }
        },
        "required": []
    }
    
    def __init__(self, config: Any = None):
        self.config = config
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        
        try:
            if not self.config:
                return "❌ No configuration available. Cannot list accounts."
            
            integrations = getattr(self.config, 'integrations', None)
            if not integrations:
                return "❌ No integrations configured."
            
            # Get all unified accounts
            if hasattr(integrations, 'get_all_accounts'):
                all_accounts = integrations.get_all_accounts()
            else:
                all_accounts = self._get_accounts_fallback(integrations)
            
            if not all_accounts:
                return "No accounts configured. Use /addmail or /addcalendar via WhatsApp to add one."
            
            # Filter by capability if needed
            if action == "calendars":
                accounts = [a for a in all_accounts if "calendar" in self._get_caps(a)]
                title = "📅 Calendar Accounts"
            elif action == "emails":
                accounts = [a for a in all_accounts if "email" in self._get_caps(a)]
                title = "📧 Email Accounts"
            elif action == "contacts":
                accounts = [a for a in all_accounts if "contacts" in self._get_caps(a)]
                title = "👥 Contacts Accounts"
            else:
                accounts = all_accounts
                title = "🔗 All Configured Accounts"
            
            if not accounts:
                return f"No {action} accounts configured."
            
            output = [f"**{title}:**\n"]
            
            for acc in accounts:
                name = self._get_attr(acc, 'name', 'Unknown')
                acc_type = self._get_attr(acc, 'type', 'unknown')
                enabled = self._get_attr(acc, 'enabled', True)
                email = self._get_attr(acc, 'email', '')
                caps = self._get_caps(acc)
                
                status = "✅" if enabled else "❌"
                caps_icons = []
                if "email" in caps:
                    caps_icons.append("📧")
                if "calendar" in caps:
                    caps_icons.append("📅")
                if "contacts" in caps:
                    caps_icons.append("👥")
                
                output.append(f"{status} **{name}** ({acc_type}) {' '.join(caps_icons)}")
                if email:
                    output.append(f"   └ {email}")
            
            return "\n".join(output)
        
        except Exception as e:
            logger.error(f"AccountsTool error: {e}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"❌ Error listing accounts: {e}"
    
    def _get_attr(self, obj: Any, key: str, default: Any = None) -> Any:
        """Get attribute from dict or object."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    def _get_caps(self, acc: Any) -> list[str]:
        """Get capabilities from account."""
        caps = self._get_attr(acc, 'capabilities', [])
        if not caps:
            # Infer from type
            acc_type = self._get_attr(acc, 'type', '')
            if acc_type == 'exchange':
                return ['email', 'calendar', 'contacts']
            elif acc_type in ('google', 'gmail'):
                return ['email', 'calendar']
            elif acc_type == 'imap':
                return ['email']
            elif acc_type == 'caldav':
                return ['calendar']
            elif acc_type == 'icloud':
                return ['contacts']
        return caps or []
    
    def _get_accounts_fallback(self, integrations) -> list[dict]:
        """Fallback: get accounts from legacy structure."""
        accounts = {}
        
        # Check for Google Workspace first (auto-detect if authorized)
        google_account = self._check_google_workspace()
        if google_account:
            accounts["Google Workspace"] = google_account
        
        # Unified accounts list
        for acc in getattr(integrations, 'accounts', []) or []:
            name = self._get_attr(acc, 'name', '')
            if name:
                accounts[name] = acc
        
        # Legacy calendar_accounts
        for acc in getattr(integrations, 'calendar_accounts', []) or []:
            name = self._get_attr(acc, 'name', '')
            if name and name not in accounts:
                accounts[name] = acc
        
        # Legacy email_accounts
        for acc in getattr(integrations, 'email_accounts', []) or []:
            name = self._get_attr(acc, 'name', '')
            if name and name not in accounts:
                accounts[name] = acc
        
        return list(accounts.values())
    
    def _check_google_workspace(self) -> dict | None:
        """Check if Google Workspace is configured and return as account."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            if status.get("authorized"):
                # Get user email from status
                user_email = status.get("email", "")
                return {
                    "name": "Google Workspace",
                    "type": "google",
                    "email": user_email,
                    "enabled": True,
                    "capabilities": ["email", "calendar"],
                    "auto_detected": True
                }
        except Exception as e:
            logger.debug(f"Google Workspace check: {e}")
        return None
