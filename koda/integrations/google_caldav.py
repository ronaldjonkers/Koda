"""Google Calendar via CalDAV with App Password authentication.

This provides a simpler alternative to OAuth - works like a mail client.
Requires: 2FA enabled + App Password generated.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass

from loguru import logger

try:
    import caldav
    CALDAV_AVAILABLE = True
except ImportError:
    CALDAV_AVAILABLE = False


# Google's CalDAV endpoint
GOOGLE_CALDAV_URL = "https://apidata.googleusercontent.com/caldav/v2/{email}/user"


@dataclass
class GoogleCalendarEvent:
    """Represents a Google Calendar event."""
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False
    calendar_name: Optional[str] = None


class GoogleCalDAVClient:
    """
    Google Calendar client using CalDAV protocol with App Password.
    
    This is simpler than OAuth - works like configuring a mail client.
    
    Setup steps:
    1. Enable 2-Step Verification on Google Account
    2. Go to https://myaccount.google.com/apppasswords
    3. Generate an App Password (select "Other" and name it "Koda")
    4. Use that 16-character password here
    
    Benefits:
    - No Google Cloud Console project needed
    - No OAuth tokens to manage
    - No credentials.json file needed
    - Works indefinitely (until you revoke the app password)
    """
    
    SETUP_INSTRUCTIONS = """
## Google Calendar Setup (CalDAV met App Wachtwoord)

Dit is de eenvoudigste manier om Google Calendar te koppelen - geen API keys of OAuth nodig!

### Stap 1: 2-Stapsverificatie Inschakelen
1. Ga naar https://myaccount.google.com/security
2. Zorg dat "2-Stapsverificatie" is ingeschakeld

### Stap 2: App Wachtwoord Aanmaken
1. Ga naar https://myaccount.google.com/apppasswords
2. Klik op "App selecteren" → kies "Overige (aangepaste naam)"
3. Voer in: "Koda" (of een andere naam)
4. Klik op "Genereren"
5. Je krijgt een **16-letter wachtwoord** (bijv: "abcd efgh ijkl mnop")

### Stap 3: Configureren
Gebruik het commando:
```
/addgoogle jouw.email@gmail.com abcdefghijklmnop
```

Of via config.json:
```json
{
  "integrations": {
    "google_caldav": {
      "enabled": true,
      "email": "jouw.email@gmail.com",
      "app_password": "abcdefghijklmnop"
    }
  }
}
```

