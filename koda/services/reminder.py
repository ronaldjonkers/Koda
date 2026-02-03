"""Active reminder system with webhook and email support."""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger


class ReminderChannel(str, Enum):
    """Reminder delivery channels."""
    WEBHOOK = "webhook"
    EMAIL = "email"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


@dataclass
class Reminder:
    """A scheduled reminder."""
    id: str
    title: str
    message: str
    trigger_at_ms: int
    channel: ReminderChannel
    recipient: str  # email, webhook URL, or chat_id
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    sent: bool = False
    sent_at_ms: int | None = None
    error: str | None = None


class ReminderStore:
    """Persistent storage for reminders."""
    
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._reminders: dict[str, Reminder] = {}
        self._load()
    
    def _load(self) -> None:
        """Load reminders from disk."""
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text())
                for r in data.get("reminders", []):
                    reminder = Reminder(
                        id=r["id"],
                        title=r["title"],
                        message=r["message"],
                        trigger_at_ms=r["trigger_at_ms"],
                        channel=ReminderChannel(r["channel"]),
                        recipient=r["recipient"],
                        metadata=r.get("metadata", {}),
                        created_at_ms=r.get("created_at_ms", 0),
                        sent=r.get("sent", False),
                        sent_at_ms=r.get("sent_at_ms"),
                        error=r.get("error")
                    )
                    self._reminders[reminder.id] = reminder
            except Exception as e:
                logger.warning(f"Failed to load reminders: {e}")
    
    def _save(self) -> None:
        """Save reminders to disk."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "reminders": [
                {
                    "id": r.id,
                    "title": r.title,
                    "message": r.message,
                    "trigger_at_ms": r.trigger_at_ms,
                    "channel": r.channel.value,
                    "recipient": r.recipient,
                    "metadata": r.metadata,
                    "created_at_ms": r.created_at_ms,
                    "sent": r.sent,
                    "sent_at_ms": r.sent_at_ms,
                    "error": r.error
                }
                for r in self._reminders.values()
            ]
        }
        self.store_path.write_text(json.dumps(data, indent=2))
    
    def add(self, reminder: Reminder) -> None:
        """Add a reminder."""
        self._reminders[reminder.id] = reminder
        self._save()
    
    def get(self, reminder_id: str) -> Reminder | None:
        """Get a reminder by ID."""
        return self._reminders.get(reminder_id)
    
    def remove(self, reminder_id: str) -> bool:
        """Remove a reminder."""
        if reminder_id in self._reminders:
            del self._reminders[reminder_id]
            self._save()
            return True
        return False
    
    def list_pending(self) -> list[Reminder]:
        """List all pending (unsent) reminders."""
        return [r for r in self._reminders.values() if not r.sent]
    
    def list_all(self) -> list[Reminder]:
        """List all reminders."""
        return list(self._reminders.values())
    
    def get_due(self, now_ms: int) -> list[Reminder]:
        """Get reminders that are due."""
        return [
            r for r in self._reminders.values()
            if not r.sent and r.trigger_at_ms <= now_ms
        ]
    
    def mark_sent(self, reminder_id: str, error: str | None = None) -> None:
        """Mark a reminder as sent."""
        if reminder_id in self._reminders:
            r = self._reminders[reminder_id]
            r.sent = True
            r.sent_at_ms = int(time.time() * 1000)
            r.error = error
            self._save()


class EmailSender:
    """Email sender using SMTP."""
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls
    
    async def send(self, to_email: str, subject: str, body: str) -> None:
        """Send an email."""
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            message = MIMEMultipart("alternative")
            message["From"] = self.from_email
            message["To"] = to_email
            message["Subject"] = subject
            
            # Add plain text version
            text_part = MIMEText(body, "plain")
            message.attach(text_part)
            
            # Add HTML version
            html_body = f"<html><body><pre>{body}</pre></body></html>"
            html_part = MIMEText(html_body, "html")
            message.attach(html_part)
            
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                use_tls=self.use_tls
            )
            
            logger.info(f"Email sent to {to_email}: {subject}")
            
        except ImportError:
            raise RuntimeError("aiosmtplib not installed")
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise


class WebhookSender:
    """Webhook sender using HTTP POST."""
    
    async def send(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Send a webhook POST request."""
        import httpx
        
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=default_headers)
            response.raise_for_status()
            
            logger.info(f"Webhook sent to {url}: status={response.status_code}")
            
            try:
                return response.json()
            except Exception:
                return {"status": response.status_code, "text": response.text}


