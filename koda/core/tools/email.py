"""Email tools for Gmail and Exchange."""

from typing import Any

from koda.core.tools.base import Tool


class GmailTool(Tool):
    """Tool for Gmail operations."""
    
    name = "gmail"
    description = """Access Gmail to read, search, and send emails.
    
Actions:
- inbox: Get recent inbox messages
- unread: Get unread messages
- search: Search emails with Gmail query
- read: Read full email content by ID
- send: Send a new email
- reply: Reply to an email

Examples:
- Get inbox: {"action": "inbox", "max_results": 10}
- Get unread: {"action": "unread"}
- Search: {"action": "search", "query": "from:example@gmail.com"}
- Read email: {"action": "read", "message_id": "abc123"}
- Send email: {"action": "send", "to": "user@example.com", "subject": "Hello", "body": "Message content"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["inbox", "unread", "search", "read", "send", "reply"],
                "description": "Action to perform"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return"
            },
            "query": {
                "type": "string",
                "description": "Gmail search query (for search action)"
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (for read/reply actions)"
            },
            "to": {
                "type": "string",
                "description": "Recipient email (for send action)"
            },
            "subject": {
                "type": "string",
                "description": "Email subject (for send action)"
            },
            "body": {
                "type": "string",
                "description": "Email body (for send/reply actions)"
            },
        },
        "required": ["action"]
    }
    
    def __init__(self, credentials_file: str | None = None, token_file: str | None = None):
        self.credentials_file = credentials_file or "~/.koda/google_credentials.json"
        self.token_file = token_file or "~/.koda/google_token_gmail.json"
        self._client = None
    
    def _get_client(self):
        if not self._client:
            from koda.integrations.google_gmail import GmailClient
            self._client = GmailClient(
                credentials_file=self.credentials_file,
                token_file=self.token_file
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "inbox")
        max_results = kwargs.get("max_results", 10)
        
        try:
            client = self._get_client()
            
            if action == "inbox":
                messages = client.get_inbox(max_results=max_results)
                return self._format_messages(messages, "Inbox")
            
            elif action == "unread":
                messages = client.get_unread(max_results=max_results)
                count = client.get_unread_count()
                return f"Unread count: {count}\n\n" + self._format_messages(messages, "Unread")
            
            elif action == "search":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: Search query required"
                messages = client.list_messages(query=query, max_results=max_results)
                return self._format_messages(messages, f"Search: {query}")
            
            elif action == "read":
                message_id = kwargs.get("message_id")
                if not message_id:
                    return "Error: Message ID required"
                msg = client.get_message(message_id)
                return self._format_full_message(msg)
            
            elif action == "send":
                to = kwargs.get("to")
                subject = kwargs.get("subject")
                body = kwargs.get("body")
                
                if not all([to, subject, body]):
                    return "Error: Missing: to, subject, or body"
                
                result = client.send_message(to=to, subject=subject, body=body)
                return f"Email sent to {to}: {subject}"
            
            elif action == "reply":
                message_id = kwargs.get("message_id")
                body = kwargs.get("body")
                
                if not message_id or not body:
                    return "Error: Missing: message_id or body"
                
                # Get original to find recipient
                original = client.get_message(message_id)
                to = original.get("from", "").split("<")[-1].rstrip(">")
                subject = f"Re: {original.get('subject', '')}"
                
                result = client.send_message(
                    to=to,
                    subject=subject,
                    body=body,
                    reply_to_message_id=message_id
                )
                return f"Reply sent to {to}"
            
            else:
                return f"Error: Unknown action: {action}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _format_messages(self, messages: list, title: str) -> str:
        if not messages:
            return f"{title}: No messages found."
        
        output = f"{title} ({len(messages)}):\n\n"
        for m in messages:
            output += f"• [{m['id'][:8]}...] {m['subject']}\n"
            output += f"  From: {m['from']}\n"
            output += f"  Date: {m['date']}\n"
            output += f"  Preview: {m['snippet'][:100]}...\n\n"
        
        return output
    
    def _format_full_message(self, msg: dict) -> str:
        output = f"Subject: {msg['subject']}\n"
        output += f"From: {msg['from']}\n"
        output += f"To: {msg['to']}\n"
        output += f"Date: {msg['date']}\n"
        output += f"ID: {msg['id']}\n"
        output += f"\n{'='*50}\n\n"
        output += msg.get('body', '(No body)')
        return output


class ExchangeEmailTool(Tool):
    """Tool for Exchange/Outlook email operations."""
    
    name = "exchange_email"
    description = """Access Exchange/Outlook email to read, search, and send emails.
    
