"""Proactive Reminder Service - Your AI Executive Assistant's memory.

This service continuously monitors:
- Upcoming calendar events and sends reminders
- Birthdays and special occasions
- Important emails that need attention
- Tasks and deadlines
- User preferences and patterns

It operates as a background service that sends proactive notifications
via WhatsApp, Telegram, or email based on configured preferences.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger


class ReminderType(str, Enum):
    """Types of proactive reminders."""
    CALENDAR = "calendar"           # Upcoming appointments
    BIRTHDAY = "birthday"           # Birthday reminders
    EMAIL = "email"                 # Important emails
    TASK = "task"                   # Task/deadline reminders
    MORNING_BRIEFING = "morning"    # Daily morning summary
    CUSTOM = "custom"               # User-defined reminders


class ReminderPriority(str, Enum):
    """Priority levels for reminders."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProactiveReminder:
    """A proactive reminder."""
    id: str
    type: ReminderType
    title: str
    message: str
    scheduled_time: datetime
    priority: ReminderPriority = ReminderPriority.NORMAL
    channel: str = "whatsapp"  # whatsapp, telegram, email
    recipient: str = ""        # phone number or email
    sent: bool = False
    sent_at: Optional[datetime] = None
    snooze_until: Optional[datetime] = None
    related_event_id: Optional[str] = None  # For calendar reminders
    metadata: dict = field(default_factory=dict)


@dataclass
class ProactiveReminderConfig:
    """Configuration for the proactive reminder service."""
    # Calendar reminders
    calendar_reminders_enabled: bool = True
    calendar_default_minutes_before: int = 15
    calendar_morning_check_time: str = "08:00"
    
    # Birthday reminders
    birthday_reminders_enabled: bool = True
    birthday_days_before: int = 1
    birthday_send_time: str = "09:00"
    
    # Special occasions
    special_occasions_enabled: bool = True
    
    # Email digest
    email_digest_enabled: bool = True
    email_digest_time: str = "08:30"
    
    # Default settings
    default_channel: str = "whatsapp"
    default_recipient: str = ""
    
    # Quiet hours
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    respect_quiet_hours: bool = True


