"""Unified email tool that works with email_accounts configuration."""

from typing import Any
from koda.core.tools.base import Tool


class UnifiedEmailTool(Tool):
    """Tool for accessing configured email accounts."""
    
    name = "email"
    description = """Access your configured email accounts to read and search emails.
    
Actions:
- list_accounts: List all configured email accounts
- inbox: Get recent inbox messages from an account
- unread: Get unread messages from an account
- search: Search emails in an account
- read: Read full email content by ID

Examples:
- List accounts: {"action": "list_accounts"}
- Get inbox: {"action": "inbox", "account_name": "MRSN", "max_results": 10}
- Get unread: {"action": "unread", "account_name": "MRSN"}
- Search: {"action": "search", "account_name": "MRSN", "query": "subject:invoice"}
- Read email: {"action": "read", "account_name": "MRSN", "message_id": "123"}
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
                "description": "Name of the email account to use"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return",
                "default": 10
            },
            "query": {
                "type": "string",
                "description": "Search query (for search action)"
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
    
    def _get_client(self, account_name: str):
        """Get or create email client for the specified account."""
        if account_name not in self._clients:
            # Find account in config
            account = None
            if self.config and hasattr(self.config, 'integrations'):
                for acc in self.config.integrations.email_accounts:
                    if acc.name == account_name and acc.enabled:
                        account = acc
                        break
            
            if not account:
                raise ValueError(f"Email account '{account_name}' not found or not enabled")
            
            # Create appropriate client based on type
            if account.type == "imap":
                from koda.integrations.imap_client import IMAPClient
                self._clients[account_name] = IMAPClient(
                    host=account.host,
                    port=account.port,
                    username=account.email,
                    password=account.password,
                    use_ssl=account.use_ssl
                )
            elif account.type == "exchange":
                from koda.integrations.exchange_client import ExchangeClient
                self._clients[account_name] = ExchangeClient(
                    email=account.email,
                    password=account.password,
                    server=account.server,
                    username=account.username
                )
            else:
                raise ValueError(f"Unsupported email type: {account.type}")
        
        return self._clients[account_name]
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action")
        
        if action == "list_accounts":
            # List all configured email accounts
            if not self.config or not hasattr(self.config, 'integrations'):
                return "No configuration available"
            
            accounts = []
            for acc in self.config.integrations.email_accounts:
                if acc.enabled:
                    accounts.append(f"- {acc.name} ({acc.type}): {acc.email}")
            
            if accounts:
                return f"Available email accounts:\n" + "\n".join(accounts)
            else:
                return "No email accounts configured"
        
        # For other actions, we need an account name
        account_name = kwargs.get("account_name")
        if not account_name:
            # Try to use the first available account
            if self.config and hasattr(self.config, 'integrations'):
                for acc in self.config.integrations.email_accounts:
                    if acc.enabled:
                        account_name = acc.name
                        break
            
            if not account_name:
                return "Error: No account_name specified and no default account available"
        
        try:
            client = self._get_client(account_name)
        except ValueError as e:
            return f"Error: {e}"
        
        if action == "inbox":
            max_results = kwargs.get("max_results", 10)
            messages = client.get_inbox(max_results=max_results)
            return self._format_messages(messages)
        
        elif action == "unread":
            messages = client.get_unread()
            return self._format_messages(messages)
        
        elif action == "search":
            query = kwargs.get("query", "")
            messages = client.search(query)
            return self._format_messages(messages)
        
        elif action == "read":
            message_id = kwargs.get("message_id")
            if not message_id:
                return "Error: message_id required for read action"
            
            content = client.get_message(message_id)
            return content
        
        else:
            return f"Unknown action: {action}"
    
    def _format_messages(self, messages: list) -> str:
        """Format email messages for display."""
        if not messages:
            return "No messages found"
        
        output = []
        for msg in messages:
            output.append(f"ID: {msg.get('id', 'unknown')}")
            output.append(f"From: {msg.get('from', 'unknown')}")
            output.append(f"Subject: {msg.get('subject', 'No subject')}")
            output.append(f"Date: {msg.get('date', 'unknown')}")
            if msg.get('snippet'):
                output.append(f"Preview: {msg['snippet'][:100]}...")
            output.append("---")
        
        return "\n".join(output)
