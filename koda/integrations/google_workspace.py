"""Unified Google Workspace Integration - Gmail, Calendar, and Meet.

This module provides a single OAuth flow for all Google services:
- Gmail: Read, send, search emails
- Calendar: Full access including shared calendars
- Meet: Create video conference links

Setup requires:
1. Google Cloud Project with APIs enabled
2. OAuth 2.0 credentials (Desktop App type)
3. credentials.json file in ~/.koda/

Key improvements in this version:
- Robust token refresh with automatic retry
- Better shared calendar discovery
- Connection health monitoring
- Persistent connection state tracking
"""
from __future__ import annotations

import base64
import json
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

from loguru import logger

# Check for Google API libraries
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow, Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


# All scopes needed for full Google Workspace integration
GOOGLE_SCOPES = [
    # OpenID (Google adds this automatically, so we must request it)
    "openid",
    # Gmail
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar (full access for Meet links)
    "https://www.googleapis.com/auth/calendar",
    # User info
    "https://www.googleapis.com/auth/userinfo.email",
]


@dataclass
class GoogleEmail:
    """Represents a Gmail message."""
    id: str
    thread_id: str
    subject: str
    sender: str
    to: str
    date: datetime
    snippet: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    is_unread: bool = False
    priority: str = "normal"  # normal, high, low


@dataclass
class GoogleCalendarEvent:
    """Represents a Google Calendar event."""
    id: str
    summary: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: list[str] = field(default_factory=list)
    meet_link: Optional[str] = None
    calendar_id: str = "primary"
    calendar_name: str = ""
    is_all_day: bool = False
    status: str = "confirmed"
    organizer: str = ""
    is_recurring: bool = False
    recurrence_rule: str = ""


@dataclass 
class GoogleCalendar:
    """Represents a Google Calendar."""
    id: str
    name: str
    description: str = ""
    is_primary: bool = False
    access_role: str = "reader"  # owner, writer, reader
    background_color: str = ""
    is_shared: bool = False  # True if this is a shared calendar
    owner_email: str = ""


