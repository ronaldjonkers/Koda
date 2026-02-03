"""Calendar tools for Google and Exchange calendars."""

from datetime import datetime, timedelta
from typing import Any

from koda.core.tools.base import Tool


class GoogleCalendarTool(Tool):
    """Tool for Google Calendar operations."""
    
    name = "google_calendar"
    description = """Access Google Calendar to list, view, and create events.
    
Actions:
- list: List upcoming events (default: next 7 days)
- today: Get today's events
- create: Create a new event
- calendars: List available calendars

Examples:
- List events: {"action": "list", "days": 7}
- Today's events: {"action": "today"}
- Create event: {"action": "create", "summary": "Meeting", "start": "2024-01-15T10:00:00", "end": "2024-01-15T11:00:00"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "today", "create", "calendars"],
                "description": "Action to perform"
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead (for list action)"
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID (default: primary)"
            },
            "summary": {
                "type": "string",
                "description": "Event title (for create action)"
            },
            "start": {
                "type": "string",
                "description": "Start datetime ISO format (for create action)"
            },
            "end": {
                "type": "string",
                "description": "End datetime ISO format (for create action)"
            },
            "description": {
                "type": "string",
                "description": "Event description (for create action)"
            },
            "location": {
                "type": "string",
                "description": "Event location (for create action)"
            },
        },
        "required": ["action"]
    }
    
    def __init__(self, credentials_file: str | None = None, token_file: str | None = None):
        self.credentials_file = credentials_file or "~/.koda/google_credentials.json"
        self.token_file = token_file or "~/.koda/google_token.json"
        self._client = None
    
    def _get_client(self):
        if not self._client:
            from koda.integrations.google_calendar import GoogleCalendarClient
            self._client = GoogleCalendarClient(
                credentials_file=self.credentials_file,
                token_file=self.token_file
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        calendar_id = kwargs.get("calendar_id", "primary")
        
        try:
            client = self._get_client()
            
            if action == "list":
                days = kwargs.get("days", 7)
                events = client.get_upcoming_events(days=days, calendar_id=calendar_id)
                return self._format_events(events)
            
            elif action == "today":
                events = client.get_today_events(calendar_id=calendar_id)
                return self._format_events(events, "Today's events")
            
            elif action == "calendars":
                calendars = client.list_calendars()
                output = "Available calendars:\n"
                for cal in calendars:
                    primary = " (primary)" if cal.get("primary") else ""
                    output += f"- {cal['summary']}{primary}\n  ID: {cal['id']}\n"
                return output
            
            elif action == "create":
                summary = kwargs.get("summary")
                start_str = kwargs.get("start")
                end_str = kwargs.get("end")
                
                if not all([summary, start_str, end_str]):
                    return "Error: Missing required fields: summary, start, end"
                
                start = datetime.fromisoformat(start_str)
                end = datetime.fromisoformat(end_str)
                
                result = client.create_event(
                    summary=summary,
                    start=start,
                    end=end,
                    calendar_id=calendar_id,
                    description=kwargs.get("description"),
                    location=kwargs.get("location")
                )
                
                return f"Created event: {result['summary']}\nLink: {result.get('htmlLink', 'N/A')}"
            
            else:
                return f"Error: Unknown action: {action}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _format_events(self, events: list, title: str = "Upcoming events") -> str:
        if not events:
            return f"{title}: No events found."
        
        output = f"{title} ({len(events)}):\n\n"
        for e in events:
            start = e.get("start", "")
            if "T" in str(start):
                start = datetime.fromisoformat(start.replace("Z", "")).strftime("%Y-%m-%d %H:%M")
            output += f"• {e['summary']}\n"
            output += f"  When: {start}\n"
            if e.get("location"):
                output += f"  Where: {e['location']}\n"
            output += "\n"
        
        return output


class ExchangeCalendarTool(Tool):
    """Tool for Exchange Calendar operations."""
    
    name = "exchange_calendar"
    description = """Access Exchange/Outlook Calendar to list, view, and create events.
    
Actions:
- list: List upcoming events (default: next 7 days)
- today: Get today's events
- create: Create a new event

Examples:
- List events: {"action": "list", "days": 7}
- Today's events: {"action": "today"}
- Create event: {"action": "create", "subject": "Meeting", "start": "2024-01-15T10:00:00", "end": "2024-01-15T11:00:00"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "today", "create"],
                "description": "Action to perform"
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead (for list action)"
            },
            "subject": {
                "type": "string",
                "description": "Event subject (for create action)"
            },
            "start": {
                "type": "string",
                "description": "Start datetime ISO format (for create action)"
            },
            "end": {
                "type": "string",
                "description": "End datetime ISO format (for create action)"
            },
            "body": {
                "type": "string",
                "description": "Event body/description (for create action)"
            },
            "location": {
                "type": "string",
                "description": "Event location (for create action)"
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
        action = kwargs.get("action", "list")
        
        try:
            client = self._get_client()
            
            if action == "list":
                days = kwargs.get("days", 7)
                now = datetime.now()
                events = client.list_calendar_events(
                    start=now,
                    end=now + timedelta(days=days)
                )
                return self._format_events(events)
            
            elif action == "today":
                events = client.get_today_events()
                return self._format_events(events, "Today's events")
            
            elif action == "create":
                subject = kwargs.get("subject")
                start_str = kwargs.get("start")
                end_str = kwargs.get("end")
                
                if not all([subject, start_str, end_str]):
                    return "Error: Missing required fields: subject, start, end"
                
                start = datetime.fromisoformat(start_str)
                end = datetime.fromisoformat(end_str)
                
                result = client.create_calendar_event(
                    subject=subject,
                    start=start,
                    end=end,
                    body=kwargs.get("body"),
                    location=kwargs.get("location")
                )
                
                return f"Created event: {result['subject']}"
            
            else:
                return f"Error: Unknown action: {action}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _format_events(self, events: list, title: str = "Upcoming events") -> str:
        if not events:
            return f"{title}: No events found."
        
        output = f"{title} ({len(events)}):\n\n"
        for e in events:
            start = e.get("start", "")
            if start:
                try:
                    start = datetime.fromisoformat(start).strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            output += f"• {e.get('subject', '(No title)')}\n"
            output += f"  When: {start}\n"
            if e.get("location"):
                output += f"  Where: {e['location']}\n"
            output += "\n"
        
        return output
