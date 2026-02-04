"""IMAP email client for generic mail servers.

Works with any IMAP-compatible email server.
"""
from __future__ import annotations

import email
import imaplib
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class EmailMessage:
    """Represents an email message."""
    uid: str
    subject: str
    sender: str
    sender_name: str
    recipients: list[str]
    date: datetime
    body_text: str = ""
    body_html: str = ""
    is_read: bool = False
    has_attachments: bool = False
    attachments: list[str] = field(default_factory=list)


class IMAPClient:
    """
    IMAP client for reading emails from any IMAP server.
    
    Compatible with:
    - Gmail
    - Outlook/Office 365
    - Yahoo Mail
    - ProtonMail Bridge
    - FastMail
    - Any standard IMAP server
    """
    
    def __init__(
        self,
        host: str,
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
        self.folder = folder
        self._connection: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
    
    def connect(self) -> bool:
        """Connect to the IMAP server."""
        try:
            if self.use_ssl:
                self._connection = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._connection = imaplib.IMAP4(self.host, self.port)
            
            self._connection.login(self.username, self.password)
            self._connection.select(self.folder)
            
            logger.info(f"Connected to IMAP server: {self.host}")
            return True
        
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self._connection:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                pass
            self._connection = None
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the IMAP connection and return status."""
        try:
            if self.connect():
                # Get mailbox status
                status, data = self._connection.status(self.folder, "(MESSAGES UNSEEN)")
                self.disconnect()
                
                if status == "OK":
                    return True, f"Connected to {self.host}, folder: {self.folder}"
                return True, f"Connected to {self.host}"
            return False, "Failed to connect to IMAP server"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def list_folders(self) -> list[str]:
        """List all available mail folders."""
        if not self._connection:
            self.connect()
        
        try:
            status, folders = self._connection.list()
            if status != "OK":
                return []
            
            result = []
            for folder in folders:
                # Parse folder name from response
                if isinstance(folder, bytes):
                    folder = folder.decode("utf-8", errors="replace")
                # Extract folder name (last part after delimiter)
                parts = folder.split('"')
                if len(parts) >= 2:
                    result.append(parts[-2])
            
            return result
        except Exception as e:
            logger.error(f"Failed to list folders: {e}")
            return []
    
    def _decode_header_value(self, value: str | None) -> str:
        """Decode email header value."""
        if not value:
            return ""
        
        decoded_parts = []
        for part, charset in decode_header(value):
            if isinstance(part, bytes):
                charset = charset or "utf-8"
                try:
                    decoded_parts.append(part.decode(charset, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    decoded_parts.append(part.decode("utf-8", errors="replace"))
            else:
                decoded_parts.append(str(part))
        
        return "".join(decoded_parts)
    
    def _parse_email(self, msg_data: bytes, uid: str) -> EmailMessage | None:
        """Parse email message data."""
        try:
            msg = email.message_from_bytes(msg_data)
            
            # Get headers
            subject = self._decode_header_value(msg.get("Subject", ""))
            sender = msg.get("From", "")
            sender_name = ""
            
            # Parse sender name and email
            if "<" in sender:
                parts = sender.split("<")
                sender_name = self._decode_header_value(parts[0].strip().strip('"'))
                sender = parts[1].rstrip(">")
            
            # Get recipients
            recipients = []
            to_header = msg.get("To", "")
            if to_header:
                for addr in to_header.split(","):
                    addr = addr.strip()
                    if "<" in addr:
                        addr = addr.split("<")[1].rstrip(">")
                    recipients.append(addr)
            
            # Get date
            date_str = msg.get("Date", "")
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()
            
            # Get body
            body_text = ""
            body_html = ""
            attachments = []
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    
                    if "attachment" in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            attachments.append(self._decode_header_value(filename))
                    elif content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="replace")
                    elif content_type == "text/html":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_html = payload.decode(charset, errors="replace")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    if msg.get_content_type() == "text/html":
                        body_html = payload.decode(charset, errors="replace")
                    else:
                        body_text = payload.decode(charset, errors="replace")
            
            return EmailMessage(
                uid=uid,
                subject=subject,
                sender=sender,
                sender_name=sender_name,
                recipients=recipients,
                date=date,
                body_text=body_text,
                body_html=body_html,
                has_attachments=len(attachments) > 0,
                attachments=attachments
            )
        
        except Exception as e:
            logger.error(f"Failed to parse email: {e}")
            return None
    
    def get_messages(
        self,
        folder: str | None = None,
        limit: int = 20,
        unread_only: bool = False,
        since: datetime | None = None
    ) -> list[EmailMessage]:
        """Get email messages from the specified folder."""
        if not self._connection:
            if not self.connect():
                return []
        
        try:
            # Select folder
            if folder:
                self._connection.select(folder)
            
            # Build search criteria
            criteria = []
            if unread_only:
                criteria.append("UNSEEN")
            if since:
                date_str = since.strftime("%d-%b-%Y")
                criteria.append(f'SINCE "{date_str}"')
            
            if criteria:
                search_criteria = "(" + " ".join(criteria) + ")"
            else:
                search_criteria = "ALL"
            
            # Search for messages
            status, data = self._connection.search(None, search_criteria)
            if status != "OK":
                return []
            
            message_ids = data[0].split()
            if not message_ids:
                return []
            
            # Get most recent messages
            message_ids = message_ids[-limit:]
            
            messages = []
            for msg_id in reversed(message_ids):
                try:
                    status, msg_data = self._connection.fetch(msg_id, "(RFC822 UID FLAGS)")
                    if status != "OK" or not msg_data[0]:
                        continue
                    
                    # Extract UID
                    uid = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    
                    # Parse email
                    email_data = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
                    parsed = self._parse_email(email_data, uid)
                    if parsed:
                        messages.append(parsed)
                
                except Exception as e:
                    logger.debug(f"Failed to fetch message {msg_id}: {e}")
                    continue
            
            return messages
        
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []
    
    def search_messages(
        self,
        query: str,
        folder: str | None = None,
        limit: int = 20
    ) -> list[EmailMessage]:
        """Search for messages matching the query."""
        if not self._connection:
            if not self.connect():
                return []
        
        try:
            if folder:
                self._connection.select(folder)
            
            # Search in subject and body
            status, data = self._connection.search(None, f'(OR SUBJECT "{query}" BODY "{query}")')
            if status != "OK":
                return []
            
            message_ids = data[0].split()[-limit:]
            
            messages = []
            for msg_id in reversed(message_ids):
                try:
                    status, msg_data = self._connection.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data[0]:
                        continue
                    
                    uid = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    email_data = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
                    parsed = self._parse_email(email_data, uid)
                    if parsed:
                        messages.append(parsed)
                except Exception:
                    continue
            
            return messages
        
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def mark_as_read(self, uid: str) -> bool:
        """Mark a message as read."""
        if not self._connection:
            return False
        
        try:
            self._connection.store(uid.encode(), "+FLAGS", "\\Seen")
            return True
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False
