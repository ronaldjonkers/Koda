"""Reminder tool for scheduling notifications."""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class ReminderTool(BaseTool):
    """
    Tool for managing reminders and scheduled notifications.
    
    Allows the agent to:
    - Create reminders for specific times
    - Send reminders via email, webhook, or messaging channels
    - List and manage pending reminders
    """
    
    name = "reminder"
    description = """Schedule and manage reminders. Use this to:
- Set reminders for specific times
- Send notifications via email, webhook, Telegram, or WhatsApp
- List, update, or cancel pending reminders

Actions:
- add: Create a new reminder
- list: Show pending reminders  
- remove: Cancel a reminder
- get: Get details of a specific reminder"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "remove", "get"],
                "description": "The reminder operation to perform"
            },
            "title": {
                "type": "string",
                "description": "For 'add': reminder title"
            },
            "message": {
                "type": "string",
                "description": "For 'add': reminder message body"
            },
            "trigger_at": {
                "type": "string",
                "description": "For 'add': when to send (ISO format: 2024-12-25T09:00:00, or relative: '+1h', '+30m', '+1d')"
            },
            "channel": {
                "type": "string",
                "enum": ["email", "webhook", "telegram", "whatsapp"],
                "description": "For 'add': delivery channel (default: webhook)"
            },
            "recipient": {
                "type": "string",
                "description": "For 'add': email address, webhook URL, or chat_id"
            },
            "reminder_id": {
                "type": "string",
                "description": "For 'remove' or 'get': reminder ID"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, reminder_service: Any):
        self.reminder_service = reminder_service
    
    def _parse_trigger_time(self, trigger_at: str) -> datetime:
        """Parse trigger time from string."""
        trigger_at = trigger_at.strip()
        
        # Relative time format: +1h, +30m, +1d
        if trigger_at.startswith("+"):
            now = datetime.now()
            value = trigger_at[1:-1]
            unit = trigger_at[-1].lower()
            
            try:
                amount = int(value)
            except ValueError:
                raise ValueError(f"Invalid relative time: {trigger_at}")
            
            if unit == "m":
                return now + timedelta(minutes=amount)
            elif unit == "h":
                return now + timedelta(hours=amount)
            elif unit == "d":
                return now + timedelta(days=amount)
            else:
                raise ValueError(f"Unknown time unit: {unit} (use m, h, or d)")
        
        # ISO format
        try:
            return datetime.fromisoformat(trigger_at)
        except ValueError:
            raise ValueError(f"Invalid datetime format: {trigger_at}. Use ISO format or relative (+1h, +30m, +1d)")
    
    async def execute(self, **kwargs) -> str:
        """Execute a reminder operation."""
        action = kwargs.get("action")
        
        if not self.reminder_service:
            return "Error: Reminder service not available"
        
        try:
            if action == "add":
                title = kwargs.get("title", "")
                message = kwargs.get("message", "")
                trigger_at = kwargs.get("trigger_at", "")
                channel = kwargs.get("channel", "webhook")
                recipient = kwargs.get("recipient", "")
                
                if not title:
                    return "Error: 'title' is required"
                if not trigger_at:
                    return "Error: 'trigger_at' is required"
                if not recipient:
                    return "Error: 'recipient' is required (email, webhook URL, or chat_id)"
                
                trigger_time = self._parse_trigger_time(trigger_at)
                
                if trigger_time <= datetime.now():
                    return "Error: trigger_at must be in the future"
                
                reminder = self.reminder_service.add_reminder(
                    title=title,
                    message=message or title,
                    trigger_at=trigger_time,
                    channel=channel,
                    recipient=recipient
                )
                
                return f"Reminder created:\n- ID: {reminder.id}\n- Title: {title}\n- Triggers at: {trigger_time.strftime('%Y-%m-%d %H:%M')}\n- Channel: {channel}\n- Recipient: {recipient}"
            
            elif action == "list":
                reminders = self.reminder_service.list_reminders(pending_only=True)
                
                if not reminders:
                    return "No pending reminders."
                
                output = [f"Pending reminders ({len(reminders)}):\n"]
                for r in reminders:
                    trigger = datetime.fromtimestamp(r.trigger_at_ms / 1000)
                    output.append(f"- [{r.id}] {r.title}")
                    output.append(f"  Triggers: {trigger.strftime('%Y-%m-%d %H:%M')}")
                    output.append(f"  Channel: {r.channel.value} → {r.recipient}")
                
                return "\n".join(output)
            
            elif action == "remove":
                reminder_id = kwargs.get("reminder_id", "")
                if not reminder_id:
                    return "Error: 'reminder_id' is required"
                
                if self.reminder_service.remove_reminder(reminder_id):
                    return f"Reminder {reminder_id} removed."
                return f"Reminder {reminder_id} not found."
            
            elif action == "get":
                reminder_id = kwargs.get("reminder_id", "")
                if not reminder_id:
                    return "Error: 'reminder_id' is required"
                
                r = self.reminder_service.get_reminder(reminder_id)
                if not r:
                    return f"Reminder {reminder_id} not found."
                
                trigger = datetime.fromtimestamp(r.trigger_at_ms / 1000)
                return f"Reminder details:\n- ID: {r.id}\n- Title: {r.title}\n- Message: {r.message}\n- Triggers: {trigger.strftime('%Y-%m-%d %H:%M')}\n- Channel: {r.channel.value}\n- Recipient: {r.recipient}\n- Sent: {r.sent}"
            
            else:
                return f"Unknown action: {action}"
        
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"Reminder operation failed: {e}")
            return f"Error: {str(e)}"