### Belangrijk
- Het App Wachtwoord is 16 letters (zonder spaties)
- Bewaar het veilig - je kunt het niet opnieuw bekijken
- Je kunt het altijd intrekken via myaccount.google.com/apppasswords
"""
    
    def __init__(self, email: str, app_password: str):
        if not CALDAV_AVAILABLE:
            raise ImportError("caldav package required. Run: pip install caldav")
        
        self.email = email
        self.app_password = app_password.replace(" ", "")  # Remove spaces
        self.url = GOOGLE_CALDAV_URL.format(email=email)
        self._client: Optional[caldav.DAVClient] = None
        self._calendars: list = []
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to Google Calendar via CalDAV."""
        try:
            self._client = caldav.DAVClient(
                url=self.url,
                username=self.email,
                password=self.app_password
            )
            
            principal = self._client.principal()
            self._calendars = principal.calendars()
            
            if not self._calendars:
                logger.warning("No calendars found")
                return False
            
            self._connected = True
            logger.info(f"Connected to Google Calendar ({self.email}), found {len(self._calendars)} calendar(s)")
            return True
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                logger.error("Authentication failed. Check your email and app password.")
                logger.error("Make sure 2FA is enabled and you're using an App Password, not your regular password.")
            else:
                logger.error(f"Google CalDAV connection failed: {e}")
            return False
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection and return status message."""
        try:
            if self.connect():
                cal_names = [c.name for c in self._calendars]
                return True, f"Connected! Found calendars: {', '.join(cal_names)}"
            return False, "Connection failed - no calendars found"
        except Exception as e:
            return False, f"Connection failed: {e}"
    
    def list_calendars(self) -> list[dict]:
        """List all available calendars."""
        if not self._connected:
            self.connect()
        
        return [
            {"name": cal.name, "url": str(cal.url)}
            for cal in self._calendars
        ]
    
    def get_calendar(self, name: Optional[str] = None) -> Optional[caldav.Calendar]:
        """Get calendar by name, or primary calendar if not specified."""
        if not self._connected:
            self.connect()
        
        if not self._calendars:
            return None
        
        if name:
            for cal in self._calendars:
                if cal.name and name.lower() in cal.name.lower():
                    return cal
        
        # Return primary calendar (usually first, or one matching email)
        for cal in self._calendars:
            if self.email in str(cal.url):
                return cal
        
        return self._calendars[0]
    
    def get_events(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        calendar_name: Optional[str] = None
    ) -> list[GoogleCalendarEvent]:
        """Get events within a date range."""
        calendar = self.get_calendar(calendar_name)
        if not calendar:
            return []
        
        start = start or datetime.now()
        end = end or (start + timedelta(days=7))
        
        try:
            events = calendar.date_search(start=start, end=end, expand=True)
            result = []
            
            for event in events:
                try:
                    vevent = event.vobject_instance.vevent
                    
                    # Parse start/end times
                    ev_start = vevent.dtstart.value
                    ev_end = vevent.dtend.value if hasattr(vevent, 'dtend') else ev_start
                    
                    # Check if all-day event
                    all_day = not isinstance(ev_start, datetime)
                    if all_day:
                        ev_start = datetime.combine(ev_start, datetime.min.time())
                        ev_end = datetime.combine(ev_end, datetime.min.time())
                    
                    result.append(GoogleCalendarEvent(
                        uid=str(vevent.uid.value) if hasattr(vevent, 'uid') else "",
                        summary=str(vevent.summary.value) if hasattr(vevent, 'summary') else "Untitled",
                        start=ev_start,
                        end=ev_end,
                        location=str(vevent.location.value) if hasattr(vevent, 'location') else None,
                        description=str(vevent.description.value) if hasattr(vevent, 'description') else None,
                        all_day=all_day,
                        calendar_name=calendar.name
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing event: {e}")
                    continue
            
            return sorted(result, key=lambda e: e.start)
            
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
            return []
    
    def get_today_events(self, calendar_name: Optional[str] = None) -> list[GoogleCalendarEvent]:
        """Get today's events."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.get_events(start=today, end=tomorrow, calendar_name=calendar_name)
    
    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        location: Optional[str] = None,
        description: Optional[str] = None,
        calendar_name: Optional[str] = None
    ) -> Optional[str]:
        """Create a new calendar event. Returns event UID."""
        calendar = self.get_calendar(calendar_name)
        if not calendar:
            logger.error("No calendar available")
            return None
        
        try:
            event = calendar.save_event(
                dtstart=start,
                dtend=end,
                summary=summary,
                location=location,
                description=description
            )
            
            # Extract UID
            uid = None
            if hasattr(event, 'vobject_instance'):
                vevent = event.vobject_instance.vevent
                if hasattr(vevent, 'uid'):
                    uid = str(vevent.uid.value)
            
            logger.info(f"Created event: {summary}")
            return uid
            
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return None
    
    def delete_event(self, uid: str, calendar_name: Optional[str] = None) -> bool:
        """Delete an event by UID."""
        calendar = self.get_calendar(calendar_name)
        if not calendar:
            return False
        
        try:
            # Search for the event
            events = calendar.events()
            for event in events:
                try:
                    vevent = event.vobject_instance.vevent
                    if hasattr(vevent, 'uid') and str(vevent.uid.value) == uid:
                        event.delete()
                        logger.info(f"Deleted event: {uid}")
                        return True
                except:
                    continue
            
            logger.warning(f"Event not found: {uid}")
            return False
            
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return False


def setup_google_caldav(email: str, app_password: str) -> tuple[bool, str]:
    """
    Setup and test Google CalDAV connection.
    
    Returns (success, message).
    """
    try:
        client = GoogleCalDAVClient(email, app_password)
        success, message = client.test_connection()
        
        if success:
            # Save to config
            from koda.config.loader import load_config, save_config
            config = load_config()
            
            # Update config
            if not hasattr(config.integrations, 'google_caldav'):
                # Add to config if not exists
                pass
            
            return True, f"✅ Google Calendar gekoppeld!\n{message}"
        else:
            return False, f"❌ Verbinding mislukt: {message}\n\n{GoogleCalDAVClient.SETUP_INSTRUCTIONS}"
            
    except Exception as e:
        return False, f"❌ Error: {e}\n\n{GoogleCalDAVClient.SETUP_INSTRUCTIONS}"
