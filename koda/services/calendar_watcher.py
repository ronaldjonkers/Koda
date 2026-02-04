"""Calendar Watcher Service - Proactive calendar event notifications.

Monitors calendars for upcoming events and sends reminders via WhatsApp.
Alerts user about meetings before they start.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from loguru import logger


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    calendar_name: str = ""
    all_day: bool = False


@dataclass
class EventReminder:
    """A reminder for an upcoming event."""
    event: CalendarEvent
    remind_at: datetime
    minutes_before: int
    sent: bool = False


class CalendarWatcherService:
    """
    Service that monitors calendars and sends proactive reminders.
    
    Features:
    - Checks for upcoming events every 5 minutes
    - Sends reminders at configurable intervals (30m, 15m, 5m before)
    - Morning briefing with day's agenda
    - Supports multiple calendar sources
    """
    
    DEFAULT_REMINDER_MINUTES = [30, 15, 5]  # Minutes before event
    
    def __init__(
        self,
        on_notification: Callable[[str, str], asyncio.coroutine],
        owner_phone: str = "",
        enabled: bool = True,
        reminder_minutes: list[int] = None,
        morning_briefing: bool = True,
        morning_briefing_time: str = "08:00"
    ):
        self.on_notification = on_notification
        self.owner_phone = owner_phone
        self.enabled = enabled
        self.reminder_minutes = reminder_minutes or self.DEFAULT_REMINDER_MINUTES
        self.morning_briefing = morning_briefing
        self.morning_briefing_time = morning_briefing_time
        
        self._calendar_sources: list[Callable[[], list[CalendarEvent]]] = []
        self._sent_reminders: set[str] = set()  # Track sent reminder IDs
        self._last_briefing_date: Optional[datetime] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Quiet hours (no reminders during these hours)
        self._quiet_start = 23
        self._quiet_end = 7
    
    def set_quiet_hours(self, start: int, end: int) -> None:
        """Set quiet hours during which reminders are suppressed."""
        self._quiet_start = start
        self._quiet_end = end
    
    def _is_quiet_time(self) -> bool:
        """Check if current time is within quiet hours."""
        hour = datetime.now().hour
        if self._quiet_start > self._quiet_end:
            return hour >= self._quiet_start or hour < self._quiet_end
        return self._quiet_start <= hour < self._quiet_end
    
    def add_calendar_source(self, source: Callable[[], list[CalendarEvent]]) -> None:
        """Add a calendar source function that returns events."""
        self._calendar_sources.append(source)
    
    def add_google_caldav(self, email: str, app_password: str) -> bool:
        """Add Google Calendar via CalDAV."""
        try:
            from koda.integrations.google_caldav import GoogleCalDAVClient
            
            client = GoogleCalDAVClient(email, app_password)
            if not client.connect():
                return False
            
            def get_events() -> list[CalendarEvent]:
                """Get upcoming events from Google Calendar."""
                now = datetime.now()
                end = now + timedelta(days=1)
                events = client.get_events(start=now, end=end)
                return [
                    CalendarEvent(
                        uid=e.uid,
                        summary=e.summary,
                        start=e.start,
                        end=e.end,
                        location=e.location,
                        description=e.description,
                        calendar_name=e.calendar_name or "Google",
                        all_day=e.all_day
                    )
                    for e in events
                ]
            
            self._calendar_sources.append(get_events)
            logger.info(f"📅 Added Google Calendar source: {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add Google Calendar: {e}")
            return False
    
    def add_caldav(self, url: str, username: str, password: str, name: str = "CalDAV") -> bool:
        """Add generic CalDAV calendar."""
        try:
            from koda.integrations.caldav_client import CalDAVClient
            
            client = CalDAVClient(url, username, password)
            if not client.connect():
                return False
            
            def get_events() -> list[CalendarEvent]:
                """Get upcoming events from CalDAV."""
                now = datetime.now()
                end = now + timedelta(days=1)
                events = client.get_events(start=now, end=end)
                return [
                    CalendarEvent(
                        uid=e.uid,
                        summary=e.summary,
                        start=e.start,
                        end=e.end,
                        location=e.location,
                        description=e.description,
                        calendar_name=name,
                        all_day=e.all_day
                    )
                    for e in events
                ]
            
            self._calendar_sources.append(get_events)
            logger.info(f"📅 Added CalDAV source: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add CalDAV calendar: {e}")
            return False
    
    def _get_all_events(self) -> list[CalendarEvent]:
        """Get events from all calendar sources."""
        all_events = []
        for source in self._calendar_sources:
            try:
                events = source()
                all_events.extend(events)
            except Exception as e:
                logger.error(f"Error fetching calendar events: {e}")
        return all_events
    
    def _get_reminder_id(self, event: CalendarEvent, minutes_before: int) -> str:
        """Generate unique ID for a reminder."""
        return f"{event.uid}_{event.start.isoformat()}_{minutes_before}"
    
    def _should_send_reminder(self, event: CalendarEvent, minutes_before: int) -> bool:
        """Check if a reminder should be sent for this event."""
        now = datetime.now()
        remind_at = event.start - timedelta(minutes=minutes_before)
        
        # Check if it's time to send
        if now < remind_at:
            return False
        
        # Check if already sent
        reminder_id = self._get_reminder_id(event, minutes_before)
        if reminder_id in self._sent_reminders:
            return False
        
        # Don't send if event already started
        if now >= event.start:
            return False
        
        return True
    
    def _format_event_reminder(self, event: CalendarEvent, minutes_before: int) -> str:
        """Format a reminder message for an event."""
        time_str = event.start.strftime("%H:%M")
        
        if minutes_before >= 60:
            time_until = f"{minutes_before // 60} uur"
        else:
            time_until = f"{minutes_before} minuten"
        
        message = f"""⏰ *Agenda Herinnering*

