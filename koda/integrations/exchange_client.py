"""Microsoft Exchange integration client for Calendar and Email.

Compatible with:
- Exchange 2013 (Build 15.0)
- Exchange 2016 (Build 15.1)
- Exchange 2019 (Build 15.2)
- Office 365 / Exchange Online
"""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger


class ExchangeClient:
    """
    Client for Microsoft Exchange (Calendar and Email) operations.
    
    Supports Exchange 2013, 2016, 2019, and Office 365.
    Uses EWS (Exchange Web Services) protocol for maximum compatibility.
    """
    
    # Version mapping for explicit version specification
    VERSION_MAP = {
        "2013": (15, 0),  # Exchange 2013
        "2016": (15, 1),  # Exchange 2016
        "2019": (15, 2),  # Exchange 2019
        "o365": None,     # Auto-detect for Office 365
        "auto": None,     # Auto-detect
    }
    
    def __init__(
        self,
        email: str,
        password: str,
        server: str | None = None,
        username: str | None = None,
        calendar_name: str = "Calendar",
        version: str = "auto",
        auth_type: str = "basic",
        use_autodiscover: bool = True
    ):
        """
        Initialize Exchange client.
        
        Args:
            email: Email address for the mailbox
            password: Password or app-specific password
            server: Exchange server URL (optional if autodiscover enabled)
            username: Username for authentication (if different from email, e.g., DOMAIN\\user)
            calendar_name: Name of the calendar to use
            version: Exchange version (auto, 2013, 2016, 2019, o365)
            auth_type: Authentication type (basic, ntlm, oauth2)
            use_autodiscover: Whether to use autodiscover for server lookup
        """
        self.email = email
        self.password = password
        self.server = server
        self.username = username or email  # Use email as username if not provided
        self.calendar_name = calendar_name
        self.version = version
        self.auth_type = auth_type
        self.use_autodiscover = use_autodiscover
        self._account = None
    
    def _get_account(self):
        """Get or create the Exchange account connection."""
        if self._account:
            return self._account
        
        try:
            from exchangelib import (
                Account, Credentials, Configuration, DELEGATE,
                EWSDateTime, EWSTimeZone, Version, Build
            )
            from exchangelib.protocol import BaseProtocol
        except ImportError:
            raise ImportError(
                "exchangelib not installed. Run: pip install exchangelib"
            )
        
        # Set up credentials based on auth type
        # Use username for authentication (may be different from email, e.g., DOMAIN\\user)
        if self.auth_type == "ntlm":
            # NTLM authentication for on-premises Exchange
            from exchangelib import NTLM
            credentials = Credentials(self.username, self.password)
        else:
            # Basic authentication
            credentials = Credentials(self.username, self.password)
        
        # Determine version
        version_obj = None
        if self.version in self.VERSION_MAP and self.VERSION_MAP[self.version]:
            major, minor = self.VERSION_MAP[self.version]
            version_obj = Version(Build(major, minor))
        
        if self.server and not self.use_autodiscover:
            # Direct connection to specified server
            config_kwargs = {
                "server": self.server,
                "credentials": credentials,
            }
            if version_obj:
                config_kwargs["version"] = version_obj
            
            config = Configuration(**config_kwargs)
            self._account = Account(
                self.email,
                config=config,
                autodiscover=False,
                access_type=DELEGATE
            )
        else:
            # Use autodiscover
            self._account = Account(
                self.email,
                credentials=credentials,
                autodiscover=True,
                access_type=DELEGATE
            )
        
        # Log the detected version for debugging
        if self._account:
            detected = self._account.version
            logger.debug(f"Connected to Exchange: {detected}")
        
        return self._account
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the Exchange connection and return status."""
        try:
            account = self._get_account()
            version = account.version
            return True, f"Connected to Exchange {version.build}"
        except Exception as e:
            return False, str(e)
    
    def list_calendar_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        max_results: int = 50
    ) -> list[dict[str, Any]]:
        """
        List calendar events.
        
        Args:
            start: Start datetime (default: now)
            end: End datetime (default: 7 days from now)
            max_results: Maximum number of events
        
        Returns:
            List of event dictionaries
        """
        from exchangelib import EWSDateTime, EWSTimeZone
        
        account = self._get_account()
        tz = EWSTimeZone.localzone()
        
        if start is None:
            start = datetime.now()
        if end is None:
            end = start + timedelta(days=7)
        
        start_ews = EWSDateTime.from_datetime(start.replace(tzinfo=tz))
        end_ews = EWSDateTime.from_datetime(end.replace(tzinfo=tz))
        
        calendar = account.calendar
        events = calendar.view(start=start_ews, end=end_ews)[:max_results]
        
        return [
            {
                "id": str(item.id) if item.id else None,
                "subject": item.subject,
                "start": item.start.isoformat() if item.start else None,
                "end": item.end.isoformat() if item.end else None,
                "location": item.location,
                "body": item.body[:500] if item.body else None,
                "organizer": str(item.organizer) if item.organizer else None,
                "attendees": [str(a.mailbox.email_address) for a in (item.required_attendees or [])],
            }
            for item in events
        ]
    
    def create_calendar_event(
        self,
        subject: str,
        start: datetime,
        end: datetime,
        body: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Create a calendar event.
        
        Args:
            subject: Event subject
            start: Start datetime
            end: End datetime
            body: Event body/description
            location: Event location
            attendees: List of attendee email addresses
        
        Returns:
            Created event details
        """
        from exchangelib import CalendarItem, EWSDateTime, EWSTimeZone, Attendee, Mailbox
        
        account = self._get_account()
        tz = EWSTimeZone.localzone()
        
        event = CalendarItem(
            account=account,
            folder=account.calendar,
            subject=subject,
            start=EWSDateTime.from_datetime(start.replace(tzinfo=tz)),
            end=EWSDateTime.from_datetime(end.replace(tzinfo=tz)),
        )
        
        if body:
            event.body = body
        if location:
            event.location = location
        if attendees:
            event.required_attendees = [
                Attendee(mailbox=Mailbox(email_address=email))
                for email in attendees
            ]
        
        event.save()
        
        logger.info(f"Created Exchange event: {subject}")
        
        return {
            "id": str(event.id) if event.id else None,
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
    
    def list_emails(
        self,
        folder: str = "inbox",
        max_results: int = 10,
        unread_only: bool = False
    ) -> list[dict[str, Any]]:
        """
        List emails from a folder.
        
        Args:
            folder: Folder name (inbox, sent, drafts)
            max_results: Maximum number of emails
            unread_only: Only return unread emails
        
        Returns:
            List of email dictionaries
        """
        account = self._get_account()
        
        folder_map = {
            "inbox": account.inbox,
            "sent": account.sent,
            "drafts": account.drafts,
        }
        
        target_folder = folder_map.get(folder.lower(), account.inbox)
        
        if unread_only:
            emails = target_folder.filter(is_read=False).order_by("-datetime_received")[:max_results]
        else:
            emails = target_folder.all().order_by("-datetime_received")[:max_results]
        
        return [
            {
                "id": str(item.id) if item.id else None,
                "subject": item.subject,
                "from": str(item.sender.email_address) if item.sender else None,
                "to": [str(r.email_address) for r in (item.to_recipients or [])],
                "date": item.datetime_received.isoformat() if item.datetime_received else None,
                "is_read": item.is_read,
                "body_preview": item.body[:300] if item.body else None,
            }
            for item in emails
        ]
    
    def get_email(self, message_id: str) -> dict[str, Any]:
        """
        Get full email content.
        
        Args:
            message_id: Email message ID
        
        Returns:
            Full email details
        """
        account = self._get_account()
        
        from exchangelib import Message
        
        items = list(account.inbox.filter(id=message_id))
        if not items:
            items = list(account.sent.filter(id=message_id))
        
        if not items:
            raise ValueError(f"Email not found: {message_id}")
        
        item = items[0]
        
        return {
            "id": str(item.id),
            "subject": item.subject,
            "from": str(item.sender.email_address) if item.sender else None,
            "to": [str(r.email_address) for r in (item.to_recipients or [])],
            "date": item.datetime_received.isoformat() if item.datetime_received else None,
            "body": item.body if item.body else "",
            "is_read": item.is_read,
        }
    
    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Send an email.
        
        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body
            cc: Optional CC recipients
        
        Returns:
            Sent email details
        """
        from exchangelib import Message, Mailbox, HTMLBody
        
        account = self._get_account()
        
        message = Message(
            account=account,
            folder=account.sent,
            subject=subject,
            body=HTMLBody(body) if "<" in body else body,
            to_recipients=[Mailbox(email_address=email) for email in to],
        )
        
        if cc:
            message.cc_recipients = [Mailbox(email_address=email) for email in cc]
        
        message.send()
        
        logger.info(f"Sent Exchange email to {to}: {subject}")
        
        return {
            "to": to,
            "subject": subject,
            "status": "sent",
        }
    
    def reply_to_email(self, message_id: str, body: str) -> dict[str, Any]:
        """
        Reply to an email.
        
        Args:
            message_id: Original message ID
            body: Reply body
        
        Returns:
            Reply status
        """
        account = self._get_account()
        
        items = list(account.inbox.filter(id=message_id))
        if not items:
            raise ValueError(f"Email not found: {message_id}")
        
        original = items[0]
        original.reply(subject=f"Re: {original.subject}", body=body)
        
        logger.info(f"Replied to email: {original.subject}")
        
        return {
            "original_subject": original.subject,
            "status": "replied",
        }
    
    def get_today_events(self) -> list[dict[str, Any]]:
        """Get all calendar events for today."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.list_calendar_events(start=today, end=tomorrow)
    
    def get_unread_count(self) -> int:
        """Get count of unread emails in inbox."""
        account = self._get_account()
        return account.inbox.filter(is_read=False).count()
