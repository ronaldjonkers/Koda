"""Event reminder service for public events.

Sends proactive reminders about upcoming events like:
- "🏎️ F1 race this weekend: Dutch Grand Prix"
- "⚽ Feyenoord plays tomorrow vs Ajax at 14:30"
- "🎵 Concert reminder: Your favorite artist is playing tonight"
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from koda.config.loader import load_config
from koda.core.tools.public_events import PublicEventsTool
from koda.scheduler.types import CronSchedule
from koda.services.base import BaseService


class EventReminderService(BaseService):
    """
    Service that sends reminders about upcoming public events.
    
    Checks daily for events in the next 1-3 days and sends reminders
    to the configured WhatsApp number.
    
    Configurable:
    - How many days ahead to remind (default: 3)
    - Which event categories to remind about
    - Time of day to send reminders
    """
    
    name = "event_reminder"
    description = "Sends reminders about upcoming public events (sports, concerts, etc.)"
    
    DEFAULT_REMINDER_TIME = "08:00"  # 8 AM
    DEFAULT_DAYS_AHEAD = 3
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config
        self.event_tool: Optional[PublicEventsTool] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the event reminder service."""
        logger.info("🏎️ Starting Event Reminder Service...")
        
        # Load main config
        main_config = load_config()
        
        # Initialize event tool
        workspace = Path.home() / ".koda" / "workspace"
        football_key = getattr(main_config.tools, 'football_api_key', None)
        self.event_tool = PublicEventsTool(workspace, football_api_key=football_key)
        
        self._running = True
        
        # Run immediately on startup, then schedule daily
        await self._check_and_remind()
        
        # Schedule daily check
        from koda.scheduler.service import SchedulerService
        scheduler = SchedulerService()
        
        # Schedule for 8 AM daily
        schedule = CronSchedule(kind="cron", expr="0 8 * * *", tz="Europe/Amsterdam")
        
        scheduler.add_job(
            name="event_reminder",
            schedule=schedule,
            prompt="Check for upcoming public events and send reminders",
            target_channel="whatsapp",
            enabled=True
        )
        
        logger.info("✅ Event Reminder Service scheduled for 8:00 AM daily")
    
    async def stop(self) -> None:
        """Stop the event reminder service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event Reminder Service stopped")
    
    async def run_once(self) -> list[str]:
        """Run a single reminder check. Returns list of sent reminders."""
        return await self._check_and_remind()
    
    async def _check_and_remind(self) -> list[str]:
        """Check for upcoming events and send reminders."""
        if not self.event_tool:
            return []
        
        sent_reminders = []
        
        try:
            # Get events needing reminders
            events = self.event_tool.get_upcoming_events_for_reminders(days_ahead=self.DEFAULT_DAYS_AHEAD)
            
            if not events:
                logger.debug("No upcoming events need reminders")
                return []
            
            logger.info(f"Found {len(events)} events needing reminders")
            
            # Group events by urgency
            today_events = []
            tomorrow_events = []
            weekend_events = []
            
            now = datetime.now()
            tomorrow = now + timedelta(days=1)
            
            for event in events:
                days_until = (event.start_time - now).days
                
                if days_until == 0:
                    today_events.append(event)
                elif days_until == 1:
                    tomorrow_events.append(event)
                elif days_until <= 3:
                    weekend_events.append(event)
            
            # Build reminder messages
            reminders = []
            
            if today_events:
                reminders.append(self._format_today_reminder(today_events))
            
            if tomorrow_events:
                reminders.append(self._format_tomorrow_reminder(tomorrow_events))
            
            if weekend_events:
                reminders.append(self._format_weekend_reminder(weekend_events))
            
            # Send reminders
            for reminder in reminders:
                await self._send_reminder(reminder)
                sent_reminders.append(reminder)
            
            # Mark events as reminded
            for event in events:
                self.event_tool.mark_reminder_sent(event.id)
            
            return sent_reminders
            
        except Exception as e:
            logger.error(f"Error checking events: {e}")
            return []
    
    def _format_today_reminder(self, events: list) -> str:
        """Format reminder for today's events."""
        lines = ["🚨 *Events Today!*\n"]
        
        for event in events:
            time_str = event.start_time.strftime("%H:%M")
            lines.append(f"• *{event.title}* at {time_str}")
            if event.location:
                lines.append(f"  📍 {event.location}")
        
        return "\n".join(lines)
    
    def _format_tomorrow_reminder(self, events: list) -> str:
        """Format reminder for tomorrow's events."""
        lines = ["📅 *Tomorrow's Events*\n"]
        
        for event in events:
            time_str = event.start_time.strftime("%H:%M")
            lines.append(f"• *{event.title}* at {time_str}")
            if event.location:
                lines.append(f"  📍 {event.location}")
        
        return "\n".join(lines)
    
    def _format_weekend_reminder(self, events: list) -> str:
        """Format reminder for weekend/upcoming events."""
        lines = ["🎉 *Coming Up This Weekend*\n"]
        
        for event in events[:5]:  # Limit to 5 events
            day_name = event.start_time.strftime("%A")
            time_str = event.start_time.strftime("%H:%M")
            lines.append(f"• *{event.title}* - {day_name} at {time_str}")
        
        if len(events) > 5:
            lines.append(f"\n_And {len(events) - 5} more events..._")
        
        return "\n".join(lines)
    
    async def _send_reminder(self, message: str) -> bool:
        """Send a reminder message via WhatsApp."""
        try:
            # Get WhatsApp channel
            from koda.services.manager import ServiceManager
            manager = ServiceManager()
            
            wa_channel = None
            for channel in manager.channels.values():
                if channel.name == "whatsapp":
                    wa_channel = channel
                    break
            
            if not wa_channel:
                logger.warning("WhatsApp channel not available for event reminders")
                return False
            
            # Get owner phone
            config = load_config()
            owner_phone = config.channels.whatsapp.owner_phone
            
            if not owner_phone:
                logger.warning("No owner_phone configured for event reminders")
                return False
            
            # Format JID
            jid = f"{owner_phone.replace('+', '')}@s.whatsapp.net"
            
            # Send message
            from koda.messaging.queue import OutboundMessage
            msg = OutboundMessage(
                channel="whatsapp",
                chat_id=jid,
                content=message
            )
            
            await wa_channel.send(msg)
            logger.info(f"Sent event reminder: {message[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send event reminder: {e}")
            return False
    
    def get_next_events_summary(self, days: int = 7) -> str:
        """Get a summary of upcoming events (for proactive messages)."""
        if not self.event_tool:
            return ""
        
        events = [
            e for e in self.event_tool.events
            if not e.reminder_sent
            and datetime.now() <= e.start_time <= datetime.now() + timedelta(days=days)
        ]
        
        if not events:
            return ""
        
        lines = ["📅 *Upcoming Events This Week:*\n"]
        
        for event in events[:5]:
            day_name = event.start_time.strftime("%A %d %b")
            lines.append(f"• {event.title} ({day_name})")
        
        return "\n".join(lines)


# Standalone function for scheduler integration
async def check_event_reminders() -> str:
    """Check for event reminders (called by scheduler)."""
    service = EventReminderService()
    await service.start()
    reminders = await service.run_once()
    await service.stop()
    
    if reminders:
        return f"Sent {len(reminders)} event reminders"
    return "No upcoming events need reminders"
