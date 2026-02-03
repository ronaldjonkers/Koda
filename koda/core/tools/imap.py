"""IMAP email tool for the agent."""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class IMAPTool(BaseTool):
    """
    Tool for reading emails via IMAP.
    
    Works with any IMAP-compatible mail server.
    """
    
    name = "imap_email"
    description = """Read emails from any IMAP mail server. Use this to:
- View recent emails
- Search for specific emails
- List mail folders
- Check for unread messages

Actions:
- list_messages: Get recent emails from a folder
- search: Search emails by query
- list_folders: Show available mail folders
- get_unread: Get unread message count"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_messages", "search", "list_folders", "get_unread"],
                "description": "The email operation to perform"
            },
            "folder": {
                "type": "string",
                "description": "Mail folder (default: INBOX)"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum messages to return (default: 10)"
            },
            "unread_only": {
                "type": "boolean",
                "description": "For list_messages: only show unread messages"
            },
            "query": {
                "type": "string",
                "description": "For search: search query"
            },
            "days": {
                "type": "integer",
                "description": "For list_messages: only messages from last N days"
            }
        },
        "required": ["action"]
    }
    
    def __init__(
        self,
        host: str = "",
        port: int = 993,
        username: str = "",
        password: str = "",
        use_ssl: bool = True,
        folder: str = "INBOX"
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.default_folder = folder
        self._client = None
    
    def _get_client(self):
        """Get or create IMAP client."""
        if not self._client:
            from koda.integrations.imap_client import IMAPClient
            self._client = IMAPClient(
                self.host,
                self.port,
                self.username,
                self.password,
                self.use_ssl,
                self.default_folder
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        """Execute an IMAP email operation."""
        if not self.host:
            return "IMAP not configured. Run 'koda config imap' to set up."
        
        action = kwargs.get("action")
        
        try:
            if action == "list_messages":
                return await self._list_messages(
                    folder=kwargs.get("folder"),
                    limit=kwargs.get("limit", 10),
                    unread_only=kwargs.get("unread_only", False),
                    days=kwargs.get("days")
                )
            
            elif action == "search":
                return await self._search(
                    query=kwargs.get("query", ""),
                    folder=kwargs.get("folder"),
                    limit=kwargs.get("limit", 10)
                )
            
            elif action == "list_folders":
                return await self._list_folders()
            
            elif action == "get_unread":
                return await self._get_unread(kwargs.get("folder"))
            
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            logger.error(f"IMAP operation failed: {e}")
            return f"Error: {str(e)}"
    
    async def _list_messages(
        self,
        folder: str | None,
        limit: int,
        unread_only: bool,
        days: int | None
    ) -> str:
        """List recent messages."""
        client = self._get_client()
        
        since = None
        if days:
            since = datetime.now() - timedelta(days=days)
        
        messages = client.get_messages(
            folder=folder,
            limit=limit,
            unread_only=unread_only,
            since=since
        )
        
        if not messages:
            folder_name = folder or self.default_folder
            return f"No messages found in {folder_name}."
        
        output = [f"**Recent Emails ({len(messages)}):**\n"]
        
        for msg in messages:
            date_str = msg.date.strftime("%Y-%m-%d %H:%M")
            sender = msg.sender_name or msg.sender
            
            output.append(f"- **{msg.subject}**")
            output.append(f"  From: {sender} ({msg.sender})")
            output.append(f"  Date: {date_str}")
            if msg.has_attachments:
                output.append(f"  📎 Attachments: {', '.join(msg.attachments)}")
            
            # Preview of body
            preview = msg.body_text[:150].replace("\n", " ").strip()
            if preview:
                output.append(f"  > {preview}...")
            output.append("")
        
        return "\n".join(output)
    
    async def _search(self, query: str, folder: str | None, limit: int) -> str:
        """Search messages."""
        if not query:
            return "Error: 'query' is required for search"
        
        client = self._get_client()
        messages = client.search_messages(query, folder, limit)
        
        if not messages:
            return f"No messages found matching: {query}"
        
        output = [f"**Search Results for '{query}' ({len(messages)}):**\n"]
        
        for msg in messages:
            date_str = msg.date.strftime("%Y-%m-%d")
            output.append(f"- **{msg.subject}**")
            output.append(f"  From: {msg.sender} | {date_str}")
            output.append("")
        
        return "\n".join(output)
    
    async def _list_folders(self) -> str:
        """List mail folders."""
        client = self._get_client()
        folders = client.list_folders()
        
        if not folders:
            return "No folders found."
        
        output = [f"**Mail Folders ({len(folders)}):**\n"]
        for folder in folders:
            output.append(f"- {folder}")
        
        return "\n".join(output)
    
    async def _get_unread(self, folder: str | None) -> str:
        """Get unread message count."""
        client = self._get_client()
        messages = client.get_messages(
            folder=folder,
            limit=100,
            unread_only=True
        )
        
        folder_name = folder or self.default_folder
        count = len(messages)
        
        if count == 0:
            return f"No unread messages in {folder_name}."
        else:
            return f"You have **{count}** unread messages in {folder_name}."
