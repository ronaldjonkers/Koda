"""Unified email tool that works with email_accounts configuration."""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import Tool


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class GoogleWorkspaceEmailAdapter:
    """Adapter to make GoogleWorkspaceClient compatible with email tool interface."""
    
    def __init__(self, client):
        self.client = client
    
    def get_inbox(self, max_results: int = 10):
        """Get inbox messages."""
        return self.client.list_emails(max_results=max_results)
    
    def get_unread(self, max_results: int = 50):
        """Get unread messages."""
        return self.client.list_emails(query="is:unread", max_results=max_results)
    
    def search(self, query: str, max_results: int = 20):
        """Search emails."""
        return self.client.list_emails(query=query, max_results=max_results)
    
    def get_message(self, message_id: str):
        """Get a specific message."""
        return self.client.get_email(message_id)
    
    def send_email(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None):
        """Send an email."""
        return self.client.send_email(to=to, subject=subject, body=body, cc=cc, bcc=bcc)


class UnifiedEmailTool(Tool):
    """Tool for accessing configured email accounts."""
    
    name = "email"
    description = """Access your configured email accounts to read, search, and summarize emails.

Actions:
- list_accounts: List all configured email accounts
- inbox: Get recent inbox messages (use max_results to control how many)
- today: Get emails received today
- recent: Get emails from the last few hours (use hours parameter)
- unread: Get unread messages
- search: Search emails by subject, sender, or content
- read: Read full email content by ID (for summarizing)
- send: Send an email (requires to, subject, body)

Parameters:
- account_name: Name of the email account (optional if only one account)
- max_results: Number of emails to return (default: 10)
- hours: For 'recent' action - how many hours back to look (default: 4)
- query: Search query for 'search' action

Examples:
- Get last 5 emails: {"action": "inbox", "max_results": 5}
- Get today's emails: {"action": "today"}
- Get emails from last 2 hours: {"action": "recent", "hours": 2}
- Search for invoices: {"action": "search", "query": "invoice"}
- Read specific email: {"action": "read", "message_id": "abc123"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_accounts", "inbox", "today", "recent", "unread", "search", "read", "send"],
                "description": "Action to perform"
            },
            "to": {
                "type": "string",
                "description": "Recipient email address (for send action)"
            },
            "subject": {
                "type": "string",
                "description": "Email subject (for send action)"
            },
            "body": {
                "type": "string",
                "description": "Email body content (for send action)"
            },
            "cc": {
                "type": "string",
                "description": "CC recipients, comma-separated (for send action)"
            },
            "account_name": {
                "type": "string",
                "description": "Name of the email account to use (optional if only one account)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return (default: 10)",
                "default": 10
            },
            "hours": {
                "type": "integer",
                "description": "For 'recent' action: how many hours back to look (default: 4)",
                "default": 4
            },
            "query": {
                "type": "string",
                "description": "Search query - searches subject, sender, and body"
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (for read action)"
            },
        },
        "required": ["action"]
    }
    
    def __init__(self, config: Any = None):
        self.config = config
        self._clients = {}
        self._google_workspace_client = None
        self._google_workspace_available = self._check_google_workspace()
    
    def _check_google_workspace(self) -> bool:
        """Check if Google Workspace is configured and authorized."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            if status.get("authorized"):
                self._google_workspace_client = client
                return True
        except Exception:
            pass
        return False
    
    def _get_accounts(self) -> list[dict]:
        """Get all accounts with email capability from unified accounts."""
        accounts = []
        
        # Auto-add Google Workspace if connected
        if self._google_workspace_available:
            accounts.append({
                "name": "Gmail",
                "type": "google",
                "enabled": True,
                "auto_added": True
            })
        
        if not self.config or not hasattr(self.config, 'integrations'):
            return accounts
        
        integrations = self.config.integrations
        
        # Use new unified method if available
        if hasattr(integrations, 'get_all_email_accounts'):
            raw_accounts = integrations.get_all_email_accounts()
        else:
            # Fallback: check multiple sources
            raw_accounts = []
            # Unified accounts with email capability
            for acc in getattr(integrations, 'accounts', []) or []:
                caps = _get_attr(acc, 'capabilities', [])
                if 'email' in caps or _get_attr(acc, 'type', '') in ('exchange', 'google', 'imap'):
                    raw_accounts.append(acc)
            # Legacy email_accounts
            for acc in getattr(integrations, 'email_accounts', []) or []:
                raw_accounts.append(acc)
        
        for acc in raw_accounts:
            if isinstance(acc, dict):
                accounts.append(acc)
            else:
                # Convert Pydantic model to dict
                accounts.append({
                    "name": getattr(acc, 'name', ''),
                    "type": getattr(acc, 'type', ''),
                    "enabled": getattr(acc, 'enabled', True),
                    "capabilities": getattr(acc, 'capabilities', []),
                    "email": getattr(acc, 'email', ''),
                    "username": getattr(acc, 'username', ''),
                    "password": getattr(acc, 'password', ''),
                    "server": getattr(acc, 'server', ''),
                    "host": getattr(acc, 'host', ''),
                    "port": getattr(acc, 'port', 993),
                    "use_ssl": getattr(acc, 'use_ssl', True),
                    "use_autodiscover": getattr(acc, 'use_autodiscover', False),
                })
        
        # Deduplicate by name
        seen = set()
        unique_accounts = []
        for acc in accounts:
            name = acc.get('name', '')
            if name and name not in seen:
                seen.add(name)
                unique_accounts.append(acc)
        
        return unique_accounts
    
    def _find_account(self, account_name: str) -> dict | None:
        """Find account by name (case-insensitive)."""
        accounts = self._get_accounts()
        name_lower = account_name.lower()
        
        for acc in accounts:
            if acc.get("name", "").lower() == name_lower and acc.get("enabled", True):
                return acc
        return None
    
    def _get_client(self, account_name: str):
        """Get or create email client for the specified account."""
        if account_name in self._clients:
            return self._clients[account_name]
        
        account = self._find_account(account_name)
        if not account:
            raise ValueError(f"Email account '{account_name}' not found or not enabled")
        
        acc_type = account.get("type", "")
        
        if acc_type == "google":
            # Use Google Workspace client for Gmail
            if self._google_workspace_client:
                self._clients[account_name] = GoogleWorkspaceEmailAdapter(self._google_workspace_client)
            else:
                raise ValueError("Google Workspace not connected. Use dashboard to authenticate.")
        elif acc_type == "imap":
            from koda.integrations.imap_client import IMAPClient
            self._clients[account_name] = IMAPClient(
                host=account.get("host", ""),
                port=account.get("port", 993),
                username=account.get("email", ""),
                password=account.get("password", ""),
                use_ssl=account.get("use_ssl", True)
            )
        elif acc_type == "exchange":
            from koda.integrations.exchange_client import ExchangeClient
            self._clients[account_name] = ExchangeClient(
                email=account.get("email", ""),
                password=account.get("password", ""),
                server=account.get("server", ""),
                username=account.get("username", "") or account.get("email", ""),
                use_autodiscover=account.get("use_autodiscover", True)
            )
        else:
            raise ValueError(f"Unsupported email type: {acc_type}")
        
        return self._clients[account_name]
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action")
        
        try:
            if action == "list_accounts":
                return self._list_accounts()
            
            # For other actions, we need an account name
            account_name = kwargs.get("account_name")
            if not account_name:
                # Try to use the first available account
                accounts = self._get_accounts()
                for acc in accounts:
                    if acc.get("enabled", True):
                        account_name = acc.get("name")
                        break
                
                if not account_name:
                    return "Error: No account_name specified and no default account available. Use list_accounts first."
            
            client = self._get_client(account_name)
            
            if action == "inbox":
                return self._get_inbox(client, kwargs.get("max_results", 10))
            
            elif action == "today":
                return self._get_today(client, kwargs.get("max_results", 50))
            
            elif action == "recent":
                hours = kwargs.get("hours", 4)
                return self._get_recent(client, hours, kwargs.get("max_results", 50))
            
            elif action == "unread":
                return self._get_unread(client)
            
            elif action == "search":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: query is required for search action"
                return self._search(client, query, kwargs.get("max_results", 20))
            
            elif action == "read":
                message_id = kwargs.get("message_id")
                if not message_id:
                    return "Error: message_id required for read action"
                return self._read_message(client, message_id)
            
            elif action == "send":
                to = kwargs.get("to")
                subject = kwargs.get("subject")
                body = kwargs.get("body")
                if not to or not subject or not body:
                    return "Error: to, subject, and body are required for send action"
                return self._send_email(client, to, subject, body, kwargs.get("cc"))
            
            else:
                return f"Unknown action: {action}"
        
        except ConnectionError as e:
            # Connection errors - show friendly message to user, full error on server
            import traceback
            logger.error(f"Email connection error for account '{account_name}':")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"""❌ **Kan geen verbinding maken met email server**

Account: {account_name}

Mogelijke oorzaken:
• Onjuiste inloggegevens (email/wachtwoord)
• Server is niet bereikbaar
• Autodiscover werkt niet voor dit account

Probeer:
1. Controleer of je wachtwoord correct is
2. Gebruik /removemail {account_name} en /addmail om opnieuw in te stellen
3. Probeer handmatig een server op te geven (niet autodiscover)

_Technische fout is gelogd op de server._"""
        
        except Exception as e:
            # Other errors - log full details on server
            import traceback
            logger.error(f"Email tool error for action '{action}':")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"❌ **Email fout:** {str(e)}\n\n_Details zijn gelogd op de server._"
    
    def _list_accounts(self) -> str:
        """List all configured email accounts."""
        accounts = self._get_accounts()
        
        if not accounts:
            return "No email accounts configured. Use /addmail via WhatsApp to add one."
        
        output = ["**📧 Available Email Accounts:**\n"]
        for acc in accounts:
            if acc.get("enabled", True):
                status = "✅"
                name = acc.get("name", "Unknown")
                acc_type = acc.get("type", "unknown")
                email = acc.get("email", "")
                output.append(f"{status} **{name}** ({acc_type})")
                if email:
                    output.append(f"   📧 {email}")
        
        if len(output) == 1:
            return "No enabled email accounts found."
        
        output.append("\n_Use account_name parameter with other actions._")
        return "\n".join(output)
    
    def _get_inbox(self, client, max_results: int) -> str:
        """Get inbox messages."""
        # ExchangeClient uses list_emails(), others might use get_inbox()
        if hasattr(client, 'list_emails'):
            messages = client.list_emails(max_results=max_results)
        else:
            messages = client.get_inbox(max_results=max_results)
        return self._format_messages(messages, "Inbox")
    
    def _get_unread(self, client) -> str:
        """Get unread messages."""
        if hasattr(client, 'list_emails'):
            messages = client.list_emails(unread_only=True)
            count = client.get_unread_count() if hasattr(client, 'get_unread_count') else len(messages)
            return f"**Unread: {count}**\n\n" + self._format_messages(messages, "Unread messages")
        else:
            messages = client.get_unread()
            return self._format_messages(messages, "Unread messages")
    
    def _get_today(self, client, max_results: int) -> str:
        """Get emails received today."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if hasattr(client, 'list_emails_since'):
            messages = client.list_emails_since(since=today, max_results=max_results)
        elif hasattr(client, 'list_emails'):
            # Get more emails and filter by date
            all_messages = client.list_emails(max_results=100)
            messages = []
            for m in all_messages:
                date_str = m.get('date', '')
                if date_str:
                    try:
                        # Parse ISO date
                        msg_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        if msg_date.replace(tzinfo=None) >= today:
                            messages.append(m)
                    except (ValueError, TypeError):
                        pass
            messages = messages[:max_results]
        else:
            messages = []
        
        today_str = today.strftime("%A %d %B")
        return self._format_messages(messages, f"Emails from today ({today_str})")
    
    def _get_recent(self, client, hours: int, max_results: int) -> str:
        """Get emails from the last N hours."""
        since = datetime.now() - timedelta(hours=hours)
        
        if hasattr(client, 'list_emails_since'):
            messages = client.list_emails_since(since=since, max_results=max_results)
        elif hasattr(client, 'list_emails'):
            # Get more emails and filter by date
            all_messages = client.list_emails(max_results=100)
            messages = []
            for m in all_messages:
                date_str = m.get('date', '')
                if date_str:
                    try:
                        msg_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        if msg_date.replace(tzinfo=None) >= since:
                            messages.append(m)
                    except (ValueError, TypeError):
                        pass
            messages = messages[:max_results]
        else:
            messages = []
        
        return self._format_messages(messages, f"Emails from last {hours} hours")
    
    def _search(self, client, query: str, max_results: int) -> str:
        """Search emails."""
        if hasattr(client, 'search_emails'):
            messages = client.search_emails(query, max_results=max_results)
        elif hasattr(client, 'search'):
            messages = client.search(query, max_results=max_results)
        else:
            # Fallback: filter inbox results
            if hasattr(client, 'list_emails'):
                all_messages = client.list_emails(max_results=100)
            else:
                all_messages = client.get_inbox(max_results=100)
            
            query_lower = query.lower()
            messages = [
                m for m in all_messages
                if query_lower in m.get("subject", "").lower()
                or query_lower in m.get("from", "").lower()
                or query_lower in m.get("body_preview", "").lower()
            ][:max_results]
        
        return self._format_messages(messages, f"Search results for '{query}'")
    
    def _send_email(self, client, to: str, subject: str, body: str, cc: str = None) -> str:
        """Send an email."""
        try:
            if hasattr(client, 'send_email'):
                result = client.send_email(to=to, subject=subject, body=body, cc=cc)
                if result:
                    return f"✅ **Email verzonden**\n\n📧 Naar: {to}\n📝 Onderwerp: {subject}"
                else:
                    return "❌ Kon email niet verzenden"
            else:
                return "❌ Dit account ondersteunt geen emails verzenden"
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return f"❌ Fout bij verzenden: {e}"
    
    def _read_message(self, client, message_id: str) -> str:
        """Read full message content."""
        if hasattr(client, 'get_email'):
            msg = client.get_email(message_id)
        else:
            msg = client.get_message(message_id)
        
        if isinstance(msg, str):
            return msg
        
        output = []
        output.append(f"**Subject:** {msg.get('subject', '(No subject)')}")
        output.append(f"**From:** {msg.get('from', 'Unknown')}")
        output.append(f"**To:** {', '.join(msg.get('to', []))}")
        output.append(f"**Date:** {msg.get('date', 'Unknown')}")
        output.append(f"**ID:** {msg.get('id', 'N/A')}")
        output.append("")
        output.append("---")
        output.append("")
        output.append(msg.get('body', '(No content)'))
        
        return "\n".join(output)
    
    def _format_messages(self, messages: list, title: str = "Messages") -> str:
        """Format email messages for display."""
        if not messages:
            return f"{title}: No messages found."
        
        output = [f"**{title}** ({len(messages)} messages):\n"]
        
        for msg in messages:
            unread = " 🔵" if not msg.get("is_read", True) else ""
            msg_id = msg.get('id', '')
            short_id = msg_id[:12] + "..." if len(msg_id) > 12 else msg_id
            
            output.append(f"• **{msg.get('subject', '(No subject)')}**{unread}")
            output.append(f"  From: {msg.get('from', 'Unknown')}")
            output.append(f"  Date: {msg.get('date', 'Unknown')}")
            output.append(f"  ID: `{short_id}`")
            
            preview = msg.get('body_preview') or msg.get('snippet', '')
            if preview:
                preview = preview[:150].replace('\n', ' ')
                output.append(f"  Preview: {preview}...")
            output.append("")
        
        return "\n".join(output)
