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
    ANNIVERSARY = "anniversary"     # Special occasions
    EMAIL = "email"                 # Important unread emails
    TASK = "task"                   # Task deadlines
    CUSTOM = "custom"               # User-defined reminders
    MORNING_BRIEFING = "morning"    # Daily morning summary
    EVENING_WRAPUP = "evening"      # Daily evening summary


class ReminderPriority(str, Enum):
    """Priority levels for reminders."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProactiveReminder:
    """A proactive reminder to be sent to the user."""
    id: str
    type: ReminderType
    title: str
    message: str
    scheduled_time: datetime
    priority: ReminderPriority
    channel: str  # whatsapp, telegram, email
    recipient: str
    sent: bool = False
    sent_at: Optional[datetime] = None
    related_event_id: Optional[str] = None
    snooze_until: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ReminderConfig:
    """Configuration for proactive reminders."""
    # Calendar reminders
    calendar_reminders_enabled: bool = True
    calendar_default_minutes_before: int = 15
    calendar_morning_check_time: str = "08:00"  # Daily briefing time
    
    # Birthday reminders
    birthday_reminders_enabled: bool = True
    birthday_days_before: int = 1  # How many days before to remind
    birthday_send_time: str = "09:00"
    
    # Special occasions
    special_occasions_enabled: bool = True
    occasions_to_track: list[str] = field(default_factory=lambda: [
        "valentines", "mothers_day", "fathers_day", 
        "christmas", "new_year", "anniversary"
    ])
    
    # Email monitoring
    email_digest_enabled: bool = True
    email_digest_time: str = "08:30"
    email_high_priority_only: bool = True
    
    # Channels
    default_channel: str = "whatsapp"
    default_recipient: str = ""
    
    # Quiet hours
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    respect_quiet_hours: bool = True


class ProactiveReminderService:
    """
    Service that sends proactive reminders and maintains assistant memory.
    
    This is the core of the "executive secretary" functionality - it:
    1. Scans calendars for upcoming events and sends reminders
    2. Checks for birthdays and special occasions
    3. Monitors important emails
    4. Provides daily briefings
    5. Learns user patterns and preferences
    """
    
    def __init__(
        self,
        config: ReminderConfig | None = None,
        storage_path: Path | None = None,
        send_callback: Callable[[str, str, str], asyncio.Future] | None = None
    ):
        self.config = config or ReminderConfig()
        self.storage_path = storage_path or Path.home() / ".koda" / "proactive_reminders.json"
        self.send_callback = send_callback
        
        self._reminders: list[ProactiveReminder] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_check: dict[str, datetime] = {}
        
        # User preferences learned over time
        self._user_preferences: dict[str, Any] = {}
        
        self._load_reminders()
    
    def _load_reminders(self) -> None:
        """Load saved reminders from disk."""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for r in data.get("reminders", []):
                    self._reminders.append(ProactiveReminder(
                        id=r["id"],
                        type=ReminderType(r["type"]),
                        title=r["title"],
                        message=r["message"],
                        scheduled_time=datetime.fromisoformat(r["scheduled_time"]),
                        priority=ReminderPriority(r["priority"]),
                        channel=r["channel"],
                        recipient=r["recipient"],
                        sent=r.get("sent", False),
                        sent_at=datetime.fromisoformat(r["sent_at"]) if r.get("sent_at") else None,
                        snooze_until=datetime.fromisoformat(r["snooze_until"]) if r.get("snooze_until") else None,
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
    
    def _is_quiet_hours(self, check_time: datetime | None = None) -> bool:
        """Check if current time is within quiet hours."""
        if not self.config.respect_quiet_hours:
            return False
        
        now = check_time or datetime.now(timezone.utc)
        current_time = now.strftime("%H:%M")
        
        quiet_start = self.config.quiet_hours_start
        quiet_end = self.config.quiet_hours_end
        
        if quiet_start <= quiet_end:
            # Normal case (e.g., 22:00 to 07:00 doesn't apply here)
            return quiet_start <= current_time <= quiet_end
        else:
            # Wraps around midnight (e.g., 22:00 to 07:00)
            return current_time >= quiet_start or current_time <= quiet_end
    
    def _get_next_non_quiet_time(self) -> datetime:
        """Get the next time outside quiet hours."""
        now = datetime.now(timezone.utc)
        quiet_end = datetime.strptime(self.config.quiet_hours_end, "%H:%M").time()
        
        next_time = now.replace(hour=quiet_end.hour, minute=quiet_end.minute, second=0)
        if next_time <= now:
            next_time += timedelta(days=1)
        
        return next_time
    
    async def start(self) -> None:
        """Start the proactive reminder service."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("✅ Proactive reminder service started")
    
    async def stop(self) -> None:
        """Stop the proactive reminder service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Proactive reminder service stopped")
    
    async def _run_loop(self) -> None:
        """Main loop that checks and sends reminders."""
        while self._running:
            try:
                await self._check_and_send_reminders()
                await self._scan_for_new_reminders()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reminder loop: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_send_reminders(self) -> None:
        """Check for due reminders and send them."""
        now = datetime.now(timezone.utc)
        
        for reminder in self._reminders:
            if reminder.sent:
                continue
            
            if reminder.snooze_until and now < reminder.snooze_until:
                continue
            
            if now >= reminder.scheduled_time:
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
        
        if datetime.now(timezone.utc) - last >= timedelta(minutes=minutes):
            self._last_check[check_type] = datetime.now(timezone.utc)
            return True
        
        return False
    
    async def _scan_calendar_events(self) -> None:
        """Scan calendars for upcoming events that need reminders."""
        if not self.config.calendar_reminders_enabled:
            return
        
        try:
            from datetime import timezone
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
                    title=f"Afspraak: {event.summary}",
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
            f"📅 *Herinnering: Afspraak over {self.config.calendar_default_minutes_before} minuten*",
            "",
            f"**{event.summary}**",
        ]
        
        if hasattr(event, 'start') and event.start:
            time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else str(event.start)
            lines.append(f"🕐 {time_str}")
        
        if hasattr(event, 'location') and event.location:
            lines.append(f"📍 {event.location}")
        
        if hasattr(event, 'meet_link') and event.meet_link:
            lines.append(f"🔗 {event.meet_link}")
        
        if hasattr(event, 'description') and event.description:
            # Truncate long descriptions
            desc = event.description[:200] + "..." if len(event.description) > 200 else event.description
            lines.append(f"\n📝 {desc}")
        
        lines.append("\n_Reageer met 'snooze 5' om over 5 minuten opnieuw te herinneren_")
        
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
                    age_text = f" ({age} jaar)" if age else ""
                    
                    message = (
                        f"🎂 *Verjaardag herinnering*{age_text}\n\n"
                        f"**{name}** is jarig over {days_until} dag(en)!\n\n"
                        f"Vergeet niet om te feliciteren. 🎉"
                    )
                    
                    reminder = ProactiveReminder(
                        id=f"bday_{name}_{int(scheduled.timestamp())}",
                        type=ReminderType.BIRTHDAY,
                        title=f"Verjaardag: {name}",
                        message=message,
                        scheduled_time=scheduled,
                        priority=ReminderPriority.NORMAL,
                        channel=self.config.default_channel,
                        recipient=self.config.default_recipient,
                        metadata={"contact_name": name, "days_until": days_until}
                    )
                    
                    self._reminders.append(reminder)
                    logger.info(f"Scheduled birthday reminder for {name}")
            
            self._save_reminders()
            
        except Exception as e:
            logger.error(f"Error scanning birthdays: {e}")
    
    async def _schedule_morning_briefing(self) -> None:
        """Schedule the daily morning briefing."""
        try:
            send_time = datetime.strptime(self.config.calendar_morning_check_time, "%H:%M").time()
            scheduled = datetime.combine(date.today(), send_time).replace(tzinfo=timezone.utc)
            
            # If already passed today, schedule for tomorrow
            if scheduled < datetime.now(timezone.utc):
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
                title="Goedemorgen!",
                message="",  # Will be filled at send time
                scheduled_time=scheduled,
                priority=ReminderPriority.NORMAL,
                channel=self.config.default_channel,
                recipient=self.config.default_recipient,
                metadata={"dynamic_content": True}
            )
            
            self._reminders.append(reminder)
            logger.info(f"Scheduled morning briefing for {scheduled}")
            self._save_reminders()
            
        except Exception as e:
            logger.error(f"Error scheduling morning briefing: {e}")
    
    async def _schedule_email_digest(self) -> None:
        """Schedule the daily email digest."""
        # Similar to morning briefing
        pass
    
    async def generate_morning_briefing(self) -> str:
        """Generate the morning briefing message with current data."""
        lines = ["🌅 *Goedemorgen!*", ""]
        
        # Today's events
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            if client.is_authorized:
                events = client.get_today_events()
                if events:
                    lines.append(f"📅 *Vandaag heb je {len(events)} afspraak(len):*")
                    for event in events[:5]:  # Show max 5
                        time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else ""
                        lines.append(f"  • {time_str} - {event.summary}")
                    if len(events) > 5:
                        lines.append(f"  ... en nog {len(events) - 5} meer")
                    lines.append("")
                else:
                    lines.append("📅 *Vandaag geen afspraken in je agenda.*")
                    lines.append("")
        except Exception as e:
            logger.debug(f"Could not get today's events: {e}")
        
        # Birthday reminders
        try:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            client = ICloudContactsClient(use_local=True)
            birthdays = client.get_birthdays_on_date(date.today())
            if birthdays:
                lines.append("🎂 *Vandaag jarig:*")
                for b in birthdays:
                    age = b.get("age", "")
                    age_text = f" ({age})" if age else ""
                    lines.append(f"  • {b['name']}{age_text}")
                lines.append("")
        except Exception as e:
            logger.debug(f"Could not get birthdays: {e}")
        
        # Weather (placeholder)
        lines.append("☀️ _Fijne dag gewenst!_")
        
        return "\n".join(lines)
    
    def add_custom_reminder(
        self,
        title: str,
        message: str,
        when: datetime,
        priority: ReminderPriority = ReminderPriority.NORMAL,
        channel: str | None = None,
        recipient: str | None = None
    ) -> str:
        """Add a custom reminder."""
        reminder = ProactiveReminder(
            id=f"custom_{int(datetime.now(timezone.utc).timestamp())}_{hash(title) % 10000}",
            type=ReminderType.CUSTOM,
            title=title,
            message=message,
            scheduled_time=when,
            priority=priority,
            channel=channel or self.config.default_channel,
            recipient=recipient or self.config.default_recipient
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
