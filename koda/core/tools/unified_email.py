"""Unified email tool that works with email_accounts configuration."""

from typing import Any

from loguru import logger

from koda.core.tools.base import Tool


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class UnifiedEmailTool(Tool):
    """Tool for accessing configured email accounts."""
    
    name = "email"
    description = """Access your configured email accounts to read, search, and summarize emails.
    
IMPORTANT: First use 'list_accounts' to see available accounts, then specify account_name for other actions.

Actions:
- list_accounts: List all configured email accounts (use this first!)
- inbox: Get recent inbox messages from an account
- unread: Get unread messages from an account
- search: Search emails by subject, sender, or content
- read: Read full email content by ID (for summarizing)

Examples:
- List accounts: {"action": "list_accounts"}
- Get inbox: {"action": "inbox", "account_name": "goSettle Ronald", "max_results": 10}
- Get unread: {"action": "unread", "account_name": "goSettle Ronald"}
- Search: {"action": "search", "account_name": "goSettle Ronald", "query": "invoice"}
- Read email: {"action": "read", "account_name": "goSettle Ronald", "message_id": "abc123"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_accounts", "inbox", "unread", "search", "read"],
                "description": "Action to perform"
            },
            "account_name": {
                "type": "string",
                "description": "Name of the email account to use (from list_accounts)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return",
                "default": 10
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
    
    def _get_accounts(self) -> list[dict]:
        """Get all email accounts from config (handles both dicts and Pydantic models)."""
        if not self.config or not hasattr(self.config, 'integrations'):
            return []
        
        accounts = []
        raw_accounts = getattr(self.config.integrations, 'email_accounts', []) or []
        
        for acc in raw_accounts:
            if isinstance(acc, dict):
                accounts.append(acc)
            else:
                # Convert Pydantic model to dict
                accounts.append({
                    "name": getattr(acc, 'name', ''),
                    "type": getattr(acc, 'type', ''),
                    "enabled": getattr(acc, 'enabled', True),
                    "email": getattr(acc, 'email', ''),
                    "username": getattr(acc, 'username', ''),
                    "password": getattr(acc, 'password', ''),
                    "server": getattr(acc, 'server', ''),
                    "host": getattr(acc, 'host', ''),
                    "port": getattr(acc, 'port', 993),
                    "use_ssl": getattr(acc, 'use_ssl', True),
                    "use_autodiscover": getattr(acc, 'use_autodiscover', True),
                })
        
        return accounts
    
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
        
        if acc_type == "imap":
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
            
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            logger.error(f"Email tool error: {e}")
            return f"Error: {str(e)}"
    
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
