"""CalDAV calendar tool for the agent."""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class CalDAVTool(BaseTool):
    """
    Tool for interacting with CalDAV calendars.
    
    Supports Nextcloud, ownCloud, Radicale, Baikal, and other CalDAV servers.
    """
    
    name = "caldav_calendar"
    description = """Access CalDAV calendars (Nextcloud, ownCloud, Radicale, etc.). Use this to:
- View upcoming events from CalDAV calendars
- Create new calendar events
- Delete events
- List available calendars

Actions:
- list_events: Get events for a time range
- create_event: Create a new event
- delete_event: Delete an event by UID
- list_calendars: Show available calendars"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_events", "create_event", "delete_event", "list_calendars"],
                "description": "The calendar operation to perform"
            },
            "days_ahead": {
                "type": "integer",
                "description": "For list_events: number of days to look ahead (default: 7)"
            },
            "summary": {
                "type": "string",
                "description": "For create_event: event title"
            },
            "start": {
                "type": "string",
                "description": "For create_event: start time (ISO format or natural language)"
            },
            "end": {
                "type": "string",
                "description": "For create_event: end time (ISO format or natural language)"
            },
            "location": {
                "type": "string",
                "description": "For create_event: event location"
            },
            "description": {
                "type": "string",
                "description": "For create_event: event description"
            },
            "all_day": {
                "type": "boolean",
                "description": "For create_event: whether it's an all-day event"
            },
            "uid": {
                "type": "string",
                "description": "For delete_event: event UID to delete"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, url: str = "", username: str = "", password: str = "", calendar_path: str = ""):
        self.url = url
        self.username = username
        self.password = password
        self.calendar_path = calendar_path
        self._client = None
    
    def _get_client(self):
        """Get or create CalDAV client."""
        if not self._client:
            from koda.integrations.caldav_client import CalDAVClient
            self._client = CalDAVClient(
                self.url,
                self.username,
                self.password,
                self.calendar_path
            )
        return self._client
    
    async def execute(self, **kwargs) -> str:
        """Execute a CalDAV calendar operation."""
        if not self.url:
            return "CalDAV not configured. Run 'koda config caldav' to set up."
        
        action = kwargs.get("action")
        
        try:
            if action == "list_events":
                return await self._list_events(kwargs.get("days_ahead", 7))
            
            elif action == "create_event":
                return await self._create_event(
                    summary=kwargs.get("summary", ""),
                    start=kwargs.get("start", ""),
                    end=kwargs.get("end", ""),
                    location=kwargs.get("location"),
                    description=kwargs.get("description"),
                    all_day=kwargs.get("all_day", False)
                )
            
            elif action == "delete_event":
                return await self._delete_event(kwargs.get("uid", ""))
            
            elif action == "list_calendars":
                return await self._list_calendars()
            
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            logger.error(f"CalDAV operation failed: {e}")
            return f"Error: {str(e)}"
    
    async def _list_events(self, days_ahead: int) -> str:
        """List upcoming events."""
        client = self._get_client()
        events = client.get_events(days_ahead=days_ahead)
        
        if not events:
            return f"No events found in the next {days_ahead} days."
        
        output = [f"**Upcoming Events ({len(events)}):**\n"]
        
        for event in events:
            if event.all_day:
                time_str = event.start.strftime("%Y-%m-%d") + " (all day)"
            else:
                time_str = event.start.strftime("%Y-%m-%d %H:%M") + " - " + event.end.strftime("%H:%M")
            
            output.append(f"- **{event.summary}**")
            output.append(f"  📅 {time_str}")
            if event.location:
                output.append(f"  📍 {event.location}")
            output.append("")
        
        return "\n".join(output)
    
    async def _create_event(
        self,
        summary: str,
        start: str,
        end: str,
        location: str | None,
        description: str | None,
        all_day: bool
    ) -> str:
        """Create a new event."""
        if not summary:
            return "Error: 'summary' (event title) is required"
        if not start:
            return "Error: 'start' time is required"
        
        # Parse times
        try:
            start_dt = self._parse_datetime(start)
            if end:
                end_dt = self._parse_datetime(end)
            else:
                end_dt = start_dt + timedelta(hours=1)
        except ValueError as e:
            return f"Error parsing time: {e}"
        
        client = self._get_client()
        uid = client.create_event(
            summary=summary,
            start=start_dt,
            end=end_dt,
            location=location,
            description=description,
            all_day=all_day
        )
        
        if uid:
            return f"✓ Event created: {summary} on {start_dt.strftime('%Y-%m-%d %H:%M')}"
        else:
            return "Failed to create event"
    
    async def _delete_event(self, uid: str) -> str:
        """Delete an event."""
        if not uid:
            return "Error: 'uid' is required"
        
        client = self._get_client()
        if client.delete_event(uid):
            return f"✓ Event deleted: {uid}"
        else:
            return f"Failed to delete event: {uid}"
    
    async def _list_calendars(self) -> str:
        """List available calendars."""
        client = self._get_client()
        calendars = client.list_calendars()
        
        if not calendars:
            return "No calendars found."
        
        output = [f"**Available Calendars ({len(calendars)}):**\n"]
        for cal in calendars:
            output.append(f"- {cal['name']}")
            output.append(f"  URL: {cal['url']}")
        
        return "\n".join(output)
    
    def _parse_datetime(self, value: str) -> datetime:
        """Parse datetime from string."""
        # Try ISO format first
        for fmt in [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d"
        ]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Cannot parse datetime: {value}")