Actions:
- inbox: Get recent inbox messages
- unread: Get unread messages
- read: Read full email content by ID
- send: Send a new email
- reply: Reply to an email

Examples:
- Get inbox: {"action": "inbox", "max_results": 10}
- Get unread: {"action": "unread"}
- Read email: {"action": "read", "message_id": "abc123"}
- Send email: {"action": "send", "to": ["user@example.com"], "subject": "Hello", "body": "Content"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["inbox", "unread", "read", "send", "reply"],
                "description": "Action to perform"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages"
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (for read/reply)"
            },
            "to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recipient emails (for send)"
            },
            "subject": {
                "type": "string",
                "description": "Email subject (for send)"
            },
            "body": {
                "type": "string",
                "description": "Email body (for send/reply)"
            },
        },
        "required": ["action"]
    }
    
    def __init__(self, email: str = "", password: str = "", server: str | None = None):
        self.email = email
        self.password = password
        self.server = server
        self._client = None
    
    def _get_client(self):
        if not self._client:
            from koda.integrations.exchange_client import ExchangeClient
            self._client = ExchangeClient(
                email=self.email,
                password=self.password,
                server=self.server
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "inbox")
        max_results = kwargs.get("max_results", 10)
        
        try:
            client = self._get_client()
            
            if action == "inbox":
                messages = client.list_emails(max_results=max_results)
                return self._format_messages(messages, "Inbox")
            
            elif action == "unread":
                messages = client.list_emails(max_results=max_results, unread_only=True)
                count = client.get_unread_count()
                return f"Unread count: {count}\n\n" + self._format_messages(messages, "Unread")
            
            elif action == "read":
                message_id = kwargs.get("message_id")
                if not message_id:
                    return "Error: Message ID required"
                msg = client.get_email(message_id)
                return self._format_full_message(msg)
            
            elif action == "send":
                to = kwargs.get("to", [])
                subject = kwargs.get("subject")
                body = kwargs.get("body")
                
                if not all([to, subject, body]):
                    return "Error: Missing: to, subject, or body"
                
                if isinstance(to, str):
                    to = [to]
                
                result = client.send_email(to=to, subject=subject, body=body)
                return f"Email sent to {', '.join(to)}: {subject}"
            
            elif action == "reply":
                message_id = kwargs.get("message_id")
                body = kwargs.get("body")
                
                if not message_id or not body:
                    return "Error: Missing: message_id or body"
                
                result = client.reply_to_email(message_id, body)
                return f"Reply sent: {result}"
            
            else:
                return f"Error: Unknown action: {action}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _format_messages(self, messages: list, title: str) -> str:
        if not messages:
            return f"{title}: No messages found."
        
        output = f"{title} ({len(messages)}):\n\n"
        for m in messages:
            unread = " [UNREAD]" if not m.get("is_read") else ""
            output += f"• [{m['id'][:8] if m.get('id') else 'N/A'}...]{unread} {m['subject']}\n"
            output += f"  From: {m['from']}\n"
            output += f"  Date: {m['date']}\n"
            if m.get("body_preview"):
                output += f"  Preview: {m['body_preview'][:100]}...\n"
            output += "\n"
        
        return output
    
    def _format_full_message(self, msg: dict) -> str:
        output = f"Subject: {msg['subject']}\n"
        output += f"From: {msg['from']}\n"
        output += f"To: {', '.join(msg.get('to', []))}\n"
        output += f"Date: {msg['date']}\n"
        output += f"ID: {msg['id']}\n"
        output += f"\n{'='*50}\n\n"
        output += msg.get('body', '(No body)')
        return output
