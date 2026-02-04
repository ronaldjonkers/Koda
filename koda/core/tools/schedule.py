"""Schedule tool for creating recurring cron jobs."""

from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class ScheduleTool(BaseTool):
    """
    Tool for creating and managing scheduled/recurring tasks.
    
    Allows the agent to:
    - Create one-time scheduled tasks
    - Create recurring tasks with cron expressions
    - List, enable/disable, and delete scheduled tasks
    """
    
    name = "schedule"
    description = """Create and manage scheduled/recurring tasks. Use this for:
- Daily briefings (weather, agenda, news)
- Recurring reminders
- Scheduled reports
- Any task that should run at specific times

Actions:
- create: Create a new scheduled task
- list: Show all scheduled tasks
- get: Get details of a task
- enable: Enable a disabled task
- disable: Disable a task (keeps it but stops execution)
- delete: Remove a task permanently

Schedule types:
- at: One-time at specific datetime (ISO format)
- every: Recurring interval (e.g., "1h", "30m", "1d")
- cron: Cron expression (e.g., "0 7 * * *" = daily at 7:00)

Common cron patterns:
- "0 7 * * *" = Daily at 7:00
- "0 9 * * 1-5" = Weekdays at 9:00
- "0 */2 * * *" = Every 2 hours
- "30 8 * * 1" = Mondays at 8:30

The 'prompt' is what the agent should do when the task runs. Be specific!
Example: "Get today's weather for Amsterdam, my calendar events, and send a summary to WhatsApp"
"""
from __future__ import annotations
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "get", "enable", "disable", "delete"],
                "description": "The operation to perform"
            },
            "name": {
                "type": "string",
                "description": "For 'create': Human-readable name for the task"
            },
            "schedule_type": {
                "type": "string",
                "enum": ["at", "every", "cron"],
                "description": "For 'create': Type of schedule"
            },
            "schedule_value": {
                "type": "string",
                "description": "For 'create': Schedule value - datetime for 'at', interval for 'every' (e.g., '1h'), cron expression for 'cron'"
            },
            "timezone": {
                "type": "string",
                "description": "For 'create': Timezone (default: Europe/Amsterdam)"
            },
            "prompt": {
                "type": "string",
                "description": "For 'create': What the agent should do when this task runs. Be specific!"
            },
            "deliver_to": {
                "type": "string",
                "description": "For 'create': Where to send the result - 'whatsapp:+31612345678' or 'telegram:123456'"
            },
            "task_id": {
                "type": "string",
                "description": "For 'get', 'enable', 'disable', 'delete': Task ID"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, cron_service: Any = None):
        self.cron_service = cron_service
    
    def _parse_interval(self, value: str) -> int:
        """Parse interval string to milliseconds."""
        value = value.strip().lower()
        
        if value.endswith("ms"):
            return int(value[:-2])
        elif value.endswith("s"):
            return int(value[:-1]) * 1000
        elif value.endswith("m"):
            return int(value[:-1]) * 60 * 1000
        elif value.endswith("h"):
            return int(value[:-1]) * 60 * 60 * 1000
        elif value.endswith("d"):
            return int(value[:-1]) * 24 * 60 * 60 * 1000
        else:
            # Assume minutes if no unit
            return int(value) * 60 * 1000
    
    def _parse_datetime(self, value: str) -> int:
        """Parse datetime string to milliseconds timestamp."""
        from datetime import datetime
        
        try:
            dt = datetime.fromisoformat(value)
            return int(dt.timestamp() * 1000)
        except ValueError:
            raise ValueError(f"Invalid datetime format: {value}. Use ISO format (e.g., 2024-12-25T09:00:00)")
    
    def _format_schedule(self, schedule) -> str:
        """Format schedule for display."""
        if schedule.kind == "at":
            from datetime import datetime
            dt = datetime.fromtimestamp(schedule.at_ms / 1000)
            return f"Once at {dt.strftime('%Y-%m-%d %H:%M')}"
        elif schedule.kind == "every":
            ms = schedule.every_ms
            if ms >= 86400000:
                return f"Every {ms // 86400000} day(s)"
            elif ms >= 3600000:
                return f"Every {ms // 3600000} hour(s)"
            elif ms >= 60000:
                return f"Every {ms // 60000} minute(s)"
            else:
                return f"Every {ms // 1000} second(s)"
        elif schedule.kind == "cron":
            return f"Cron: {schedule.expr} ({schedule.tz or 'UTC'})"
        return "Unknown"
    
    def _format_job(self, job) -> str:
        """Format a job for display."""
        from datetime import datetime
        
        lines = [f"**{job.name}** (ID: `{job.id}`)"]
        lines.append(f"  Status: {'✅ Enabled' if job.enabled else '❌ Disabled'}")
        lines.append(f"  Schedule: {self._format_schedule(job.schedule)}")
        
        if job.payload.message:
            prompt_preview = job.payload.message[:100] + "..." if len(job.payload.message) > 100 else job.payload.message
            lines.append(f"  Prompt: {prompt_preview}")
        
        if job.payload.deliver and job.payload.channel:
            lines.append(f"  Deliver to: {job.payload.channel}:{job.payload.to}")
        
        if job.state.next_run_at_ms:
            next_run = datetime.fromtimestamp(job.state.next_run_at_ms / 1000)
            lines.append(f"  Next run: {next_run.strftime('%Y-%m-%d %H:%M')}")
        
        if job.state.last_run_at_ms:
            last_run = datetime.fromtimestamp(job.state.last_run_at_ms / 1000)
            lines.append(f"  Last run: {last_run.strftime('%Y-%m-%d %H:%M')} ({job.state.last_status})")
        
        return "\n".join(lines)
    
    async def execute(self, **kwargs) -> str:
        """Execute a schedule operation."""
        action = kwargs.get("action")
        
        if not self.cron_service:
            return "Error: Scheduling service not available. The scheduler may not be running."
        
        try:
            if action == "create":
                return await self._create_task(kwargs)
            elif action == "list":
                return self._list_tasks()
            elif action == "get":
                return self._get_task(kwargs.get("task_id", ""))
            elif action == "enable":
                return self._set_enabled(kwargs.get("task_id", ""), True)
            elif action == "disable":
                return self._set_enabled(kwargs.get("task_id", ""), False)
            elif action == "delete":
                return self._delete_task(kwargs.get("task_id", ""))
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Schedule tool error: {e}")
            return f"Error: {e}"
    
    async def _create_task(self, kwargs: dict) -> str:
        """Create a new scheduled task."""
        from koda.scheduler.types import CronSchedule
        
        name = kwargs.get("name", "")
        schedule_type = kwargs.get("schedule_type", "")
        schedule_value = kwargs.get("schedule_value", "")
        timezone = kwargs.get("timezone", "Europe/Amsterdam")
        prompt = kwargs.get("prompt", "")
        deliver_to = kwargs.get("deliver_to", "")
        
        if not name:
            return "Error: 'name' is required"
        if not schedule_type:
            return "Error: 'schedule_type' is required (at, every, or cron)"
        if not schedule_value:
            return "Error: 'schedule_value' is required"
        if not prompt:
            return "Error: 'prompt' is required - what should the agent do?"
        
        # Build schedule
        schedule = CronSchedule(kind=schedule_type)
        
        if schedule_type == "at":
            schedule.at_ms = self._parse_datetime(schedule_value)
        elif schedule_type == "every":
            schedule.every_ms = self._parse_interval(schedule_value)
        elif schedule_type == "cron":
            schedule.expr = schedule_value
            schedule.tz = timezone
        else:
            return f"Error: Unknown schedule_type: {schedule_type}"
        
        # Parse delivery target
        channel = None
        to = None
        deliver = bool(deliver_to)
        
        if deliver_to:
            if ":" in deliver_to:
                channel, to = deliver_to.split(":", 1)
            else:
                return "Error: deliver_to must be in format 'channel:target' (e.g., 'whatsapp:+31612345678')"
        
        # Add job via service API
        job = self.cron_service.add_job(
            name=name,
            schedule=schedule,
            message=prompt,
            deliver=deliver,
            channel=channel,
            to=to,
            delete_after_run=(schedule_type == "at")  # One-time tasks auto-delete
        )
        
        logger.info(f"Created scheduled task: {name} ({job.id})")
        
        return f"""✅ **Scheduled task created!**

{self._format_job(job)}

The task will run according to the schedule. Use `schedule list` to see all tasks."""
    
    def _list_tasks(self) -> str:
        """List all scheduled tasks."""
        jobs = self.cron_service.list_jobs()
        
        if not jobs:
            return "No scheduled tasks found. Use `schedule create` to create one."
        
        lines = [f"📅 **Scheduled Tasks** ({len(jobs)} total)\n"]
        
        for job in jobs:
            lines.append(self._format_job(job))
            lines.append("")
        
        return "\n".join(lines)
    
    def _get_task(self, task_id: str) -> str:
        """Get details of a specific task."""
        if not task_id:
            return "Error: 'task_id' is required"
        
        job = self.cron_service.get_job(task_id)
        if not job:
            return f"Error: Task '{task_id}' not found"
        
        return self._format_job(job)
    
    def _set_enabled(self, task_id: str, enabled: bool) -> str:
        """Enable or disable a task."""
        if not task_id:
            return "Error: 'task_id' is required"
        
        success = self.cron_service.set_job_enabled(task_id, enabled)
        if not success:
            return f"Error: Task '{task_id}' not found"
        
        status = "enabled" if enabled else "disabled"
        return f"✅ Task '{task_id}' has been {status}."
    
    def _delete_task(self, task_id: str) -> str:
        """Delete a task."""
        if not task_id:
            return "Error: 'task_id' is required"
        
        success = self.cron_service.remove_job(task_id)
        if not success:
            return f"Error: Task '{task_id}' not found"
        
        return f"✅ Task '{task_id}' has been deleted."
