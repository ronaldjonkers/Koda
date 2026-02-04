"""Hooks System - Event-driven automation for Koda.

Allows registering handlers for various events in the system,
enabling extensible automation and integrations.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, Union

from loguru import logger


class HookEventType(str, Enum):
    """Types of hook events."""
    # Message events
    MESSAGE_RECEIVED = "message:received"
    MESSAGE_PROCESSED = "message:processed"
    MESSAGE_SENT = "message:sent"
    
    # Session events
    SESSION_START = "session:start"
    SESSION_END = "session:end"
    
    # Agent events
    AGENT_THINKING = "agent:thinking"
    AGENT_TOOL_CALL = "agent:tool_call"
    AGENT_RESPONSE = "agent:response"
    AGENT_ERROR = "agent:error"
    
    # Gateway events
    GATEWAY_START = "gateway:start"
    GATEWAY_STOP = "gateway:stop"
    GATEWAY_CONFIG_RELOAD = "gateway:config_reload"
    
    # Email events
    EMAIL_RECEIVED = "email:received"
    EMAIL_IMPORTANT = "email:important"
    
    # Calendar events
    CALENDAR_EVENT_SOON = "calendar:event_soon"
    CALENDAR_MORNING_BRIEFING = "calendar:morning_briefing"
    
    # Schedule events
    CRON_JOB_RUN = "cron:job_run"
    REMINDER_TRIGGERED = "reminder:triggered"
    
    # Custom events
    CUSTOM = "custom"


@dataclass
class HookEvent:
    """Represents an event that can trigger hooks."""
    type: HookEventType
    action: str = ""
    session_key: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    
    def add_message(self, message: str) -> None:
        """Add a message to be sent back to the user."""
        self.messages.append(message)


# Type for hook handlers
HookHandler = Callable[[HookEvent], Union[None, asyncio.coroutine]]


class HooksManager:
    """
    Central manager for the hooks system.
    
    Allows registering handlers for specific event types or patterns,
    and triggering events throughout the system.
    """
    
    def __init__(self):
        self._handlers: dict[str, list[HookHandler]] = {}
        self._async_handlers: dict[str, list[HookHandler]] = {}
        self._enabled = True
    
    def enable(self) -> None:
        """Enable hook processing."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable hook processing."""
        self._enabled = False
    
    def register(
        self,
        event_key: str,
        handler: HookHandler,
        is_async: bool = False
    ) -> None:
        """
        Register a hook handler for an event type.
        
        Args:
            event_key: Event type or pattern (e.g., 'message:received' or 'message:*')
            handler: Function to call when event is triggered
            is_async: Whether the handler is async
        
        Example:
            hooks.register('message:received', lambda e: print(e.context))
            hooks.register('email:*', handle_email_events, is_async=True)
        """
        if is_async:
            if event_key not in self._async_handlers:
                self._async_handlers[event_key] = []
            self._async_handlers[event_key].append(handler)
        else:
            if event_key not in self._handlers:
                self._handlers[event_key] = []
            self._handlers[event_key].append(handler)
        
        logger.debug(f"Registered {'async ' if is_async else ''}hook for {event_key}")
    
    def unregister(self, event_key: str, handler: HookHandler) -> None:
        """Unregister a hook handler."""
        if event_key in self._handlers and handler in self._handlers[event_key]:
            self._handlers[event_key].remove(handler)
        if event_key in self._async_handlers and handler in self._async_handlers[event_key]:
            self._async_handlers[event_key].remove(handler)
    
    def clear(self, event_key: Optional[str] = None) -> None:
        """Clear all handlers for an event type, or all handlers if no key specified."""
        if event_key:
            self._handlers.pop(event_key, None)
            self._async_handlers.pop(event_key, None)
        else:
            self._handlers.clear()
            self._async_handlers.clear()
    
    def _get_matching_handlers(
        self,
        event_type: str,
        is_async: bool = False
    ) -> list[HookHandler]:
        """Get all handlers matching an event type (including wildcards)."""
        handlers = self._async_handlers if is_async else self._handlers
        matching = []
        
        # Exact match
        if event_type in handlers:
            matching.extend(handlers[event_type])
        
        # Wildcard matches
        parts = event_type.split(":")
        if len(parts) >= 1:
            # Match 'category:*'
            wildcard = f"{parts[0]}:*"
            if wildcard in handlers:
                matching.extend(handlers[wildcard])
        
        # Match '*' (all events)
        if "*" in handlers:
            matching.extend(handlers["*"])
        
        return matching
    
    def trigger(self, event: HookEvent) -> list[str]:
        """
        Trigger a hook event synchronously.
        
        Returns list of messages added by handlers.
        """
        if not self._enabled:
            return []
        
        event_type = f"{event.type.value}"
        if event.action:
            event_type = f"{event.type.value}:{event.action}"
        
        handlers = self._get_matching_handlers(event_type, is_async=False)
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in hook handler for {event_type}: {e}")
        
        return event.messages
    
    async def trigger_async(self, event: HookEvent) -> list[str]:
        """
        Trigger a hook event asynchronously.
        
        Runs both sync and async handlers.
        Returns list of messages added by handlers.
        """
        if not self._enabled:
            return []
        
        event_type = f"{event.type.value}"
        if event.action:
            event_type = f"{event.type.value}:{event.action}"
        
        # Run sync handlers
        sync_handlers = self._get_matching_handlers(event_type, is_async=False)
        for handler in sync_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in sync hook handler for {event_type}: {e}")
        
        # Run async handlers
        async_handlers = self._get_matching_handlers(event_type, is_async=True)
        for handler in async_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in async hook handler for {event_type}: {e}")
        
        return event.messages
    
    def get_registered_events(self) -> list[str]:
        """Get list of event types that have registered handlers."""
        events = set(self._handlers.keys()) | set(self._async_handlers.keys())
        return sorted(events)