class ProactiveReminderService:
    """
    Proactive reminder service that sends notifications before events.
    
    This is like having an executive assistant who:
    - Reminds you of upcoming meetings
    - Alerts you to birthdays
    - Gives you a morning briefing
    - Flags important emails
    """
    
    def __init__(
        self,
        config: ProactiveReminderConfig,
        send_callback: Callable[[str, str, str], Any],
        storage_path: Optional[Path] = None,
        timezone: str = "Europe/Amsterdam"
    ):
        self.config = config
        self.send_callback = send_callback
        self.storage_path = storage_path or Path.home() / ".koda" / "proactive_reminders.json"
        self.timezone = timezone
        
        self._reminders: list[ProactiveReminder] = []
        self._last_check: dict[str, datetime] = {}
        self._user_preferences: dict = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Load saved reminders
        self._load_reminders()
    
    def _load_reminders(self) -> None:
        """Load saved reminders from disk."""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for r in data.get("reminders", []):
                    # Parse datetimes and ensure timezone-aware
                    scheduled_time = datetime.fromisoformat(r["scheduled_time"])
                    if scheduled_time.tzinfo is None:
                        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
                    
                    sent_at = None
                    if r.get("sent_at"):
                        sent_at = datetime.fromisoformat(r["sent_at"])
                        if sent_at.tzinfo is None:
                            sent_at = sent_at.replace(tzinfo=timezone.utc)
                    
                    snooze_until = None
                    if r.get("snooze_until"):
                        snooze_until = datetime.fromisoformat(r["snooze_until"])
                        if snooze_until.tzinfo is None:
                            snooze_until = snooze_until.replace(tzinfo=timezone.utc)
                    
                    self._reminders.append(ProactiveReminder(
                        id=r["id"],
                        type=ReminderType(r["type"]),
                        title=r["title"],
                        message=r["message"],
                        scheduled_time=scheduled_time,
                        priority=ReminderPriority(r["priority"]),
                        channel=r["channel"],
                        recipient=r["recipient"],
                        sent=r.get("sent", False),
                        sent_at=sent_at,
                        snooze_until=snooze_until,
                        metadata=r.get("metadata", {})
                    ))
                self._user_preferences = data.get("preferences", {})
                logger.info(f"Loaded {len(self._reminders)} reminders")
            except Exception as e:
                logger.warning(f"Failed to load reminders: {e}")
    
    def _save_reminders(self) -> None:
        """Save reminders to disk."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "reminders": [
                    {
                        "id": r.id,
                        "type": r.type.value,
                        "title": r.title,
                        "message": r.message,
                        "scheduled_time": r.scheduled_time.isoformat(),
                        "priority": r.priority.value,
                        "channel": r.channel,
                        "recipient": r.recipient,
                        "sent": r.sent,
                        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                        "snooze_until": r.snooze_until.isoformat() if r.snooze_until else None,
                        "metadata": r.metadata
                    }
                    for r in self._reminders
                ],
                "preferences": self._user_preferences
            }
            self.storage_path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")
    
    async def start(self) -> None:
        """Start the reminder service."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._reminder_loop())
        logger.info("✅ Proactive reminder service started")
    
    async def stop(self) -> None:
        """Stop the reminder service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._save_reminders()
        logger.info("Proactive reminder service stopped")
    
    async def _reminder_loop(self) -> None:
        """Main reminder loop - checks and sends reminders."""
        while self._running:
            try:
                await self._check_and_send_reminders()
                await self._scan_for_new_reminders()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                import traceback
                logger.error(f"Error in reminder loop: {e}")
                logger.debug(f"Reminder loop traceback: {traceback.format_exc()}")
                await asyncio.sleep(60)
    
    async def _check_and_send_reminders(self) -> None:
        """Check for due reminders and send them."""
        now = datetime.now(timezone.utc)
        
        for reminder in self._reminders:
            if reminder.sent:
                continue
            
            # Ensure snooze_until is timezone-aware for comparison
            snooze_until = reminder.snooze_until
            if snooze_until and snooze_until.tzinfo is None:
                snooze_until = snooze_until.replace(tzinfo=timezone.utc)
            
            if snooze_until and now < snooze_until:
                continue
            
            # Ensure scheduled_time is timezone-aware for comparison
            scheduled_time = reminder.scheduled_time
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
            
            if now >= scheduled_time:
                # Check quiet hours - delay if needed
                if self._is_quiet_hours(now):
                    next_valid = self._get_next_non_quiet_time()
                    logger.info(f"Delaying reminder '{reminder.title}' due to quiet hours until {next_valid}")
                    reminder.scheduled_time = next_valid
                    continue
                
                await self._send_reminder(reminder)
    
    async def _send_reminder(self, reminder: ProactiveReminder) -> None:
        """Send a reminder through the configured channel."""
        try:
            if self.send_callback:
                await self.send_callback(
                    reminder.channel,
                    reminder.recipient,
                    reminder.message
                )
                
                reminder.sent = True
                reminder.sent_at = datetime.now(timezone.utc)
                self._save_reminders()
                
                logger.info(f"Sent {reminder.type.value} reminder: {reminder.title}")
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")
    
    async def _scan_for_new_reminders(self) -> None:
        """Scan for new events that need reminders."""
        now = datetime.now(timezone.utc)
        
        # Check calendar events (every 5 minutes)
        if self._should_check("calendar", minutes=5):
            await self._scan_calendar_events()
        
        # Check birthdays (once per day)
        if self._should_check("birthday", minutes=60*24):
            await self._scan_birthdays()
        
        # Check for morning briefing
        if self._should_check("morning", minutes=60*24):
            await self._schedule_morning_briefing()
        
        # Check for email digest
        if self._should_check("email", minutes=60*24):
            await self._schedule_email_digest()
    
    def _should_check(self, check_type: str, minutes: int) -> bool:
        """Check if enough time has passed since last check."""
        last = self._last_check.get(check_type)
        if not last:
            self._last_check[check_type] = datetime.now(timezone.utc)
            return True
        
        # Ensure last check time is timezone-aware
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
            self._last_check[check_type] = last
        
        if datetime.now(timezone.utc) - last >= timedelta(minutes=minutes):
            self._last_check[check_type] = datetime.now(timezone.utc)
            return True
        
        return False
    
    async def _scan_calendar_events(self) -> None:
        """Scan calendars for upcoming events that need reminders."""
        if not self.config.calendar_reminders_enabled:
            return
        
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            
            client = GoogleWorkspaceClient()
            if not client.is_authorized:
                return
            
            # Get events in the next 24 hours
            events = client.get_upcoming_events(hours=24)
            
            # Get current time in UTC for comparison
            now = datetime.now(timezone.utc)
            
            for event in events:
                try:
                    # Check if we already have a reminder for this event
                    existing = [r for r in self._reminders 
                               if r.related_event_id == event.id and not r.sent]
                    if existing:
                        continue
                    
                    # Get event start time and ensure it's timezone-aware
                    event_start = event.start
                    if event_start.tzinfo is None:
                        event_start = event_start.replace(tzinfo=timezone.utc)
                    
                    # Schedule reminder
                    reminder_time = event_start - timedelta(
                        minutes=self.config.calendar_default_minutes_before
                    )
                    
                    # Don't schedule if already passed
                    if reminder_time < now:
                        continue
                except Exception as event_error:
                    logger.warning(f"Error processing event {getattr(event, 'id', 'unknown')}: {event_error}")
                    continue
                
                message = self._format_calendar_reminder(event)
                
                reminder = ProactiveReminder(
                    id=f"cal_{event.id}_{int(reminder_time.timestamp())}",
                    type=ReminderType.CALENDAR,
                    title=f"Appointment: {event.summary}",
                    message=message,
                    scheduled_time=reminder_time,
                    priority=ReminderPriority.HIGH if self._is_important_event(event) else ReminderPriority.NORMAL,
                    channel=self.config.default_channel,
                    recipient=self.config.default_recipient,
                    related_event_id=event.id
                )
                
                self._reminders.append(reminder)
                logger.info(f"Scheduled calendar reminder for '{event.summary}' at {reminder_time}")
            
            self._save_reminders()
            
        except Exception as e:
            import traceback
            logger.error(f"Error scanning calendar events: {e}")
            logger.debug(f"Calendar scan traceback: {traceback.format_exc()}")
    
    def _is_important_event(self, event) -> bool:
        """Determine if an event is important based on various signals."""
        # Check title for important keywords
        important_keywords = ["meeting", "call", "interview", "deadline", "presentation", "client"]
        title_lower = event.summary.lower()
        
        for keyword in important_keywords:
            if keyword in title_lower:
                return True
        
        # Check if external attendees
        if hasattr(event, 'attendees') and event.attendees:
            for attendee in event.attendees:
                if attendee and not attendee.endswith(('@gmail.com', '@google.com')):
                    return True
        
        return False
    
    def _format_calendar_reminder(self, event) -> str:
        """Format a calendar event reminder message."""
        lines = [
            f"📅 *Reminder: Appointment in {self.config.calendar_default_minutes_before} minutes*",
            "",
            f"**{event.summary}**",
        ]
        
        if hasattr(event, 'start') and event.start:
            time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else ""
            lines.append(f"🕐 {time_str}")
        
        if hasattr(event, 'location') and event.location:
            lines.append(f"📍 {event.location}")
        
        return "\n".join(lines)
    
    async def _scan_birthdays(self) -> None:
        """Scan contacts for upcoming birthdays."""
        if not self.config.birthday_reminders_enabled:
            return
        
        try:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            
            client = ICloudContactsClient(use_local=True)
            upcoming = client.get_upcoming_birthdays(days=self.config.birthday_days_before + 7)
            
            for contact in upcoming:
                name = contact.get("name", "")
                days_until = contact.get("days_until", 0)
                
                # Check if we already have a reminder for this birthday
                existing = [r for r in self._reminders 
                           if r.type == ReminderType.BIRTHDAY 
                           and r.metadata.get("contact_name") == name
                           and not r.sent]
                if existing:
                    continue
                
                # Schedule for configured days before
                if days_until == self.config.birthday_days_before:
                    send_time = datetime.strptime(self.config.birthday_send_time, "%H:%M").time()
                    scheduled = datetime.combine(date.today(), send_time).replace(tzinfo=timezone.utc)
                    
                    age = contact.get("age")
                    age_text = f" ({age})" if age else ""
                    
                    message = (
                        f"🎂 *Birthday reminder*{age_text}\n\n"
                        f"**{name}** has a birthday in {days_until} day(s)!\n\n"
                        f"Don't forget to congratulate them. 🎉"
                    )
                    
                    reminder = ProactiveReminder(
                        id=f"bday_{name}_{date.today().year}",
                        type=ReminderType.BIRTHDAY,
                        title=f"Birthday: {name}",
                        message=message,
                        scheduled_time=scheduled,
                        priority=ReminderPriority.NORMAL,
                        channel=self.config.default_channel,
                        recipient=self.config.default_recipient,
                        metadata={"contact_name": name, "age": age}
                    )
                    
                    self._reminders.append(reminder)
                    self._save_reminders()
                    logger.info(f"Scheduled birthday reminder for {name}")
                    
        except Exception as e:
            logger.error(f"Error scanning birthdays: {e}")
    
    def _get_local_tz(self):
        """Get the configured timezone as a ZoneInfo object."""
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(self.timezone)
        except Exception:
            return timezone.utc
    
    async def _schedule_morning_briefing(self) -> None:
        """Schedule the daily morning briefing."""
        try:
            local_tz = self._get_local_tz()
            send_time = datetime.strptime(self.config.calendar_morning_check_time, "%H:%M").time()
            scheduled = datetime.combine(date.today(), send_time).replace(tzinfo=local_tz)
            
            # If already passed today, schedule for tomorrow
            now_local = datetime.now(local_tz)
            if scheduled < now_local:
                scheduled += timedelta(days=1)
            
            # Check if already scheduled
            existing = [r for r in self._reminders 
                       if r.type == ReminderType.MORNING_BRIEFING 
                       and r.scheduled_time.date() == scheduled.date()]
            if existing:
                return
            
            reminder = ProactiveReminder(
                id=f"morning_{scheduled.strftime('%Y%m%d')}",
                type=ReminderType.MORNING_BRIEFING,
                title="Good morning!",
                message="",  # Will be filled at send time
                scheduled_time=scheduled,
                priority=ReminderPriority.NORMAL,
                channel=self.config.default_channel,
                recipient=self.config.default_recipient,
                metadata={"dynamic_content": True}
            )
            
            self._reminders.append(reminder)
            self._save_reminders()
            logger.info(f"Scheduled morning briefing for {scheduled}")
            
        except Exception as e:
            logger.error(f"Error scheduling morning briefing: {e}")
    
    async def _schedule_email_digest(self) -> None:
        """Schedule the daily email digest."""
        # Similar to morning briefing
        pass
    
    async def generate_morning_briefing(self) -> str:
        """Generate the morning briefing message with current data."""
        lines = ["🌅 *Good morning!*", ""]
        
        # Today's events
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient(timezone=self.timezone)
            if client.is_authorized:
                events = client.get_today_events()
                if events:
                    lines.append(f"📅 *You have {len(events)} appointment(s) today:*")
                    for event in events[:5]:  # Show max 5
                        time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else ""
                        lines.append(f"  • {time_str} - {event.summary}")
                    if len(events) > 5:
                        lines.append(f"  ... and {len(events) - 5} more")
                    lines.append("")
                else:
                    lines.append("📅 *No appointments on your calendar today.*")
                    lines.append("")
        except Exception as e:
            logger.debug(f"Could not get today's events: {e}")
        
        # Birthday reminders
        try:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            client = ICloudContactsClient(use_local=True)
            birthdays = client.get_birthdays_on_date()
            if birthdays:
                lines.append("🎂 *Birthdays today:*")
                for b in birthdays:
                    age = b.get("age")
                    age_str = f" ({age})" if age else ""
                    lines.append(f"  • {b.get('name', 'Unknown')}{age_str}")
                lines.append("")
        except Exception as e:
            logger.debug(f"Could not get birthdays: {e}")
        
        lines.append("Have a great day! ☀️")
        
        return "\n".join(lines)
    
    def _is_quiet_hours(self, now: datetime) -> bool:
        """Check if current time is within quiet hours."""
        if not self.config.respect_quiet_hours:
            return False
        
        current_time = now.time()
        quiet_start = datetime.strptime(self.config.quiet_hours_start, "%H:%M").time()
        quiet_end = datetime.strptime(self.config.quiet_hours_end, "%H:%M").time()
        
        if quiet_start <= quiet_end:
            # Same day (e.g., 22:00 to 07:00 doesn't fit this pattern)
            return quiet_start <= current_time <= quiet_end
        else:
            # Overnight (e.g., 22:00 to 07:00)
            return current_time >= quiet_start or current_time <= quiet_end
    
    def _get_next_non_quiet_time(self) -> datetime:
        """Get the next time outside of quiet hours."""
        now = datetime.now(timezone.utc)
        quiet_end = datetime.strptime(self.config.quiet_hours_end, "%H:%M").time()
        
        # Schedule for quiet hours end time today or tomorrow
        next_time = datetime.combine(now.date(), quiet_end).replace(tzinfo=timezone.utc)
        if next_time <= now:
            next_time += timedelta(days=1)
        
        return next_time
    
    # Public API methods
    
    def add_reminder(self, title: str, message: str, when: datetime, 
                     reminder_type: ReminderType = ReminderType.CUSTOM,
                     priority: ReminderPriority = ReminderPriority.NORMAL) -> str:
        """Add a custom reminder."""
        # Ensure when is timezone-aware
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        
        reminder = ProactiveReminder(
            id=f"custom_{int(datetime.now(timezone.utc).timestamp())}_{hash(title) % 10000}",
            type=reminder_type,
            title=title,
            message=message,
            scheduled_time=when,
            priority=priority,
            channel=self.config.default_channel,
            recipient=self.config.default_recipient
        )
        
        self._reminders.append(reminder)
        self._save_reminders()
        
        logger.info(f"Added custom reminder '{title}' for {when}")
        return reminder.id
    
    def snooze_reminder(self, reminder_id: str, minutes: int) -> bool:
        """Snooze a reminder for N minutes."""
        for reminder in self._reminders:
            if reminder.id == reminder_id:
                reminder.snooze_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                reminder.sent = False
                self._save_reminders()
                logger.info(f"Snoozed reminder '{reminder.title}' for {minutes} minutes")
                return True
        return False
    
    def dismiss_reminder(self, reminder_id: str) -> bool:
        """Dismiss a reminder without sending."""
        for reminder in self._reminders:
            if reminder.id == reminder_id:
                reminder.sent = True
                self._save_reminders()
                return True
        return False
    
    def get_pending_reminders(self) -> list[ProactiveReminder]:
        """Get all pending (not yet sent) reminders."""
        return [r for r in self._reminders if not r.sent]
    
    def clear_old_reminders(self, days: int = 7) -> int:
        """Clear reminders older than N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old_count = len(self._reminders)
        self._reminders = [
            r for r in self._reminders 
            if not r.sent or (r.sent_at and r.sent_at > cutoff)
        ]
        self._save_reminders()
        cleared = old_count - len(self._reminders)
        logger.info(f"Cleared {cleared} old reminders")
        return cleared
