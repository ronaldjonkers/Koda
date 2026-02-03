"""CalDAV calendar integration client.

Supports: Nextcloud, ownCloud, Radicale, Baikal, macOS Server, and other CalDAV servers.
"""

from datetime import datetime, timedelta
from typing import Any
from dataclasses import dataclass

from loguru import logger

try:
    import caldav
    from caldav.elements import dav
    CALDAV_AVAILABLE = True
except ImportError:
    CALDAV_AVAILABLE = False


@dataclass
class CalDAVEvent:
    """Represents a CalDAV calendar event."""
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str | None = None
    description: str | None = None
    all_day: bool = False


class CalDAVClient:
    """
    CalDAV client for accessing calendar servers.
    
    Compatible with most CalDAV implementations including:
    - Nextcloud
    - ownCloud
    - Radicale
    - Baikal
    - macOS Server
    - FastMail
    - Fruux
    """
    
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        calendar_path: str = ""
    ):
        if not CALDAV_AVAILABLE:
            raise ImportError("caldav package is required. Install with: pip install caldav")
        
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.calendar_path = calendar_path
        self._client: caldav.DAVClient | None = None
        self._calendar: caldav.Calendar | None = None
    
    def connect(self) -> bool:
        """Connect to the CalDAV server."""
        try:
            self._client = caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password
            )
            
            principal = self._client.principal()
            calendars = principal.calendars()
            
            if not calendars:
                logger.warning("No calendars found on CalDAV server")
                return False
            
            # Find the specified calendar or use the first one
            if self.calendar_path:
                for cal in calendars:
                    if self.calendar_path in str(cal.url):
                        self._calendar = cal
                        break
            
            if not self._calendar:
                self._calendar = calendars[0]
            
            logger.info(f"Connected to CalDAV calendar: {self._calendar.name}")
            return True
        
        except Exception as e:
            logger.error(f"CalDAV connection failed: {e}")
            return False
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the CalDAV connection and return status."""
        try:
            if self.connect():
                cal_name = self._calendar.name if self._calendar else "Unknown"
                return True, f"Connected to calendar: {cal_name}"
            return False, "Failed to connect to CalDAV server"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def list_calendars(self) -> list[dict[str, str]]:
        """List all available calendars."""
        if not self._client:
            self.connect()
        
        try:
            principal = self._client.principal()
            calendars = principal.calendars()
            
            return [
                {
                    "name": cal.name or "Unnamed",
                    "url": str(cal.url),
                    "color": getattr(cal, "calendar_color", None)
                }
                for cal in calendars
            ]
        except Exception as e:
            logger.error(f"Failed to list calendars: {e}")
            return []
    
    def get_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        days_ahead: int = 7
    ) -> list[CalDAVEvent]:
        """Get events from the calendar."""
        if not self._calendar:
            if not self.connect():
                return []
        
        if not start:
            start = datetime.now()
        if not end:
            end = start + timedelta(days=days_ahead)
        
        try:
            events = self._calendar.date_search(
                start=start,
                end=end,
                expand=True
            )
            
            result = []
            for event in events:
                try:
                    vevent = event.vobject_instance.vevent
                    
                    event_start = vevent.dtstart.value
                    event_end = vevent.dtend.value if hasattr(vevent, "dtend") else event_start
                    
                    # Check if all-day event
                    all_day = not isinstance(event_start, datetime)
                    if all_day:
                        event_start = datetime.combine(event_start, datetime.min.time())
                        event_end = datetime.combine(event_end, datetime.min.time())
                    
                    result.append(CalDAVEvent(
                        uid=str(vevent.uid.value) if hasattr(vevent, "uid") else "",
                        summary=str(vevent.summary.value) if hasattr(vevent, "summary") else "No title",
                        start=event_start,
                        end=event_end,
                        location=str(vevent.location.value) if hasattr(vevent, "location") else None,
                        description=str(vevent.description.value) if hasattr(vevent, "description") else None,
                        all_day=all_day
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse event: {e}")
                    continue
            
            return sorted(result, key=lambda e: e.start)
        
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return []
    
    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        location: str | None = None,
        description: str | None = None,
        all_day: bool = False
    ) -> str | None:
        """Create a new calendar event. Returns the event UID."""
        if not self._calendar:
            if not self.connect():
                return None
        
        try:
            import uuid
            from icalendar import Calendar, Event, vDatetime, vDate
            
            cal = Calendar()
            cal.add("prodid", "-//Koda Assistant//EN")
            cal.add("version", "2.0")
            
            event = Event()
            event.add("uid", str(uuid.uuid4()))
            event.add("summary", summary)
            
            if all_day:
                event.add("dtstart", start.date())
                event.add("dtend", end.date())
            else:
                event.add("dtstart", start)
                event.add("dtend", end)
            
            if location:
                event.add("location", location)
            if description:
                event.add("description", description)
            
            event.add("dtstamp", datetime.now())
            cal.add_component(event)
            
            self._calendar.save_event(cal.to_ical().decode("utf-8"))
            
            return str(event["uid"])
        
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return None
    
    def delete_event(self, uid: str) -> bool:
        """Delete an event by UID."""
        if not self._calendar:
            if not self.connect():
                return False
        
        try:
            event = self._calendar.event_by_uid(uid)
            event.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return False
