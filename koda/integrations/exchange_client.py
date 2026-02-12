"""Microsoft Exchange integration client for Calendar and Email.

Compatible with:
- Exchange 2013 (Build 15.0)
- Exchange 2016 (Build 15.1)
- Exchange 2019 (Build 15.2)
- Office 365 / Exchange Online
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Any

import urllib3
from loguru import logger

# Suppress noisy SSL warnings for Exchange servers with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
                EWSDateTime, EWSTimeZone, Version, Build, BASIC, NTLM
            )
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
        except ImportError:
            raise ImportError(
                "exchangelib not installed. Run: pip install exchangelib"
            )
        
        # Disable SSL verification for compatibility with various Exchange servers
        BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
        
        # Map custom timezone names that Exchange servers may use
        try:
            from exchangelib.winzone import MS_TIMEZONE_TO_IANA_MAP
            if 'Customized Time Zone' not in MS_TIMEZONE_TO_IANA_MAP:
                MS_TIMEZONE_TO_IANA_MAP['Customized Time Zone'] = 'Europe/Amsterdam'
        except ImportError:
            pass
        
        # Suppress exchangelib timezone conversion warnings
        warnings.filterwarnings('ignore', message='Cannot convert value.*Customized Time Zone.*')
        
        # Set up credentials
        credentials = Credentials(self.username, self.password)
        
        # Determine version
        version_obj = None
        if self.version in self.VERSION_MAP and self.VERSION_MAP[self.version]:
            major, minor = self.VERSION_MAP[self.version]
            version_obj = Version(Build(major, minor))
        
        # Try multiple connection methods with fallbacks
        errors = []
        
        # Method 1: If server is specified, ALWAYS try direct connection first
        # This takes priority over autodiscover
        if self.server:
            try:
                logger.info(f"Trying direct connection to {self.server}...")
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
                logger.info(f"Connected to Exchange via direct connection: {self.server}")
                return self._account
            except Exception as e:
                errors.append(f"Direct connection to {self.server} failed: {str(e)[:100]}")
                logger.warning(f"Direct connection to {self.server} failed: {e}")
        
        # Method 2: Try autodiscover (only if enabled or no server specified)
        if self.use_autodiscover or not self.server:
            try:
                logger.info(f"Trying autodiscover for {self.email}...")
                self._account = Account(
                    self.email,
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE
                )
                logger.info(f"Connected to Exchange via autodiscover")
                return self._account
            except Exception as e:
                errors.append(f"Autodiscover failed: {str(e)[:100]}")
                logger.warning(f"Autodiscover failed: {e}")
        
        # Method 3: Try Office 365 as last resort ONLY if no server was specified
        # (Don't try O365 if user specified their own server - they know what they want)
        if not self.server:
            try:
                logger.info("Trying Office 365 endpoint as fallback...")
                config = Configuration(
                    server="outlook.office365.com",
                    credentials=credentials,
                )
                self._account = Account(
                    self.email,
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE
                )
                logger.info("Connected to Exchange via Office 365 fallback")
                return self._account
            except Exception as e:
                errors.append(f"Office 365 fallback failed: {str(e)[:100]}")
                logger.warning(f"Office 365 fallback failed: {e}")
        
        # All methods failed
        error_summary = "; ".join(errors)
        raise ConnectionError(
            f"Could not connect to Exchange for {self.email}. "
            f"Tried: {error_summary}. "
            f"Check credentials and server settings."
        )
    
    def _ensure_connected(self):
        """Ensure we have a valid connection, with helpful error messages."""
        try:
            return self._get_account()
        except Exception as e:
            logger.error(f"Exchange connection error: {e}")
            raise
    
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
        
        result = []
        for item in events:
            # Extract the actual ID string from ItemId object
            event_id = None
            if item.id:
                # ItemId has 'id' attribute containing the actual ID string
                if hasattr(item.id, 'id'):
                    event_id = item.id.id
                else:
                    event_id = str(item.id)
            
            result.append({
                "id": event_id,
                "subject": item.subject,
                "start": item.start.isoformat() if item.start else None,
                "end": item.end.isoformat() if item.end else None,
                "location": item.location,
                "body": item.body[:500] if item.body else None,
                "organizer": str(item.organizer) if item.organizer else None,
                "attendees": [str(a.mailbox.email_address) for a in (item.required_attendees or [])],
            })
        return result
    
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
    
    def update_calendar_event(
        self,
        event_id: str,
        subject: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        body: str | None = None,
        location: str | None = None
    ) -> bool:
        """
        Update an existing calendar event.
        
        Args:
            event_id: The event ID to update
            subject: New subject (optional)
            start: New start time (optional)
            end: New end time (optional)
            body: New body/description (optional)
            location: New location (optional)
        
        Returns:
            True if successful
        """
        from exchangelib import EWSDateTime, EWSTimeZone
        
        account = self._get_account()
        tz = EWSTimeZone.localzone()
        
        # Find the event by ID
        try:
            from exchangelib import ItemId
            
            # Create proper ItemId object from string
            item_id = ItemId(id=event_id)
            
            # Get the event using the account's fetch method
            events = list(account.fetch(ids=[item_id]))
            if not events:
                logger.error(f"Event not found: {event_id}")
                return False
            
            event = events[0]
            
            # Update fields
            if subject is not None:
                event.subject = subject
            if start is not None:
                event.start = EWSDateTime.from_datetime(start.replace(tzinfo=tz))
            if end is not None:
                event.end = EWSDateTime.from_datetime(end.replace(tzinfo=tz))
            if body is not None:
                event.body = body
            if location is not None:
                event.location = location
            
            event.save()
            logger.info(f"Updated Exchange event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update Exchange event: {e}")
            return False
    
    def delete_calendar_event(self, event_id: str) -> bool:
        """
        Delete a calendar event.
        
        Args:
            event_id: The event ID to delete
        
        Returns:
            True if successful
        """
        account = self._get_account()
        
        try:
            from exchangelib import ItemId
            
            # Create proper ItemId object from string
            item_id = ItemId(id=event_id)
            
            # Get the event using the account's fetch method
            events = list(account.fetch(ids=[item_id]))
            if not events:
                logger.error(f"Event not found: {event_id}")
                return False
            
            event = events[0]
            event.delete()
            logger.info(f"Deleted Exchange event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete Exchange event: {e}")
            return False
    
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
    
    def search_emails(
        self,
        query: str,
        folder: str = "inbox",
        max_results: int = 20
    ) -> list[dict[str, Any]]:
        """
        Search emails by subject, sender, or body content.
        
        Args:
            query: Search query string
            folder: Folder to search (inbox, sent, drafts)
            max_results: Maximum number of results
        
        Returns:
            List of matching email dictionaries
        """
        account = self._get_account()
        
        folder_map = {
            "inbox": account.inbox,
            "sent": account.sent,
            "drafts": account.drafts,
        }
        
        target_folder = folder_map.get(folder.lower(), account.inbox)
        
        # Search in subject, sender, and body
        # Using Q objects for OR query
        from exchangelib import Q
        
        query_filter = (
            Q(subject__icontains=query) |
            Q(sender__email_address__icontains=query) |
            Q(body__icontains=query)
        )
        
        emails = target_folder.filter(query_filter).order_by("-datetime_received")[:max_results]
        
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
    
    # =========================================================================
    # Contacts Operations
    # =========================================================================
    
    def list_contacts(self, max_results: int = 100) -> list[dict[str, Any]]:
        """
        List contacts from Exchange.
        
        Args:
            max_results: Maximum number of contacts to retrieve
        
        Returns:
            List of contact dictionaries
        """
        account = self._get_account()
        
        contacts = []
        for item in account.contacts.all()[:max_results]:
            contact = self._contact_to_dict(item)
            if contact.get("name") or contact.get("email"):
                contacts.append(contact)
        
        logger.info(f"Retrieved {len(contacts)} contacts from Exchange")
        return contacts
    
    def search_contacts(self, query: str, max_results: int = 50) -> list[dict[str, Any]]:
        """
        Search contacts by name, email, or company.
        
        Args:
            query: Search query string
            max_results: Maximum number of results
        
        Returns:
            List of matching contact dictionaries
        """
        account = self._get_account()
        from exchangelib import Q
        
        query_filter = (
            Q(display_name__icontains=query) |
            Q(email_addresses__icontains=query) |
            Q(company_name__icontains=query) |
            Q(given_name__icontains=query) |
            Q(surname__icontains=query)
        )
        
        contacts = []
        for item in account.contacts.filter(query_filter)[:max_results]:
            contact = self._contact_to_dict(item)
            if contact.get("name") or contact.get("email"):
                contacts.append(contact)
        
        logger.info(f"Found {len(contacts)} contacts matching '{query}'")
        return contacts
    
    def get_contact_by_email(self, email: str) -> dict[str, Any] | None:
        """
        Get a contact by email address.
        
        Args:
            email: Email address to search for
        
        Returns:
            Contact dictionary or None if not found
        """
        account = self._get_account()
        from exchangelib import Q
        
        results = list(account.contacts.filter(
            Q(email_addresses__icontains=email)
        )[:1])
        
        if results:
            return self._contact_to_dict(results[0])
        return None
    
    def _contact_to_dict(self, contact) -> dict[str, Any]:
        """Convert Exchange contact to dictionary."""
        # Get primary email
        email = None
        emails = []
        if hasattr(contact, 'email_addresses') and contact.email_addresses:
            for addr in contact.email_addresses:
                if hasattr(addr, 'email'):
                    emails.append(addr.email)
                elif isinstance(addr, str):
                    emails.append(addr)
            email = emails[0] if emails else None
        
        # Get phone numbers
        phones = []
        for phone_attr in ['phone_numbers', 'business_phones', 'home_phones', 'mobile_phone']:
            if hasattr(contact, phone_attr):
                phone_val = getattr(contact, phone_attr)
                if phone_val:
                    if isinstance(phone_val, (list, tuple)):
                        phones.extend([str(p) for p in phone_val if p])
                    else:
                        phones.append(str(phone_val))
        
        # Build name
        name_parts = []
        if hasattr(contact, 'given_name') and contact.given_name:
            name_parts.append(contact.given_name)
        if hasattr(contact, 'surname') and contact.surname:
            name_parts.append(contact.surname)
        
        name = " ".join(name_parts) if name_parts else getattr(contact, 'display_name', None)
        
        return {
            "name": name or "",
            "firstName": getattr(contact, 'given_name', None),
            "lastName": getattr(contact, 'surname', None),
            "email": email,
            "emails": emails,
            "phones": phones,
            "company": getattr(contact, 'company_name', None),
            "jobTitle": getattr(contact, 'job_title', None),
            "department": getattr(contact, 'department', None),
            "birthday": str(contact.birthday) if hasattr(contact, 'birthday') and contact.birthday else None,
        }
