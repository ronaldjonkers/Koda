"""Proactive Assistant Tool - Manage your AI executive secretary's memory and reminders.

This tool allows the AI to:
- Set custom reminders for the user
- View pending reminders
- Configure proactive notification preferences
- Check upcoming events and birthdays
- Generate morning briefings on demand
"""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class ProactiveAssistantTool(BaseTool):
    """
    Tool for managing the proactive assistant's reminders and notifications.
    
    This tool gives the AI control over the executive secretary features:
    - Setting custom reminders
    - Checking upcoming events and birthdays
    - Configuring notification preferences
    - Generating briefings
    
    Actions:
    - add_reminder: Add a custom reminder
    - list_pending: List all pending reminders
    - snooze: Snooze a reminder
    - dismiss: Dismiss a reminder
    - upcoming: Check upcoming events across all calendars
    - birthdays: Check upcoming birthdays
    - morning_briefing: Generate a morning briefing
    - preferences: View or update notification preferences
    
    Parameters for 'add_reminder':
    - title: Reminder title
    - message: Reminder message
    - when: When to send (datetime ISO format or relative like "+30 minutes", "tomorrow 9am")
    - priority: low, normal, high, urgent
    
    Parameters for 'upcoming':
    - hours: Number of hours to look ahead (default: 24)
    
    Parameters for 'birthdays':
    - days: Number of days to look ahead (default: 7)
    
    Parameters for 'snooze':
    - reminder_id: ID of reminder to snooze
    - minutes: Minutes to snooze for
    
    Parameters for 'dismiss':
    - reminder_id: ID of reminder to dismiss
    """
    
    name = "proactive_assistant"
    description = """Manage your AI executive assistant's proactive reminders and notifications.

This tool controls the "secretary" features that anticipate your needs and send timely reminders.

Actions:
- add_reminder: Set a custom reminder (the assistant will notify you at the specified time)
- list_pending: See all reminders waiting to be sent
- snooze: Delay a reminder (e.g., "remind me again in 10 minutes")
- dismiss: Cancel a reminder without sending
- upcoming: Check upcoming calendar events
- birthdays: Check upcoming birthdays from contacts
- morning_briefing: Generate a daily briefing with agenda and important items
- status: Check the proactive assistant's status and configuration

Examples:
- "Remind me to call John tomorrow at 2pm" -> add_reminder
- "What do I have coming up?" -> upcoming
- "Any birthdays soon?" -> birthdays  
- "Give me my morning briefing" -> morning_briefing
- "What reminders do I have pending?" -> list_pending

Parameters:
- action: The action to perform (required)
- For add_reminder: title, message, when (datetime or relative time), priority
- For upcoming: hours (default: 24)
- For birthdays: days (default: 7)
- For snooze/dismiss: reminder_id
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add_reminder", "list_pending", "snooze", "dismiss", "upcoming", "birthdays", "morning_briefing", "status"],
                "description": "Action to perform"
            },
            "title": {
                "type": "string",
                "description": "Title for the reminder (for add_reminder)"
            },
            "message": {
                "type": "string",
                "description": "Message content for the reminder"
            },
            "when": {
                "type": "string",
                "description": "When to send - ISO datetime or relative like '+30 minutes', 'tomorrow 9am'"
            },
            "priority": {
                "type": "string",
                "enum": ["low", "normal", "high", "urgent"],
                "description": "Priority level for the reminder"
            },
            "hours": {
                "type": "integer",
                "description": "Hours to look ahead for upcoming events",
                "default": 24
            },
            "days": {
                "type": "integer",
                "description": "Days to look ahead for birthdays",
                "default": 7
            },
            "reminder_id": {
                "type": "string",
                "description": "ID of reminder to snooze or dismiss"
            },
            "minutes": {
                "type": "integer",
                "description": "Minutes to snooze for",
                "default": 10
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, proactive_service=None):
        self.proactive_service = proactive_service
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "status")
        
        try:
            if action == "add_reminder":
                return await self._add_reminder(**kwargs)
            elif action == "list_pending":
                return await self._list_pending()
            elif action == "snooze":
                return await self._snooze(**kwargs)
            elif action == "dismiss":
                return await self._dismiss(**kwargs)
            elif action == "upcoming":
                return await self._upcoming(**kwargs)
            elif action == "birthdays":
                return await self._birthdays(**kwargs)
            elif action == "morning_briefing":
                return await self._morning_briefing()
            elif action == "status":
                return await self._status()
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            logger.error(f"Proactive assistant error: {e}")
            return f"❌ Error: {str(e)}"
    
    def _parse_when(self, when_str: str) -> datetime | None:
        """Parse a when string into a datetime."""
        when_str = when_str.strip().lower()
        
        # Handle relative times
        if when_str.startswith("+"):
            # Format: +30 minutes, +1 hour, +2 days
            parts = when_str[1:].split()
            if len(parts) >= 2:
                try:
                    amount = int(parts[0])
                    unit = parts[1].lower()
                    
                    if unit in ["minute", "minutes", "min", "mins"]:
                        return datetime.now() + timedelta(minutes=amount)
                    elif unit in ["hour", "hours", "hr", "hrs"]:
                        return datetime.now() + timedelta(hours=amount)
                    elif unit in ["day", "days"]:
                        return datetime.now() + timedelta(days=amount)
                except ValueError:
                    pass
        
        # Handle simple relative phrases
        if when_str == "now":
            return datetime.now()
        elif when_str in ["in an hour", "in 1 hour"]:
            return datetime.now() + timedelta(hours=1)
        elif when_str in ["in 30 minutes", "in half an hour"]:
            return datetime.now() + timedelta(minutes=30)
        elif when_str in ["tomorrow"]:
            return datetime.now() + timedelta(days=1)
        elif when_str.startswith("tomorrow "):
            # tomorrow 9am, tomorrow 14:00
            time_part = when_str[9:]
            try:
                tomorrow = datetime.now() + timedelta(days=1)
                # Try parsing time
                for fmt in ["%H:%M", "%I:%M%p", "%I %p", "%H.%M"]:
                    try:
                        t = datetime.strptime(time_part.replace(" ", ""), fmt).time()
                        return tomorrow.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                    except ValueError:
                        continue
            except:
                pass
        
        # Try ISO format
        try:
            return datetime.fromisoformat(when_str.replace("Z", "+00:00"))
        except ValueError:
            pass
        
        return None
    
    async def _add_reminder(self, **kwargs) -> str:
        """Add a custom reminder."""
        title = kwargs.get("title")
        message = kwargs.get("message")
        when_str = kwargs.get("when")
        priority = kwargs.get("priority", "normal")
        
        if not title or not when_str:
            return "❌ Error: title and when are required for adding a reminder."
        
        when = self._parse_when(when_str)
        if not when:
            return f"❌ Could not understand time: '{when_str}'. Try formats like:\n- '+30 minutes'\n- 'tomorrow 9am'\n- '2024-01-15 14:30'"
        
        if when < datetime.now():
            return f"❌ Cannot set reminder in the past. Specified time: {when.strftime('%Y-%m-%d %H:%M')}"
        
        # Use proactive service if available
        if self.proactive_service:
            from koda.services.proactive_reminder import ReminderPriority
            priority_map = {
                "low": ReminderPriority.LOW,
                "normal": ReminderPriority.NORMAL,
                "high": ReminderPriority.HIGH,
                "urgent": ReminderPriority.URGENT
            }
            
            reminder_id = self.proactive_service.add_custom_reminder(
                title=title,
                message=message or title,
                when=when,
                priority=priority_map.get(priority, ReminderPriority.NORMAL)
            )
            
            return (
                f"✅ **Reminder set**\n\n"
                f"**{title}**\n"
                f"📅 {when.strftime('%Y-%m-%d %H:%M')}\n"
                f"🔔 Priority: {priority}\n\n"
                f"_You'll receive a notification on time._"
            )
        else:
            return "❌ Proactive reminder service is not available. Please restart the gateway."
    
    async def _list_pending(self) -> str:
        """List all pending reminders."""
        if not self.proactive_service:
            return "❌ Proactive reminder service is not available."
        
        pending = self.proactive_service.get_pending_reminders()
        
        if not pending:
            return "📋 No active reminders.\n\n_You can add a reminder with 'add_reminder'_"
        
        lines = [f"📋 **{len(pending)} active reminder(s):**\n"]
        
        for r in pending[:10]:  # Show max 10
            time_str = r.scheduled_time.strftime("%Y-%m-%d %H:%M")
            priority_emoji = {"urgent": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}.get(r.priority.value, "⚪")
            lines.append(f"{priority_emoji} **{r.title}**")
            lines.append(f"   📅 {time_str}")
            lines.append(f"   🆔 `{r.id}`")
            lines.append("")
        
        if len(pending) > 10:
            lines.append(f"... and {len(pending) - 10} more")
        
        lines.append("\n_Use 'snooze' or 'dismiss' with the ID to manage reminders._")
        return "\n".join(lines)
    
    async def _snooze(self, **kwargs) -> str:
        """Snooze a reminder."""
        reminder_id = kwargs.get("reminder_id")
        minutes = kwargs.get("minutes", 10)
        
        if not reminder_id:
            return "❌ Error: reminder_id is required."
        
        if not self.proactive_service:
            return "❌ Proactive reminder service is not available."
        
        success = self.proactive_service.snooze_reminder(reminder_id, minutes)
        
        if success:
            new_time = datetime.now() + timedelta(minutes=minutes)
            return f"⏰ Reminder snoozed. You'll receive a new notification in {minutes} minutes ({new_time.strftime('%H:%M')})."
        else:
            return f"❌ Reminder with ID '{reminder_id}' not found. Use 'list_pending' to see available IDs."
    
    async def _dismiss(self, **kwargs) -> str:
        """Dismiss a reminder."""
        reminder_id = kwargs.get("reminder_id")
        
        if not reminder_id:
            return "❌ Error: reminder_id is required."
        
        if not self.proactive_service:
            return "❌ Proactive reminder service is not available."
        
        success = self.proactive_service.dismiss_reminder(reminder_id)
        
        if success:
            return f"✅ Reminder dismissed."
        else:
            return f"❌ Reminder with ID '{reminder_id}' not found."
    
    async def _upcoming(self, **kwargs) -> str:
        """Check upcoming events."""
        hours = kwargs.get("hours", 24)
        
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            
            client = GoogleWorkspaceClient()
            if not client.is_authorized:
                return "❌ Google Workspace is not configured. Run 'koda setup google'."
            
            events = client.get_upcoming_events(hours=hours)
            
            if not events:
                return f"📅 No appointments in the next {hours} hours."
            
            lines = [f"📅 **Next {hours} hours** ({len(events)} appointments):\n"]
            
            for event in events[:10]:
                time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else str(event.start)
                date_str = event.start.strftime("%d %b") if hasattr(event.start, 'strftime') else ""
                
                lines.append(f"• **{event.summary}**")
                lines.append(f"  🕐 {date_str} {time_str}")
                
                if event.location:
                    lines.append(f"  📍 {event.location}")
                if event.meet_link:
                    lines.append(f"  🔗 Meet link available")
                lines.append("")
            
            if len(events) > 10:
                lines.append(f"... and {len(events) - 10} more")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error getting upcoming events: {e}")
            return f"❌ Could not retrieve calendar: {e}"
    
    async def _birthdays(self, **kwargs) -> str:
        """Check upcoming birthdays."""
        days = kwargs.get("days", 7)
        
        try:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            
            client = ICloudContactsClient(use_local=True)
            upcoming = client.get_upcoming_birthdays(days=days)
            
            if not upcoming:
                return f"🎂 No birthdays in the next {days} days."
            
            lines = [f"🎂 **Birthdays in the next {days} days** ({len(upcoming)}):\n"]
            
            for contact in upcoming:
                name = contact.get("name", "")
                days_until = contact.get("days_until", 0)
                age = contact.get("age")
                
                if days_until == 0:
                    when = "**TODAY!** 🎉"
                elif days_until == 1:
                    when = "tomorrow"
                else:
                    when = f"in {days_until} days"
                
                age_text = f" ({age})" if age else ""
                lines.append(f"• **{name}**{age_text} - {when}")
            
            lines.append("\n_Don't forget to congratulate them! 🎂_")
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error getting birthdays: {e}")
            return f"❌ Could not retrieve birthdays: {e}"
    
    async def _morning_briefing(self) -> str:
        """Generate a morning briefing."""
        lines = ["🌅 **Good morning!**", ""]
        
        # Today's events
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            from datetime import date
            
            client = GoogleWorkspaceClient()
            if client.is_authorized:
                events = client.get_today_events()
                if events:
                    lines.append(f"📅 **Today ({len(events)} appointments):**")
                    for event in events[:5]:
                        time_str = event.start.strftime("%H:%M") if hasattr(event.start, 'strftime') else ""
                        lines.append(f"  • {time_str} - {event.summary}")
                    if len(events) > 5:
                        lines.append(f"  ... and {len(events) - 5} more")
                    lines.append("")
                else:
                    lines.append("📅 *No appointments today.*")
                    lines.append("")
        except Exception as e:
            logger.debug(f"Could not get today's events: {e}")
        
        # Birthdays today
        try:
            from koda.integrations.icloud_contacts import ICloudContactsClient
            from datetime import date
            
            client = ICloudContactsClient(use_local=True)
            birthdays = client.get_birthdays_on_date(date.today())
            if birthdays:
                lines.append("🎂 **Birthdays today:**")
                for b in birthdays:
                    age = b.get("age", "")
                    age_text = f" ({age})" if age else ""
                    lines.append(f"  • {b['name']}{age_text}")
                lines.append("")
        except Exception as e:
            logger.debug(f"Could not get birthdays: {e}")
        
        # Add tip based on day of week
        weekday = datetime.now().weekday()
        tips = {
            0: "💡 *Great start to the week!*",
            1: "💡 *Have a productive Tuesday!*",
            2: "💡 *Midweek already!*",
            3: "💡 *Almost weekend!*",
            4: "💡 *Last workday of the week!*",
            5: "🎉 *Enjoy your weekend!*",
            6: "🌟 *Enjoy your Sunday!*"
        }
        lines.append(tips.get(weekday, "💡 *Have a great day!*"))
        
        return "\n".join(lines)
    
    async def _status(self) -> str:
        """Check the proactive assistant status."""
        if not self.proactive_service:
            return "❌ Proactive reminder service is not available."
        
        pending = self.proactive_service.get_pending_reminders()
        config = self.proactive_service.config
        
        lines = ["🤖 **Proactive Assistant Status**\n"]
        
        lines.append("**Configuration:**")
        lines.append(f"• Calendar reminders: {'✅' if config.calendar_reminders_enabled else '❌'}")
        lines.append(f"• Birthday reminders: {'✅' if config.birthday_reminders_enabled else '❌'}")
        lines.append(f"• Special occasions: {'✅' if config.special_occasions_enabled else '❌'}")
        lines.append(f"• Email digest: {'✅' if config.email_digest_enabled else '❌'}")
        lines.append(f"• Respect quiet hours: {'✅' if config.respect_quiet_hours else '❌'} ({config.quiet_hours_start}-{config.quiet_hours_end})")
        lines.append("")
        
        lines.append(f"**Active reminders:** {len(pending)}")
        
        # Show upcoming reminders (next 3)
        upcoming = sorted([r for r in pending if r.scheduled_time > datetime.now()], 
                         key=lambda x: x.scheduled_time)[:3]
        if upcoming:
            lines.append("\n**Next 3 reminders:**")
            for r in upcoming:
                time_str = r.scheduled_time.strftime("%Y-%m-%d %H:%M")
                lines.append(f"• {time_str} - {r.title}")
        
        return "\n".join(lines)