class ReminderService:
    """
    Active reminder service with webhook and email support.
    
    Manages scheduled reminders and sends them via:
    - Webhooks (HTTP POST)
    - Email (SMTP)
    - Messaging channels (Telegram, WhatsApp)
    """
    
    def __init__(
        self,
        store_path: Path,
        email_sender: EmailSender | None = None,
        message_callback: Callable[[str, str, str], Coroutine[Any, Any, None]] | None = None
    ):
        self.store = ReminderStore(store_path)
        self.email_sender = email_sender
        self.message_callback = message_callback  # async fn(channel, recipient, message)
        self.webhook_sender = WebhookSender()
        self._timer_task: asyncio.Task | None = None
        self._running = False
    
    async def start(self) -> None:
        """Start the reminder service."""
        self._running = True
        self._schedule_next_check()
        pending = len(self.store.list_pending())
        logger.info(f"Reminder service started with {pending} pending reminders")
    
    def stop(self) -> None:
        """Stop the reminder service."""
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
    
    def _schedule_next_check(self) -> None:
        """Schedule the next reminder check."""
        if self._timer_task:
            self._timer_task.cancel()
        
        if not self._running:
            return
        
        pending = self.store.list_pending()
        if not pending:
            # Check again in 60 seconds
            self._timer_task = asyncio.create_task(self._delayed_check(60))
            return
        
        # Find next due reminder
        now_ms = int(time.time() * 1000)
        next_trigger = min(r.trigger_at_ms for r in pending)
        delay_ms = max(0, next_trigger - now_ms)
        delay_s = delay_ms / 1000
        
        self._timer_task = asyncio.create_task(self._delayed_check(delay_s))
    
    async def _delayed_check(self, delay_s: float) -> None:
        """Wait and then check for due reminders."""
        await asyncio.sleep(delay_s)
        if self._running:
            await self._check_and_send()
            self._schedule_next_check()
    
    async def _check_and_send(self) -> None:
        """Check for due reminders and send them."""
        now_ms = int(time.time() * 1000)
        due = self.store.get_due(now_ms)
        
        for reminder in due:
            await self._send_reminder(reminder)
    
    async def _send_reminder(self, reminder: Reminder) -> None:
        """Send a single reminder."""
        error = None
        
        try:
            if reminder.channel == ReminderChannel.WEBHOOK:
                payload = {
                    "id": reminder.id,
                    "title": reminder.title,
                    "message": reminder.message,
                    "triggered_at": datetime.now().isoformat(),
                    "metadata": reminder.metadata
                }
                await self.webhook_sender.send(reminder.recipient, payload)
            
            elif reminder.channel == ReminderChannel.EMAIL:
                if not self.email_sender:
                    raise RuntimeError("Email sender not configured")
                await self.email_sender.send(
                    to_email=reminder.recipient,
                    subject=f"Reminder: {reminder.title}",
                    body=reminder.message
                )
            
            elif reminder.channel in (ReminderChannel.TELEGRAM, ReminderChannel.WHATSAPP):
                if not self.message_callback:
                    raise RuntimeError("Message callback not configured")
                await self.message_callback(
                    reminder.channel.value,
                    reminder.recipient,
                    f"🔔 **Reminder: {reminder.title}**\n\n{reminder.message}"
                )
            
            logger.info(f"Reminder sent: {reminder.id} via {reminder.channel.value}")
            
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to send reminder {reminder.id}: {e}")
        
        self.store.mark_sent(reminder.id, error=error)
    
    def add_reminder(
        self,
        title: str,
        message: str,
        trigger_at: datetime | int,
        channel: ReminderChannel | str,
        recipient: str,
        metadata: dict[str, Any] | None = None
    ) -> Reminder:
        """
        Add a new reminder.
        
        Args:
            title: Reminder title.
            message: Reminder message body.
            trigger_at: When to send (datetime or ms timestamp).
            channel: Delivery channel.
            recipient: Email, webhook URL, or chat_id.
            metadata: Additional metadata.
        
        Returns:
            The created Reminder.
        """
        if isinstance(trigger_at, datetime):
            trigger_at_ms = int(trigger_at.timestamp() * 1000)
        else:
            trigger_at_ms = trigger_at
        
        if isinstance(channel, str):
            channel = ReminderChannel(channel)
        
        reminder = Reminder(
            id=str(uuid.uuid4())[:8],
            title=title,
            message=message,
            trigger_at_ms=trigger_at_ms,
            channel=channel,
            recipient=recipient,
            metadata=metadata or {}
        )
        
        self.store.add(reminder)
        self._schedule_next_check()
        
        logger.info(f"Reminder added: {reminder.id} - {title}")
        return reminder
    
    def remove_reminder(self, reminder_id: str) -> bool:
        """Remove a reminder by ID."""
        return self.store.remove(reminder_id)
    
    def list_reminders(self, pending_only: bool = True) -> list[Reminder]:
        """List reminders."""
        if pending_only:
            return self.store.list_pending()
        return self.store.list_all()
    
    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """Get a reminder by ID."""
        return self.store.get(reminder_id)
