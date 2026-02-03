"""Gmail integration client."""

import base64
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class GmailClient:
    """Client for Gmail API operations."""
    
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    
    def __init__(
        self,
        credentials_file: str = "~/.koda/google_credentials.json",
        token_file: str = "~/.koda/google_token_gmail.json"
    ):
        self.credentials_file = Path(credentials_file).expanduser()
        self.token_file = Path(token_file).expanduser()
        self._service = None
    
    def _get_service(self):
        """Get or create the Gmail service."""
        if self._service:
            return self._service
        
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google API libraries not installed. Run: "
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        creds = None
        
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), self.SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self.credentials_file}\n"
                        "Download it from Google Cloud Console -> APIs & Services -> Credentials"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json())
        
        self._service = build("gmail", "v1", credentials=creds)
        return self._service
    
    def list_messages(
        self,
        query: str = "",
        max_results: int = 10,
        label_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        List email messages.
        
        Args:
            query: Gmail search query (e.g., "is:unread", "from:example@gmail.com")
            max_results: Maximum number of messages to return
            label_ids: Filter by label IDs (e.g., ["INBOX", "UNREAD"])
        
        Returns:
            List of message summaries
        """
        service = self._get_service()
        
        kwargs = {"userId": "me", "maxResults": max_results}
        if query:
            kwargs["q"] = query
        if label_ids:
            kwargs["labelIds"] = label_ids
        
        results = service.users().messages().list(**kwargs).execute()
        messages = results.get("messages", [])
        
        detailed_messages = []
        for msg in messages:
            full_msg = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]
            ).execute()
            
            headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
            
            detailed_messages.append({
                "id": msg["id"],
                "threadId": msg.get("threadId"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "date": headers.get("Date", ""),
                "snippet": full_msg.get("snippet", ""),
                "labels": full_msg.get("labelIds", []),
            })
        
        return detailed_messages
    
    def get_message(self, message_id: str) -> dict[str, Any]:
        """
        Get full message content.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Full message details including body
        """
        service = self._get_service()
        
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        
        body = ""
        payload = msg.get("payload", {})
        
        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    break
        
        return {
            "id": msg["id"],
            "threadId": msg.get("threadId"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", "(No subject)"),
            "date": headers.get("Date", ""),
            "body": body,
            "labels": msg.get("labelIds", []),
        }
    
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_message_id: str | None = None
    ) -> dict[str, Any]:
        """
        Send an email message.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            reply_to_message_id: Optional message ID to reply to
        
        Returns:
            Sent message details
        """
        service = self._get_service()
        
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        
        body_data = {"raw": raw}
        if reply_to_message_id:
            original = service.users().messages().get(
                userId="me", id=reply_to_message_id, format="metadata"
            ).execute()
            body_data["threadId"] = original.get("threadId")
        
        result = service.users().messages().send(userId="me", body=body_data).execute()
        
        logger.info(f"Sent email to {to}: {subject}")
        
        return {
            "id": result.get("id"),
            "threadId": result.get("threadId"),
            "to": to,
            "subject": subject,
        }
    
    def get_unread_count(self) -> int:
        """Get count of unread messages in inbox."""
        messages = self.list_messages(query="is:unread in:inbox", max_results=100)
        return len(messages)
    
    def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read."""
        service = self._get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        logger.info(f"Marked message {message_id} as read")
    
    def get_inbox(self, max_results: int = 10) -> list[dict[str, Any]]:
        """Get recent inbox messages."""
        return self.list_messages(query="in:inbox", max_results=max_results)
    
    def get_unread(self, max_results: int = 10) -> list[dict[str, Any]]:
        """Get unread messages."""
        return self.list_messages(query="is:unread", max_results=max_results)
