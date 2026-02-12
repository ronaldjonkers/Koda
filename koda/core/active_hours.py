"""Active Hours and Do Not Disturb management.

Controls when Koda is active and when notifications should be suppressed.
Supports configurable active hours, DND mode, and timezone handling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from loguru import logger


@dataclass
class ActiveHoursConfig:
    """Configuration for active hours."""
    enabled: bool = True
    start_time: str = "07:00"  # HH:MM format
    end_time: str = "23:00"    # HH:MM format
    timezone: str = "Europe/Amsterdam"
    
    # Days of the week (0=Monday, 6=Sunday)
    active_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    
    # Override: always respond to these senders even outside hours
    always_respond_to: list[str] = field(default_factory=list)
    
    # Override: always suppress notifications from these senders
    always_suppress: list[str] = field(default_factory=list)


@dataclass
class DNDConfig:
    """Do Not Disturb configuration."""
    enabled: bool = False
    until: Optional[datetime] = None  # Auto-disable after this time
    reason: str = ""
    
    # Allow important/urgent messages through
    allow_important: bool = True
    
    # Senders that can bypass DND
    allow_from: list[str] = field(default_factory=list)


class ActiveHoursManager:
    """
    Manages active hours and Do Not Disturb mode.
    
    Features:
    - Configurable active hours per day
    - Do Not Disturb mode with auto-expiry
    - Timezone-aware scheduling
    - VIP list for senders who can bypass restrictions
    - Importance-based override
    """
    
    TIME_PATTERN = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')
    
    def __init__(
        self,
        active_hours: Optional[ActiveHoursConfig] = None,
        dnd: Optional[DNDConfig] = None
    ):
        self.active_hours = active_hours or ActiveHoursConfig()
        self.dnd = dnd or DNDConfig()
        self._pending_messages: list[dict] = []  # Messages to deliver when active
    
    def _parse_time(self, time_str: str) -> time:
        """Parse HH:MM string to time object."""
        match = self.TIME_PATTERN.match(time_str)
        if not match:
            raise ValueError(f"Invalid time format: {time_str}")
        return time(int(match.group(1)), int(match.group(2)))
    
    def _get_local_now(self) -> datetime:
        """Get current time in configured timezone."""
        try:
            tz = ZoneInfo(self.active_hours.timezone)
            return datetime.now(tz)
        except:
            return datetime.now()
    
    def is_active_time(self) -> bool:
        """Check if current time is within active hours."""
        if not self.active_hours.enabled:
            return True  # Always active if not enabled
        
        now = self._get_local_now()
        
        # Check day of week
        if now.weekday() not in self.active_hours.active_days:
            return False
        
        # Check time
        start = self._parse_time(self.active_hours.start_time)
        end = self._parse_time(self.active_hours.end_time)
        current = now.time()
        
        if start <= end:
            # Normal case: e.g., 07:00 to 23:00
            return start <= current <= end
        else:
            # Crosses midnight: e.g., 22:00 to 06:00
            return current >= start or current <= end
    
    def is_dnd_active(self) -> bool:
        """Check if Do Not Disturb is currently active."""
        if not self.dnd.enabled:
            return False
        
        # Check auto-expiry
        if self.dnd.until and datetime.now() >= self.dnd.until:
            self.disable_dnd()
            return False
        
        return True
    
    def should_suppress(
        self,
        sender: str = "",
        is_important: bool = False,
        message_type: str = "notification"
    ) -> tuple[bool, str]:
        """
        Check if a notification should be suppressed.
        
        Args:
            sender: The sender ID (phone number, email, etc.)
            is_important: Whether the message is marked as important
            message_type: Type of message (notification, message, reminder)
        
        Returns:
            (should_suppress, reason)
        """
        # Check always_suppress list
        if sender in self.active_hours.always_suppress:
            return True, "Sender in suppress list"
        
        # Check always_respond_to list
        if sender in self.active_hours.always_respond_to:
            return False, "Sender in VIP list"
        
        # Check DND
        if self.is_dnd_active():
            # Check DND allow list
            if sender in self.dnd.allow_from:
                return False, "Sender can bypass DND"
            
            # Check importance override
            if is_important and self.dnd.allow_important:
                return False, "Important message allowed through DND"
            
            return True, f"DND active: {self.dnd.reason}" if self.dnd.reason else "DND active"
        
        # Check active hours
        if not self.is_active_time():
            # Direct messages should still get through, just notifications suppressed
            if message_type == "message":
                return False, "Direct messages always allowed"
            
            return True, "Outside active hours"
        
        return False, ""
    
    def enable_dnd(
        self,
        duration_minutes: Optional[int] = None,
        until: Optional[datetime] = None,
        reason: str = "",
        allow_important: bool = True,
        allow_from: Optional[list[str]] = None
    ) -> str:
        """
        Enable Do Not Disturb mode.
        
        Args:
            duration_minutes: Auto-disable after this many minutes
            until: Auto-disable at this time
            reason: Reason for DND (shown in status)
            allow_important: Allow important messages through
            allow_from: List of senders who can bypass DND
        
        Returns:
            Status message
        """
        self.dnd.enabled = True
        self.dnd.reason = reason
        self.dnd.allow_important = allow_important
        
        if allow_from:
            self.dnd.allow_from = allow_from
        
        if duration_minutes:
            self.dnd.until = datetime.now() + timedelta(minutes=duration_minutes)
        elif until:
            self.dnd.until = until
        else:
            self.dnd.until = None
        
        until_str = f" until {self.dnd.until.strftime('%H:%M')}" if self.dnd.until else ""
        return f"🔕 Do Not Disturb enabled{until_str}. {'Important messages will still come through.' if allow_important else ''}"
    
    def disable_dnd(self) -> str:
        """Disable Do Not Disturb mode."""
        self.dnd.enabled = False
        self.dnd.until = None
        self.dnd.reason = ""
        return "🔔 Do Not Disturb disabled."
    
    def set_active_hours(
        self,
        start: str,
        end: str,
        days: Optional[list[int]] = None
    ) -> str:
        """
        Set active hours.
        
        Args:
            start: Start time (HH:MM)
            end: End time (HH:MM)
            days: List of weekday numbers (0=Monday)
        
        Returns:
            Status message
        """
        # Validate times
        self._parse_time(start)
        self._parse_time(end)
        
        self.active_hours.start_time = start
        self.active_hours.end_time = end
        
        if days is not None:
            self.active_hours.active_days = days
        
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days_str = ", ".join(day_names[d] for d in self.active_hours.active_days)
        
        return f"⏰ Active hours set: {start} - {end} ({days_str})"
    
    def add_vip(self, sender: str) -> str:
        """Add sender to VIP list (always respond)."""
        if sender not in self.active_hours.always_respond_to:
            self.active_hours.always_respond_to.append(sender)
        return f"✅ {sender} added to VIP list"
    
    def remove_vip(self, sender: str) -> str:
        """Remove sender from VIP list."""
        if sender in self.active_hours.always_respond_to:
            self.active_hours.always_respond_to.remove(sender)
        return f"✅ {sender} removed from VIP list"
    
    def get_status(self) -> str:
        """Get current status as a formatted string."""
        now = self._get_local_now()
        
        lines = ["📊 *Active Hours Status*\n"]
        
        # Active hours
        if self.active_hours.enabled:
            status = "✅ Active" if self.is_active_time() else "😴 Outside active hours"
            lines.append(f"*Active hours:* {self.active_hours.start_time} - {self.active_hours.end_time}")
            lines.append(f"*Status:* {status}")
        else:
            lines.append("*Active hours:* Disabled (always active)")
        
        # DND
        if self.is_dnd_active():
            until_str = f" (until {self.dnd.until.strftime('%H:%M')})" if self.dnd.until else ""
            reason_str = f" - {self.dnd.reason}" if self.dnd.reason else ""
            lines.append(f"\n🔕 *Do Not Disturb:* Active{until_str}{reason_str}")
        
        # VIP list
        if self.active_hours.always_respond_to:
            lines.append(f"\n*VIPs:* {len(self.active_hours.always_respond_to)} contacts")
        
        lines.append(f"\n_Current time: {now.strftime('%H:%M')} ({self.active_hours.timezone})_")
        
        return "\n".join(lines)
    
    def queue_message(self, message: dict) -> None:
        """Queue a message to be delivered when active hours resume."""
        message["queued_at"] = datetime.now()
        self._pending_messages.append(message)
        logger.debug(f"Queued message for later delivery (total: {len(self._pending_messages)})")
    
    def get_pending_messages(self) -> list[dict]:
        """Get and clear pending messages."""
        messages = self._pending_messages.copy()
        self._pending_messages.clear()
        return messages


# Global instance
_manager: Optional[ActiveHoursManager] = None


def get_active_hours_manager() -> ActiveHoursManager:
    """Get or create the global active hours manager."""
    global _manager
    if _manager is None:
        _manager = ActiveHoursManager()
    return _manager


def should_suppress_notification(
    sender: str = "",
    is_important: bool = False,
    message_type: str = "notification"
) -> tuple[bool, str]:
    """Check if a notification should be suppressed (convenience function)."""
    return get_active_hours_manager().should_suppress(sender, is_important, message_type)


def is_active() -> bool:
    """Check if currently in active hours and not in DND (convenience function)."""
    manager = get_active_hours_manager()
    return manager.is_active_time() and not manager.is_dnd_active()
