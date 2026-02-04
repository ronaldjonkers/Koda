"""Google Meet tool for creating video conference links."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

from koda.core.tools.base import BaseTool


class GoogleMeetTool(BaseTool):
    """
    Tool for creating Google Meet links.
    
    This tool creates Google Meet video conference links, either standalone
    or attached to calendar events. Requires Google Workspace to be configured.
    """
    
    name = "google_meet"
    description = """Create Google Meet video conference links.

Use this tool when the user asks to:
- Create a Google Meet link
- Set up a video call/meeting
- Get a meeting room for a call
- Add a Meet link to a calendar event

Actions:
- create: Create a new Meet link (creates a calendar event with Meet attached)
- add_to_event: Add Meet link to an existing calendar event

Parameters for 'create':
- title: Meeting title (required)
- start: Start datetime ISO format (optional, defaults to now)
- duration_minutes: Duration in minutes (optional, defaults to 60)
- attendees: List of attendee emails to invite

Parameters for 'add_to_event':
- event_id: The calendar event ID to add Meet link to
- calendar_id: Calendar ID (optional, defaults to primary)
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "add_to_event"],
                "description": "Action to perform"
            },
            "title": {
                "type": "string",
                "description": "Meeting title"
            },
            "start": {
                "type": "string",
                "description": "Start datetime ISO format"
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Duration in minutes (default 60)"
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses"
            },
            "event_id": {
                "type": "string",
                "description": "Event ID to add Meet link to"
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID (default: primary)"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self._client = None
        self._available = False
        self._init_client()
    
    def _init_client(self):
        """Initialize Google Workspace client if available."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            if status.get("authorized"):
                self._client = client
                self._available = True
                logger.debug("Google Meet tool initialized with Workspace client")
        except Exception as e:
            logger.debug(f"Google Workspace not available for Meet: {e}")
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "create")
        
        if not self._available:
            return """❌ **Google Workspace niet verbonden**

Om Google Meet links te maken moet je eerst Google Workspace koppelen:

1. Run: `koda setup-google`
2. Of open het dashboard → Google tab

Na koppeling kun je:
- Meet links maken voor vergaderingen
- Automatisch Meet links toevoegen aan afspraken"""
        
        try:
            if action == "create":
                return await self._create_meet(**kwargs)
            elif action == "add_to_event":
                return await self._add_meet_to_event(**kwargs)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Google Meet error: {e}")
            return f"❌ Error: {e}"
    
    async def _create_meet(self, **kwargs) -> str:
        """Create a new meeting with Google Meet link."""
        title = kwargs.get("title", "Meeting")
        start_str = kwargs.get("start")
        duration = kwargs.get("duration_minutes", 60)
        attendees = kwargs.get("attendees", [])
        
        # Parse or default start time
        if start_str:
            try:
                start = datetime.fromisoformat(start_str)
            except ValueError:
                return "❌ Invalid start time format. Use ISO format (e.g., 2024-01-15T14:00:00)"
        else:
            # Default to now, rounded to next 15 minutes
            now = datetime.now()
            minutes = (now.minute // 15 + 1) * 15
            start = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
        
        end = start + timedelta(minutes=duration)
        
        # Create event with Meet link
        event = self._client.create_event(
            summary=title,
            start=start,
            end=end,
            attendees=attendees if attendees else None,
            add_meet_link=True,
            send_notifications=bool(attendees)
        )
        
        if not event:
            return "❌ Failed to create meeting"
        
        # Build response
        output = [f"✅ **Meeting aangemaakt:** {title}"]
        output.append(f"📅 {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')}")
        
        if event.meet_link:
            output.append(f"\n🔗 **Google Meet link:**")
            output.append(f"`{event.meet_link}`")
        
        if attendees:
            output.append(f"\n👥 Uitnodigingen verstuurd naar: {', '.join(attendees)}")
        
        return "\n".join(output)
    
    async def _add_meet_to_event(self, **kwargs) -> str:
        """Add Meet link to an existing calendar event."""
        event_id = kwargs.get("event_id")
        calendar_id = kwargs.get("calendar_id", "primary")
        
        if not event_id:
            return "❌ Event ID is required. Use the calendar tool to find event IDs."
        
        # Update event with Meet link
        event = self._client.update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            add_meet_link=True
        )
        
        if not event:
            return f"❌ Failed to add Meet link to event {event_id}"
        
        output = [f"✅ **Meet link toegevoegd aan:** {event.summary}"]
        
        if event.meet_link:
            output.append(f"\n🔗 **Google Meet link:**")
            output.append(f"`{event.meet_link}`")
        
        return "\n".join(output)
