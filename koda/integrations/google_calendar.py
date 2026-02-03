"""Google Calendar integration client."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


class GoogleCalendarClient:
    """Client for Google Calendar API operations."""
    
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    
    def __init__(
        self,
        credentials_file: str = "~/.koda/google_credentials.json",
        token_file: str = "~/.koda/google_token.json",
        calendar_ids: list[str] | None = None
    ):
        self.credentials_file = Path(credentials_file).expanduser()
        self.token_file = Path(token_file).expanduser()
        self.calendar_ids = calendar_ids or ["primary"]
        self._service = None
    
    def _get_service(self):
        """Get or create the Google Calendar service."""
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
        
        self._service = build("calendar", "v3", credentials=creds)
        return self._service
    
    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int = 10
    ) -> list[dict[str, Any]]:
        """
        List calendar events.
        
        Args:
            calendar_id: Calendar ID (default: primary)
            time_min: Start time filter (default: now)
            time_max: End time filter (default: 7 days from now)
            max_results: Maximum number of events to return
        
        Returns:
            List of event dictionaries
        """
        service = self._get_service()
        
        if time_min is None:
            time_min = datetime.utcnow()
        if time_max is None:
            time_max = time_min + timedelta(days=7)
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat() + "Z",
            timeMax=time_max.isoformat() + "Z",
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        events = events_result.get("items", [])
        
        return [
            {
                "id": e.get("id"),
                "summary": e.get("summary", "(No title)"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date")),
                "location": e.get("location"),
                "description": e.get("description"),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
                "status": e.get("status"),
            }
            for e in events
        ]
    
    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        add_meet_link: bool = False
    ) -> dict[str, Any]:
        """
        Create a calendar event.
        
        Args:
            summary: Event title
            start: Start datetime
            end: End datetime
            calendar_id: Calendar ID
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            add_meet_link: If True, add a Google Meet video conference link
        
        Returns:
            Created event details including meet_link if requested
        """
        service = self._get_service()
        
        event = {
            "summary": summary,
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Amsterdam"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Amsterdam"},
        }
        
        if description:
            event["description"] = description
        if location:
            event["location"] = location
        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]
        
        # Add Google Meet conference link
        if add_meet_link:
            event["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet-{start.timestamp()}-{hash(summary) % 10000}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}
                }
            }
        
        # Use conferenceDataVersion=1 to enable Meet link creation
        result = service.events().insert(
            calendarId=calendar_id,
            body=event,
            conferenceDataVersion=1 if add_meet_link else 0
        ).execute()
        
        logger.info(f"Created event: {result.get('summary')} ({result.get('id')})")
        
        # Extract Meet link if available
        meet_link = None
        conference_data = result.get("conferenceData", {})
        entry_points = conference_data.get("entryPoints", [])
        for ep in entry_points:
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")
                break
        
        return {
            "id": result.get("id"),
            "summary": result.get("summary"),
            "htmlLink": result.get("htmlLink"),
            "start": result.get("start"),
            "end": result.get("end"),
            "meet_link": meet_link,
        }
    
    def get_today_events(self, calendar_id: str = "primary") -> list[dict[str, Any]]:
        """Get all events for today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.list_events(calendar_id, time_min=today, time_max=tomorrow, max_results=50)
    
    def get_upcoming_events(self, days: int = 7, calendar_id: str = "primary") -> list[dict[str, Any]]:
        """Get upcoming events for the next N days."""
        now = datetime.utcnow()
        future = now + timedelta(days=days)
        return self.list_events(calendar_id, time_min=now, time_max=future, max_results=100)
    
    def list_calendars(self) -> list[dict[str, str]]:
        """List all available calendars."""
        service = self._get_service()
        calendar_list = service.calendarList().list().execute()
        
        return [
            {
                "id": c.get("id"),
                "summary": c.get("summary"),
                "primary": c.get("primary", False),
            }
            for c in calendar_list.get("items", [])
        ]