📅 *{event.summary}*
🕐 Begint over {time_until} (om {time_str})"""
        
        if event.location:
            message += f"\n📍 {event.location}"
        
        if event.description:
            desc_preview = event.description[:100]
            if len(event.description) > 100:
                desc_preview += "..."
            message += f"\n\n_{desc_preview}_"
        
        return message
    
    def _format_morning_briefing(self, events: list[CalendarEvent]) -> str:
        """Format the morning briefing message."""
        today = datetime.now().strftime("%A %d %B")
        
        if not events:
            return f"""☀️ *Goedemorgen!*

📅 *{today}*

Je hebt vandaag geen afspraken gepland. Vrije dag! 🎉"""
        
        message = f"""☀️ *Goedemorgen!*

📅 *{today}*
Je hebt {len(events)} afspraak{"en" if len(events) > 1 else ""} vandaag:

"""
        
        for event in sorted(events, key=lambda e: e.start):
            time_str = event.start.strftime("%H:%M")
            if event.all_day:
                message += f"• 📌 *{event.summary}* (hele dag)\n"
            else:
                message += f"• *{time_str}* - {event.summary}"
                if event.location:
                    message += f" 📍 _{event.location}_"
                message += "\n"
        
        message += "\n_Ik stuur je een herinnering voor elke afspraak._"
        return message
    
    def _check_and_send_reminders(self) -> None:
        """Check for events that need reminders and send them."""
        if not self.enabled or self._is_quiet_time():
            return
        
        now = datetime.now()
        events = self._get_all_events()
        
        # Check morning briefing
        if self.morning_briefing:
            briefing_time = datetime.strptime(self.morning_briefing_time, "%H:%M").time()
            if (now.time() >= briefing_time and 
                (self._last_briefing_date is None or self._last_briefing_date.date() < now.date())):
                
                # Get today's events
                today_events = [
                    e for e in events 
                    if e.start.date() == now.date()
                ]
                
                message = self._format_morning_briefing(today_events)
                self._send_notification(message)
                self._last_briefing_date = now
        
        # Check event reminders
        for event in events:
            if event.all_day:
                continue  # Skip all-day events for time reminders
            
            for minutes_before in self.reminder_minutes:
                if self._should_send_reminder(event, minutes_before):
                    message = self._format_event_reminder(event, minutes_before)
                    self._send_notification(message)
                    
                    # Mark as sent
                    reminder_id = self._get_reminder_id(event, minutes_before)
                    self._sent_reminders.add(reminder_id)
        
        # Cleanup old reminder IDs (keep last 1000)
        if len(self._sent_reminders) > 1000:
            self._sent_reminders = set(list(self._sent_reminders)[-500:])
    
    def _send_notification(self, message: str) -> None:
        """Send a notification via WhatsApp."""
        if not self.owner_phone:
            return
        
        try:
            # Try to use existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    self.on_notification(self.owner_phone, message)
                )
            else:
                loop.run_until_complete(
                    self.on_notification(self.owner_phone, message)
                )
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self.on_notification(self.owner_phone, message)
            )
            loop.close()
    
    def _watch_loop(self) -> None:
        """Main watch loop - runs in background thread."""
        check_interval = 60  # Check every minute
        
        while self._running:
            try:
                self._check_and_send_reminders()
            except Exception as e:
                logger.error(f"Error in calendar watcher: {e}")
            
            time.sleep(check_interval)
    
    def start(self) -> None:
        """Start the calendar watcher."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"📅 Calendar watcher started ({len(self._calendar_sources)} sources)")
    
    def stop(self) -> None:
        """Stop the calendar watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("📅 Calendar watcher stopped")
    
    @property
    def source_count(self) -> int:
        """Number of calendar sources."""
        return len(self._calendar_sources)


def create_calendar_watcher_from_config(config, notification_callback) -> Optional[CalendarWatcherService]:
    """
    Create a CalendarWatcherService from the Koda config.
    
    Args:
        config: Koda configuration object
        notification_callback: Async function(phone, message) to send notifications
    
    Returns:
        CalendarWatcherService or None if no calendar accounts configured
    """
    try:
        owner_phone = config.channels.whatsapp.owner_phone
        if not owner_phone:
            logger.debug("No owner phone configured for calendar notifications")
            return None
        
        service = CalendarWatcherService(
            on_notification=notification_callback,
            owner_phone=owner_phone,
            enabled=True,
            morning_briefing=True
        )
        
        accounts = config.integrations.accounts or []
        calendars_added = 0
        
        for acc in accounts:
            # Handle both Pydantic models and dicts
            if hasattr(acc, 'model_dump'):
                acc_dict = acc.model_dump()
            elif isinstance(acc, dict):
                acc_dict = acc
            else:
                acc_dict = {}
            
            acc_type = acc_dict.get('type', '')
            capabilities = acc_dict.get('capabilities', [])
            
            if 'calendar' in capabilities or acc_type in ['google_caldav', 'caldav']:
                email = acc_dict.get('email', '')
                password = acc_dict.get('password', '')
                name = acc_dict.get('name', '')
                
                if acc_type == 'google_caldav' and email and password:
                    if service.add_google_caldav(email, password):
                        calendars_added += 1
                elif acc_type == 'caldav':
                    url = acc_dict.get('url', '')
                    username = acc_dict.get('username', email)
                    if url and username and password:
                        if service.add_caldav(url, username, password, name):
                            calendars_added += 1
        
        # Also check legacy Google config
        if config.integrations.google.enabled:
            # Google Calendar via OAuth (legacy) - would need separate implementation
            pass
        
        # Also check CalDAV config
        if config.integrations.caldav.enabled:
            url = config.integrations.caldav.url
            username = config.integrations.caldav.username
            password = config.integrations.caldav.password
            if url and username and password:
                if service.add_caldav(url, username, password, "CalDAV"):
                    calendars_added += 1
        
        if calendars_added == 0:
            logger.debug("No calendar accounts configured for watching")
            return None
        
        return service
        
    except Exception as e:
        logger.error(f"Failed to create calendar watcher: {e}")
        return None