# Global hooks manager instance
_hooks_manager: Optional[HooksManager] = None


def get_hooks_manager() -> HooksManager:
    """Get or create the global hooks manager."""
    global _hooks_manager
    if _hooks_manager is None:
        _hooks_manager = HooksManager()
    return _hooks_manager


def register_hook(
    event_key: str,
    handler: HookHandler,
    is_async: bool = False
) -> None:
    """Register a hook handler (convenience function)."""
    get_hooks_manager().register(event_key, handler, is_async)


def trigger_hook(event: HookEvent) -> list[str]:
    """Trigger a hook event synchronously (convenience function)."""
    return get_hooks_manager().trigger(event)


async def trigger_hook_async(event: HookEvent) -> list[str]:
    """Trigger a hook event asynchronously (convenience function)."""
    return await get_hooks_manager().trigger_async(event)


def create_hook_event(
    event_type: HookEventType,
    action: str = "",
    session_key: str = "",
    **context
) -> HookEvent:
    """Create a hook event (convenience function)."""
    return HookEvent(
        type=event_type,
        action=action,
        session_key=session_key,
        context=context
    )


# Built-in hooks for common automation

def setup_default_hooks() -> None:
    """Setup default built-in hooks."""
    hooks = get_hooks_manager()
    
    # Log all errors
    def log_errors(event: HookEvent):
        if event.context.get("error"):
            logger.error(f"Hook error event: {event.context['error']}")
    
    hooks.register(HookEventType.AGENT_ERROR.value, log_errors)
    
    logger.debug("Default hooks registered")


# Decorator for registering hooks
def on_event(event_key: str, is_async: bool = False):
    """
    Decorator to register a function as a hook handler.
    
    Usage:
        @on_event('message:received')
        def handle_message(event: HookEvent):
            print(f"Got message: {event.context}")
        
        @on_event('email:received', is_async=True)
        async def handle_email(event: HookEvent):
            await notify_user(event.context['email'])
    """
    def decorator(func: HookHandler) -> HookHandler:
        register_hook(event_key, func, is_async=is_async)
        return func
    return decorator