class GoogleWorkspaceClient:
    """
    Unified client for Google Workspace APIs.
    
    Provides access to Gmail, Calendar, and Meet through a single OAuth flow.
    
    Setup:
    1. Go to https://console.cloud.google.com/
    2. Create a project or select existing
    3. Enable APIs: Gmail API, Google Calendar API
    4. Create OAuth 2.0 credentials (Desktop app)
    5. Download credentials.json to ~/.koda/
    6. Run: koda setup google
    """
    
    CREDENTIALS_FILE = "~/.koda/google_credentials.json"
    TOKEN_FILE = "~/.koda/google_token.json"
    STATE_FILE = "~/.koda/google_state.json"
    
    SETUP_INSTRUCTIONS = """
## 🔧 Google Workspace Setup

### Step 1: Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Name: "Koda" (or anything else)
4. Click "Create"

### Step 2: Enable APIs
1. Go to "APIs & Services" → "Library"
2. Search and enable these APIs:
   - **Gmail API**
   - **Google Calendar API**

### Step 3: OAuth Consent Screen
1. Go to "APIs & Services" → "OAuth consent screen"
2. Choose "External" (or "Internal" for Workspace)
3. Fill in:
   - App name: "Koda"
   - User support email: your email
   - Developer contact: your email
4. Click "Save and Continue"
5. At Scopes: click "Add or Remove Scopes"
6. Add:
   - `.../auth/gmail.readonly`
   - `.../auth/gmail.send`
   - `.../auth/gmail.modify`
   - `.../auth/calendar`
7. Click "Save and Continue"
8. At Test users: add your own Gmail address
9. Click "Save and Continue"

### Step 4: OAuth Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: **Desktop app**
4. Name: "Koda Desktop"
5. Click "Create"
6. Click "Download JSON"
7. Rename to `google_credentials.json`
8. Move to `~/.koda/google_credentials.json`

### Step 5: Authorize
Run in terminal:
```
koda setup google
```

Or via WhatsApp:
```
/setupgoogle
```
"""
    
    def __init__(
        self,
        credentials_file: Optional[str] = None,
        token_file: Optional[str] = None,
        state_file: Optional[str] = None,
        timezone: str = "Europe/Amsterdam"
    ):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API libraries not installed. Run:\n"
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        self.credentials_file = Path(credentials_file or self.CREDENTIALS_FILE).expanduser()
        self.token_file = Path(token_file or self.TOKEN_FILE).expanduser()
        self.state_file = Path(state_file or self.STATE_FILE).expanduser()
        
        self._credentials: Optional[Credentials] = None
        self._gmail_service = None
        self._calendar_service = None
        self._user_email: Optional[str] = None
        self._cached_calendars: list[GoogleCalendar] = []
        self._calendars_cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # Cache calendars for 5 minutes
        self.timezone = timezone
        
        # Load persistent state
        self._state = self._load_state()
    
    def _load_state(self) -> dict:
        """Load persistent state from disk."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")
        return {
            "last_refresh": None,
            "refresh_count": 0,
            "connection_failures": 0,
            "last_successful_connection": None,
        }
    
    def _save_state(self) -> None:
        """Save persistent state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._state, indent=2, default=str))
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")
    
    @property
    def is_configured(self) -> bool:
        """Check if credentials file exists."""
        return self.credentials_file.exists()
    
    @property
    def is_authorized(self) -> bool:
        """Check if we have valid tokens with robust validation."""
        if not self.token_file.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_file), GOOGLE_SCOPES)
            if not creds:
                return False
            
            # Check if token is valid or can be refreshed
            if creds.valid:
                return True
            
            # Token might be expired but refreshable
            if creds.expired and creds.refresh_token:
                return True
            
            return False
        except Exception as e:
            logger.debug(f"Authorization check failed: {e}")
            return False
    
    def _get_credentials(self) -> Credentials:
        """Get or refresh credentials with robust error handling and retry."""
        if self._credentials and self._credentials.valid:
            return self._credentials
        
        creds = None
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Load existing token
                if self.token_file.exists():
                    try:
                        creds = Credentials.from_authorized_user_file(str(self.token_file), GOOGLE_SCOPES)
                        logger.debug("Loaded credentials from token file")
                    except Exception as e:
                        logger.warning(f"Failed to load token: {e}")
                
                # Refresh or re-authorize
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        try:
                            logger.info("Refreshing Google access token...")
                            creds.refresh(Request())
                            self._save_token(creds)
                            self._state["last_refresh"] = datetime.now().isoformat()
                            self._state["refresh_count"] = self._state.get("refresh_count", 0) + 1
                            self._state["connection_failures"] = 0
                            self._state["last_successful_connection"] = datetime.now().isoformat()
                            self._save_state()
                            logger.info("✅ Token refreshed successfully")
                        except Exception as e:
                            error_str = str(e)
                            logger.error(f"Token refresh failed: {e}")
                            self._state["connection_failures"] = self._state.get("connection_failures", 0) + 1
                            
                            # If token is permanently revoked, delete it to stop endless retries
                            if "invalid_grant" in error_str.lower():
                                logger.warning("Token permanently revoked. Removing invalid token file to stop retries.")
                                try:
                                    self.token_file.rename(self.token_file.with_suffix('.revoked'))
                                    logger.info(f"Moved invalid token to {self.token_file.with_suffix('.revoked')}")
                                except Exception:
                                    try:
                                        self.token_file.unlink()
                                    except Exception:
                                        pass
                                self._state["token_revoked"] = True
                                self._state["token_revoked_at"] = datetime.now().isoformat()
                            
                            self._save_state()
                            creds = None
                            raise AuthorizationRequired(
                                f"Google authorization expired or invalid. Please run: koda setup google\nError: {e}"
                            )
                    
                    if not creds:
                        raise AuthorizationRequired(
                            "Google authorization required. Run: koda setup google"
                        )
                
                self._credentials = creds
                return creds
                
            except AuthorizationRequired:
                raise
            except Exception as e:
                retry_count += 1
                logger.warning(f"Credential attempt {retry_count} failed: {e}")
                if retry_count >= max_retries:
                    raise AuthorizationRequired(
                        f"Failed to get credentials after {max_retries} attempts. Please run: koda setup google"
                    )
                time.sleep(1)  # Brief delay before retry
        
        raise AuthorizationRequired("Could not obtain valid credentials")
    
    def _save_token(self, creds: Credentials) -> None:
        """Save credentials to token file atomically."""
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file first, then move for atomic operation
        temp_file = self.token_file.with_suffix('.tmp')
        temp_file.write_text(creds.to_json())
        temp_file.replace(self.token_file)
        logger.debug(f"Token saved to {self.token_file}")
    
    def force_refresh(self) -> bool:
        """Force a token refresh even if current token is still valid."""
        try:
            if not self.token_file.exists():
                return False
            
            creds = Credentials.from_authorized_user_file(str(self.token_file), GOOGLE_SCOPES)
            if creds and creds.refresh_token:
                logger.info("Forcing token refresh...")
                creds.refresh(Request())
                self._save_token(creds)
                self._credentials = creds
                self._state["last_refresh"] = datetime.now().isoformat()
                self._save_state()
                logger.info("✅ Token force-refreshed successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Force refresh failed: {e}")
            return False
    
    def authorize_interactive(self, port: int = 8090) -> bool:
        """
        Run interactive OAuth flow.
        
        Opens browser for user to authorize, then saves token.
        
        Args:
            port: Local port for OAuth callback
        
        Returns:
            True if authorization successful
        """
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}\n\n"
                f"{self.SETUP_INSTRUCTIONS}"
            )
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_file),
                GOOGLE_SCOPES
            )
            
            logger.info("Opening browser for Google authorization...")
            creds = flow.run_local_server(
                port=port,
                prompt="consent",
                access_type="offline",  # Request refresh token
                success_message="✅ Koda is now connected to Google! You can close this tab."
            )
            
            self._save_token(creds)
            self._credentials = creds
            
            # Get user email
            self._user_email = self._get_user_email()
            
            # Update state
            self._state["last_refresh"] = datetime.now().isoformat()
            self._state["connection_failures"] = 0
            self._state["last_successful_connection"] = datetime.now().isoformat()
            self._save_state()
            
            logger.info(f"✅ Authorized as {self._user_email}")
            
            # Clear cache
            self._cached_calendars = []
            self._calendars_cache_time = None
            
            return True
            
        except Exception as e:
            logger.error(f"Authorization failed: {e}")
            return False
    
    def get_authorization_url(self, redirect_uri: str = "http://localhost:8090") -> str:
        """
        Get OAuth authorization URL for web-based flow.
        
        Args:
            redirect_uri: Where to redirect after auth
        
        Returns:
            Authorization URL to open in browser
        """
        if not self.credentials_file.exists():
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")
        
        flow = Flow.from_client_secrets_file(
            str(self.credentials_file),
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        
        return auth_url
    
    def authorize_with_code(self, code: str, redirect_uri: str = "http://localhost:8090") -> bool:
        """
        Complete authorization with code from OAuth callback.
        
        Args:
            code: Authorization code from Google
            redirect_uri: Must match the one used in get_authorization_url
        
        Returns:
            True if successful
        """
        try:
            flow = Flow.from_client_secrets_file(
                str(self.credentials_file),
                scopes=GOOGLE_SCOPES,
                redirect_uri=redirect_uri
            )
            
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            self._save_token(creds)
            self._credentials = creds
            
            self._user_email = self._get_user_email()
            
            # Update state
            self._state["last_refresh"] = datetime.now().isoformat()
            self._state["connection_failures"] = 0
            self._state["last_successful_connection"] = datetime.now().isoformat()
            self._save_state()
            
            logger.info(f"✅ Authorized as {self._user_email}")
            
            # Clear cache
            self._cached_calendars = []
            self._calendars_cache_time = None
            
            return True
            
        except Exception as e:
            logger.error(f"Authorization with code failed: {e}")
            return False
    
    def _get_user_email(self) -> str:
        """Get the authorized user's email address."""
        try:
            service = build("oauth2", "v2", credentials=self._get_credentials())
            user_info = service.userinfo().get().execute()
            return user_info.get("email", "")
        except:
            return ""
    
    @property
    def user_email(self) -> str:
        """Get cached user email or fetch it."""
        if not self._user_email:
            self._user_email = self._get_user_email()
        return self._user_email
    
    # ========================================================================
    # Gmail Methods
    # ========================================================================
    
    def _get_gmail_service(self):
        """Get Gmail API service with automatic retry."""
        if not self._gmail_service:
            self._gmail_service = build("gmail", "v1", credentials=self._get_credentials())
        return self._gmail_service
    
    def list_emails(
        self,
        query: str = "",
        max_results: int = 10,
        unread_only: bool = False,
        prioritize: bool = True
    ) -> list[GoogleEmail]:
        """
        List emails from Gmail with optional prioritization.
        
        Args:
            query: Gmail search query (e.g., "from:example@gmail.com subject:hello")
            max_results: Maximum number of emails to return
            unread_only: Only return unread emails
            prioritize: Apply smart prioritization algorithm
        
        Returns:
            List of GoogleEmail objects, sorted by priority if prioritize=True
        """
        service = self._get_gmail_service()
        
        if unread_only:
            query = f"is:unread {query}".strip()
        
        try:
            results = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results * 2  # Fetch more for prioritization
            ).execute()
            
            messages = results.get("messages", [])
            emails = []
            
            for msg in messages:
                email = self._get_email_details(msg["id"])
                if email:
                    if prioritize:
                        email.priority = self._calculate_email_priority(email)
                    emails.append(email)
            
            # Sort by priority if requested
            if prioritize:
                emails.sort(key=lambda e: (
                    0 if e.priority == "high" else (1 if e.priority == "normal" else 2),
                    -e.date.timestamp() if e.date else 0
                ))
            
            return emails[:max_results]
            
        except HttpError as e:
            logger.error(f"Failed to list emails: {e}")
            return []
    
    def _calculate_email_priority(self, email: GoogleEmail) -> str:
        """Calculate email priority based on various signals."""
        priority_score = 0
        
        # Unread emails are higher priority
        if email.is_unread:
            priority_score += 2
        
        # Check for important labels
        important_labels = ["IMPORTANT", "STARRED", "CATEGORY_PERSONAL"]
        for label in important_labels:
            if label in email.labels:
                priority_score += 1
        
        # Check for urgency keywords in subject
        urgency_keywords = ["urgent", "asap", "deadline", "action required", "important", "meeting"]
        subject_lower = email.subject.lower()
        for keyword in urgency_keywords:
            if keyword in subject_lower:
                priority_score += 1
                break
        
        # Recent emails (within 24 hours) get higher priority
        if email.date:
            hours_old = (datetime.now(email.date.tzinfo) - email.date).total_seconds() / 3600
            if hours_old < 24:
                priority_score += 1
        
        # Determine priority level
        if priority_score >= 4:
            return "high"
        elif priority_score >= 2:
            return "normal"
        else:
            return "low"
    
    def get_high_priority_emails(self, max_results: int = 10) -> list[GoogleEmail]:
        """Get only high priority unread emails."""
        emails = self.list_emails(unread_only=True, max_results=max_results * 3, prioritize=True)
        return [e for e in emails if e.priority == "high"][:max_results]
    
    def _get_email_details(self, message_id: str) -> Optional[GoogleEmail]:
        """Get full details of an email."""
        service = self._get_gmail_service()
        
        try:
            msg = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()
            
            headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
            
            # Parse body
            body = ""
            if "parts" in msg["payload"]:
                for part in msg["payload"]["parts"]:
                    if part["mimeType"] == "text/plain" and "data" in part.get("body", {}):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break
            elif "body" in msg["payload"] and "data" in msg["payload"]["body"]:
                body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode("utf-8")
            
            # Parse date
            date_str = headers.get("date", "")
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except:
                date = datetime.now()
            
            return GoogleEmail(
                id=msg["id"],
                thread_id=msg["threadId"],
                subject=headers.get("subject", "(No Subject)"),
                sender=headers.get("from", ""),
                to=headers.get("to", ""),
                date=date,
                snippet=msg.get("snippet", ""),
                body=body,
                labels=msg.get("labelIds", []),
                is_unread="UNREAD" in msg.get("labelIds", [])
            )
            
        except HttpError as e:
            logger.error(f"Failed to get email {message_id}: {e}")
            return None
    
    def get_email(self, message_id: str) -> Optional[GoogleEmail]:
        """Get a specific email by ID."""
        return self._get_email_details(message_id)
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        html: bool = False
    ) -> Optional[str]:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            html: If True, body is HTML
        
        Returns:
            Message ID if successful, None otherwise
        """
        service = self._get_gmail_service()
        
        try:
            message = MIMEMultipart("alternative") if html else MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            
            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc
            
            if html:
                message.attach(MIMEText(body, "plain"))
                message.attach(MIMEText(body, "html"))
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            
            result = service.users().messages().send(
                userId="me",
                body={"raw": raw}
            ).execute()
            
            logger.info(f"Email sent to {to}: {result['id']}")
            return result["id"]
            
        except HttpError as e:
            logger.error(f"Failed to send email: {e}")
            return None
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark an email as read."""
        service = self._get_gmail_service()
        
        try:
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Failed to mark as read: {e}")
            return False
    
    def search_emails(self, query: str, max_results: int = 20) -> list[GoogleEmail]:
        """
        Search emails with Gmail query syntax.
        
        Examples:
            - "from:john@example.com"
            - "subject:meeting"
            - "is:unread newer_than:7d"
            - "has:attachment"
        """
        return self.list_emails(query=query, max_results=max_results)
    
    # ========================================================================
    # Calendar Methods
    # ========================================================================
    
    def _get_calendar_service(self):
        """Get Calendar API service."""
        if not self._calendar_service:
            self._calendar_service = build("calendar", "v3", credentials=self._get_credentials())
        return self._calendar_service
    
    def list_calendars(self, use_cache: bool = True) -> list[GoogleCalendar]:
        """
        List all calendars the user has access to, including shared calendars.
        
        Args:
            use_cache: Use cached results if available and fresh
        
        Returns:
            List of GoogleCalendar objects including shared calendars
        """
        # Check cache
        if use_cache and self._cached_calendars and self._calendars_cache_time:
            if datetime.now() - self._calendars_cache_time < self._cache_ttl:
                logger.debug(f"Using cached calendars ({len(self._cached_calendars)} items)")
                return self._cached_calendars
        
        service = self._get_calendar_service()
        
        try:
            # Get all calendars with pagination
            calendars = []
            page_token = None
            
            while True:
                params = {}
                if page_token:
                    params["pageToken"] = page_token
                
                result = service.calendarList().list(**params).execute()
                
                for cal in result.get("items", []):
                    # Determine if this is a shared calendar
                    access_role = cal.get("accessRole", "reader")
                    is_shared = access_role in ["reader", "writer"] and not cal.get("primary", False)
                    
                    # Get owner info if available
                    owner = cal.get("primary", False)
                    owner_email = ""
                    if not owner and "owner" in str(cal.get("summaryOverride", "")).lower():
                        # Try to extract owner from summary
                        pass
                    
                    calendar_obj = GoogleCalendar(
                        id=cal["id"],
                        name=cal.get("summary", "Unnamed"),
                        description=cal.get("description", ""),
                        is_primary=cal.get("primary", False),
                        access_role=access_role,
                        background_color=cal.get("backgroundColor", ""),
                        is_shared=is_shared,
                        owner_email=owner_email
                    )
                    calendars.append(calendar_obj)
                
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
            
            # Update cache
            self._cached_calendars = calendars
            self._calendars_cache_time = datetime.now()
            
            logger.info(f"Found {len(calendars)} calendars ({sum(1 for c in calendars if c.is_shared)} shared)")
            return calendars
            
        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            # Return cached data if available, even if stale
            if self._cached_calendars:
                logger.warning("Returning stale cached calendars due to error")
                return self._cached_calendars
            return []
    
    def get_shared_calendars(self) -> list[GoogleCalendar]:
        """Get only shared calendars (not owned by user)."""
        all_calendars = self.list_calendars()
        return [c for c in all_calendars if c.is_shared or not c.is_primary]
    
    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 50,
        include_recurring: bool = True
    ) -> list[GoogleCalendarEvent]:
        """
        List calendar events.
        
        Args:
            calendar_id: Calendar ID (default: primary, use 'all' for all calendars)
            time_min: Start time filter (default: now)
            time_max: End time filter (default: 30 days from now)
            max_results: Maximum events per calendar
            include_recurring: Expand recurring events
        
        Returns:
            List of GoogleCalendarEvent objects
        """
        service = self._get_calendar_service()
        
        if time_min is None:
            time_min = datetime.now(timezone.utc)
        if time_max is None:
            time_max = time_min + timedelta(days=30)
        
        # Get calendars to query
        if calendar_id == "all":
            calendars = self.list_calendars()
            calendar_ids = [(c.id, c.name) for c in calendars if c.access_role in ["owner", "writer", "reader"]]
        else:
            calendar_ids = [(calendar_id, "primary")]
        
        all_events = []
        
        for cal_id, cal_name in calendar_ids:
            try:
                # Use pagination for large result sets
                page_token = None
                events_fetched = 0
                
                while events_fetched < max_results:
                    params = {
                        "calendarId": cal_id,
                        "timeMin": time_min.isoformat(),
                        "timeMax": time_max.isoformat(),
                        "maxResults": min(250, max_results - events_fetched),  # Google max is 250
                        "singleEvents": include_recurring,
                        "orderBy": "startTime"
                    }
                    if page_token:
                        params["pageToken"] = page_token
                    
                    result = service.events().list(**params).execute()
                    
                    for event in result.get("items", []):
                        parsed_event = self._parse_event(event, cal_id, cal_name)
                        all_events.append(parsed_event)
                        events_fetched += 1
                    
                    page_token = result.get("nextPageToken")
                    if not page_token:
                        break
                    
            except HttpError as e:
                logger.warning(f"Failed to get events from {cal_id}: {e}")
        
        # Sort by start time
        all_events.sort(key=lambda e: e.start)
        return all_events
    
    def _parse_event(self, event: dict, calendar_id: str, calendar_name: str) -> GoogleCalendarEvent:
        """Parse raw event data into GoogleCalendarEvent."""
        # Parse start/end times
        start_data = event.get("start", {})
        end_data = event.get("end", {})
        
        is_all_day = "date" in start_data
        
        if is_all_day:
            start = datetime.fromisoformat(start_data["date"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(end_data["date"]).replace(tzinfo=timezone.utc)
        else:
            start = datetime.fromisoformat(start_data.get("dateTime", "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_data.get("dateTime", "").replace("Z", "+00:00"))
        
        # Get Meet link
        meet_link = None
        if "conferenceData" in event:
            for ep in event["conferenceData"].get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri")
                    break
        
        # Get attendees
        attendees = [a.get("email", "") for a in event.get("attendees", [])]
        
        # Check if recurring
        is_recurring = "recurrence" in event
        recurrence_rule = ""
        if is_recurring:
            recurrence_rule = ", ".join(event.get("recurrence", []))
        
        return GoogleCalendarEvent(
            id=event["id"],
            summary=event.get("summary", "(No Title)"),
            start=start,
            end=end,
            location=event.get("location"),
            description=event.get("description"),
            attendees=attendees,
            meet_link=meet_link,
            calendar_id=calendar_id,
            calendar_name=calendar_name,
            is_all_day=is_all_day,
            status=event.get("status", "confirmed"),
            organizer=event.get("organizer", {}).get("email", ""),
            is_recurring=is_recurring,
            recurrence_rule=recurrence_rule
        )
    
    def get_event(self, event_id: str, calendar_id: str = "primary") -> Optional[GoogleCalendarEvent]:
        """Get a specific event by ID."""
        service = self._get_calendar_service()
        
        try:
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            return self._parse_event(event, calendar_id, "")
            
        except HttpError as e:
            logger.error(f"Failed to get event {event_id}: {e}")
            return None
    
    def create_event(
        self,
        summary: str,
        start: datetime,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        calendar_id: str = "primary",
        add_meet_link: bool = False,
        all_day: bool = False,
        send_notifications: bool = True
    ) -> Optional[GoogleCalendarEvent]:
        """
        Create a calendar event.
        
        Args:
            summary: Event title
            start: Start time
            end: End time (default: start + 1 hour)
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            calendar_id: Which calendar to add to
            add_meet_link: Create Google Meet link for this event
            all_day: Create as all-day event
            send_notifications: Send email notifications to attendees
        
        Returns:
            Created event or None if failed
        """
        service = self._get_calendar_service()
        
        if end is None:
            end = start + timedelta(hours=1)
        
        event_body = {
            "summary": summary,
        }
        
        if all_day:
            event_body["start"] = {"date": start.strftime("%Y-%m-%d")}
            event_body["end"] = {"date": end.strftime("%Y-%m-%d")}
        else:
            event_body["start"] = {"dateTime": start.isoformat(), "timeZone": self.timezone}
            event_body["end"] = {"dateTime": end.isoformat(), "timeZone": self.timezone}
        
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]
        
        # Add Google Meet link
        if add_meet_link:
            event_body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"koda-meet-{datetime.now().timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}
                }
            }
        
        try:
            result = service.events().insert(
                calendarId=calendar_id,
                body=event_body,
                conferenceDataVersion=1 if add_meet_link else 0,
                sendUpdates="all" if send_notifications and attendees else "none"
            ).execute()
            
            logger.info(f"Created event: {result['id']}")
            
            # Invalidate calendar list cache as new event might affect things
            self._calendars_cache_time = None
            
            return self._parse_event(result, calendar_id, "")
            
        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            return None
    
    def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        add_meet_link: bool = False
    ) -> Optional[GoogleCalendarEvent]:
        """Update an existing event."""
        service = self._get_calendar_service()
        
        try:
            # Get existing event
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Update fields
            if summary:
                event["summary"] = summary
            if description:
                event["description"] = description
            if location:
                event["location"] = location
            if start:
                event["start"] = {"dateTime": start.isoformat(), "timeZone": self.timezone}
            if end:
                event["end"] = {"dateTime": end.isoformat(), "timeZone": self.timezone}
            
            # Add Meet link if requested and not present
            if add_meet_link and "conferenceData" not in event:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"koda-meet-{datetime.now().timestamp()}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                }
            
            result = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                conferenceDataVersion=1 if add_meet_link else 0
            ).execute()
            
            return self._parse_event(result, calendar_id, "")
            
        except HttpError as e:
            logger.error(f"Failed to update event: {e}")
            return None
    
    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete a calendar event."""
        service = self._get_calendar_service()
        
        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            logger.info(f"Deleted event: {event_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Failed to delete event: {e}")
            return False
    
    def create_meet_link(
        self,
        title: str = "Koda Meeting",
        start: Optional[datetime] = None,
        duration_minutes: int = 60,
        attendees: Optional[list[str]] = None
    ) -> Optional[str]:
        """
        Create a Google Meet link by creating a calendar event.
        
        Args:
            title: Meeting title
            start: Start time (default: now)
            duration_minutes: Meeting duration
            attendees: Attendee emails to invite
        
        Returns:
            Google Meet URL or None if failed
        """
        if start is None:
            start = datetime.now(timezone.utc)
        
        end = start + timedelta(minutes=duration_minutes)
        
        event = self.create_event(
            summary=title,
            start=start,
            end=end,
            attendees=attendees,
            add_meet_link=True,
            send_notifications=bool(attendees)
        )
        
        if event and event.meet_link:
            return event.meet_link
        
        return None
    
    def get_upcoming_events(self, hours: int = 24) -> list[GoogleCalendarEvent]:
        """Get events happening in the next N hours."""
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(hours=hours)
        return self.list_events(time_min=now, time_max=time_max, calendar_id="all")
    
    def get_today_events(self) -> list[GoogleCalendarEvent]:
        """Get all events for today across all calendars."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        return self.list_events(time_min=start_of_day, time_max=end_of_day, calendar_id="all")
    
    # ========================================================================
    # Status & Test Methods
    # ========================================================================
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test the Google connection comprehensively.
        
        Returns:
            (success, message)
        """
        try:
            creds = self._get_credentials()
            
            # Test Gmail
            gmail = self._get_gmail_service()
            profile = gmail.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress", "")
            
            # Test Calendar
            calendars = self.list_calendars(use_cache=False)
            shared_count = sum(1 for c in calendars if c.is_shared)
            
            # Update state
            self._state["last_successful_connection"] = datetime.now().isoformat()
            self._save_state()
            
            return True, f"✅ Connected as {email} with {len(calendars)} calendars ({shared_count} shared)"
            
        except AuthorizationRequired:
            return False, "❌ Authorization required. Run: koda setup google"
        except FileNotFoundError as e:
            return False, f"❌ {str(e)}"
        except Exception as e:
            self._state["connection_failures"] = self._state.get("connection_failures", 0) + 1
            self._save_state()
            return False, f"❌ Connection failed: {e}"
    
    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status information."""
        status = {
            "configured": self.is_configured,
            "authorized": self.is_authorized,
            "email": None,
            "calendars": 0,
            "shared_calendars": 0,
            "credentials_file": str(self.credentials_file),
            "token_file": str(self.token_file),
            "last_refresh": self._state.get("last_refresh"),
            "refresh_count": self._state.get("refresh_count", 0),
            "connection_failures": self._state.get("connection_failures", 0),
            "last_successful_connection": self._state.get("last_successful_connection"),
        }
        
        if self.is_authorized:
            try:
                status["email"] = self.user_email
                calendars = self.list_calendars()
                status["calendars"] = len(calendars)
                status["shared_calendars"] = sum(1 for c in calendars if c.is_shared)
            except Exception as e:
                status["error"] = str(e)
        
        return status


class AuthorizationRequired(Exception):
    """Raised when Google authorization is needed."""
    pass


# Convenience functions

def get_google_client() -> GoogleWorkspaceClient:
    """Get a configured Google Workspace client."""
    return GoogleWorkspaceClient()


def is_google_configured() -> bool:
    """Check if Google is configured."""
    return GoogleWorkspaceClient().is_configured


def is_google_authorized() -> bool:
    """Check if Google is authorized."""
    return GoogleWorkspaceClient().is_authorized
