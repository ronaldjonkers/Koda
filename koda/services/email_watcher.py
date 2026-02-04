"""Email Watcher Service - Proactive email monitoring using IMAP IDLE.

Monitors email accounts for new messages and notifies the user via WhatsApp.
This makes Koda truly proactive - alerting you about important emails.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Any, Callable, Optional

from loguru import logger


@dataclass
class EmailNotification:
    """Represents an email notification to send to the user."""
    account_name: str
    sender: str
    subject: str
    preview: str
    received_at: datetime
    is_important: bool = False


class IMAPIdleClient:
    """
    IMAP client with IDLE support for real-time email notifications.
    
    IMAP IDLE is a push protocol - the server notifies us when new mail arrives,
    rather than us polling. This is much more efficient and responsive.
    """
    
    def __init__(
        self,
        host: str,
        email: str,
        password: str,
        port: int = 993,
        use_ssl: bool = True,
        folder: str = "INBOX",
        account_name: str = ""
    ):
        self.host = host
        self.email = email
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.folder = folder
        self.account_name = account_name or email.split("@")[0]
        
        self._imap: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None
        self._running = False
        self._last_uid: Optional[int] = None
        self._callbacks: list[Callable[[EmailNotification], None]] = []
    
    def on_new_email(self, callback: Callable[[EmailNotification], None]) -> None:
        """Register a callback for new email notifications."""
        self._callbacks.append(callback)
    
    def connect(self) -> bool:
        """Connect to the IMAP server."""
        try:
            if self.use_ssl:
                self._imap = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._imap = imaplib.IMAP4(self.host, self.port)
            
            self._imap.login(self.email, self.password)
            self._imap.select(self.folder)
            
            # Get the latest UID to avoid notifying about old emails
            self._last_uid = self._get_latest_uid()
            
            logger.info(f"📧 Connected to {self.host} as {self.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}: {e}")
            return False
    
    def _get_latest_uid(self) -> Optional[int]:
        """Get the UID of the latest email."""
        try:
            result, data = self._imap.uid("search", None, "ALL")
            if result == "OK" and data[0]:
                uids = data[0].split()
                if uids:
                    return int(uids[-1])
        except:
            pass
        return None
    
    def _check_new_emails(self) -> list[EmailNotification]:
        """Check for new emails since last check."""
        notifications = []
        
        try:
            if not self._imap:
                return notifications
            
            # Search for new emails
            if self._last_uid:
                search_criteria = f"UID {self._last_uid + 1}:*"
                result, data = self._imap.uid("search", None, search_criteria)
            else:
                result, data = self._imap.uid("search", None, "UNSEEN")
            
            if result != "OK" or not data[0]:
                return notifications
            
            uids = data[0].split()
            
            for uid in uids:
                uid_int = int(uid)
                if self._last_uid and uid_int <= self._last_uid:
                    continue
                
                notification = self._fetch_email(uid)
                if notification:
                    notifications.append(notification)
                    self._last_uid = uid_int
            
        except Exception as e:
            logger.error(f"Error checking new emails: {e}")
        
        return notifications
    
    def _fetch_email(self, uid: bytes) -> Optional[EmailNotification]:
        """Fetch email details by UID."""
        try:
            result, data = self._imap.uid("fetch", uid, "(RFC822.HEADER BODY.PEEK[TEXT])")
            if result != "OK":
                return None
            
            # Parse the email
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Decode subject
            subject = ""
            if msg["subject"]:
                decoded = decode_header(msg["subject"])
                subject = "".join(
                    part.decode(charset or "utf-8") if isinstance(part, bytes) else part
                    for part, charset in decoded
                )
            
            # Decode sender
            sender = ""
            if msg["from"]:
                decoded = decode_header(msg["from"])
                sender = "".join(
                    part.decode(charset or "utf-8") if isinstance(part, bytes) else part
                    for part, charset in decoded
                )
            
            # Get preview text
            preview = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            preview = payload.decode("utf-8", errors="ignore")[:200]
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    preview = payload.decode("utf-8", errors="ignore")[:200]
            
            # Check if important
            is_important = self._is_important_email(sender, subject)
            
            return EmailNotification(
                account_name=self.account_name,
                sender=sender,
                subject=subject,
                preview=preview.strip().replace("\n", " ")[:150],
                received_at=datetime.now(),
                is_important=is_important
            )
            
        except Exception as e:
            logger.error(f"Error fetching email {uid}: {e}")
            return None
    
    def _is_important_email(self, sender: str, subject: str) -> bool:
        """Determine if an email is important based on sender/subject."""
        important_keywords = [
            "urgent", "important", "asap", "deadline", "action required",
            "dringend", "belangrijk", "actie vereist"
        ]
        
        subject_lower = subject.lower()
        for keyword in important_keywords:
            if keyword in subject_lower:
                return True
        
        return False
    
    def _notify_callbacks(self, notification: EmailNotification) -> None:
        """Notify all registered callbacks about a new email."""
        for callback in self._callbacks:
            try:
                callback(notification)
            except Exception as e:
                logger.error(f"Error in email callback: {e}")
    
    def start_idle(self) -> None:
        """Start IDLE monitoring in a background thread."""
        self._running = True
        thread = threading.Thread(target=self._idle_loop, daemon=True)
        thread.start()
        logger.info(f"📧 Started IDLE monitoring for {self.email}")
    
    def stop(self) -> None:
        """Stop IDLE monitoring."""
        self._running = False
        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except:
                pass
            self._imap = None
        logger.info(f"📧 Stopped monitoring {self.email}")
    
    def _idle_loop(self) -> None:
        """Main IDLE loop - runs in background thread."""
        reconnect_delay = 5
        
        while self._running:
            try:
                if not self._imap:
                    if not self.connect():
                        time.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, 300)  # Max 5 min
                        continue
                    reconnect_delay = 5
                
                # Check for new emails
                notifications = self._check_new_emails()
                for notification in notifications:
                    self._notify_callbacks(notification)
                
                # Start IDLE mode
                try:
                    self._imap.send(b"IDLE\r\n")
                    
                    # Wait for response or timeout (29 minutes, per RFC 2177)
                    start = time.time()
                    while self._running and (time.time() - start) < 29 * 60:
                        # Check for new data
                        ready = self._imap.socket().recv(1, 0x40)  # MSG_PEEK
                        if ready:
                            # Exit IDLE to process
                            self._imap.send(b"DONE\r\n")
                            self._imap.readline()  # Read response
                            break
                        time.sleep(1)
                    else:
                        # Timeout - exit IDLE and restart
                        self._imap.send(b"DONE\r\n")
                        self._imap.readline()
                        
                except Exception as e:
                    logger.debug(f"IDLE error (will reconnect): {e}")
                    self._imap = None
                    
            except Exception as e:
                logger.error(f"Error in IDLE loop: {e}")
                self._imap = None
                time.sleep(5)


class EmailWatcherService:
    """
    Service that monitors multiple email accounts and sends notifications.
    
    Integrates with the gateway to send WhatsApp notifications about new emails.
    """
    
    def __init__(
        self,
        on_notification: Callable[[str, str], asyncio.coroutine],  # (recipient, message) -> None
        owner_phone: str = "",
        enabled: bool = True
    ):
        self.on_notification = on_notification
        self.owner_phone = owner_phone
        self.enabled = enabled
        self._watchers: list[IMAPIdleClient] = []
        self._important_only = False  # Only notify for important emails
        self._quiet_hours: tuple[int, int] = (23, 7)  # 23:00 - 07:00
    
    def set_quiet_hours(self, start: int, end: int) -> None:
        """Set quiet hours during which notifications are suppressed."""
        self._quiet_hours = (start, end)
    
    def set_important_only(self, value: bool) -> None:
        """Only send notifications for important emails."""
        self._important_only = value
    
    def _is_quiet_time(self) -> bool:
        """Check if current time is within quiet hours."""
        hour = datetime.now().hour
        start, end = self._quiet_hours
        
        if start > end:  # Crosses midnight
            return hour >= start or hour < end
        else:
            return start <= hour < end
    
    def add_account(
        self,
        host: str,
        email: str,
        password: str,
        port: int = 993,
        account_name: str = ""
    ) -> bool:
        """Add an email account to monitor."""
        try:
            client = IMAPIdleClient(
                host=host,
                email=email,
                password=password,
                port=port,
                account_name=account_name
            )
            
            client.on_new_email(self._handle_new_email)
            
            if client.connect():
                self._watchers.append(client)
                logger.info(f"📧 Added email watcher for {email}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to add email watcher: {e}")
            return False
    
    def add_account_from_config(self, account: dict) -> bool:
        """Add account from config dict."""
        acc_type = account.get("type", "")
        
        # Determine IMAP settings based on account type
        if acc_type == "imap" or "imap" in account.get("capabilities", []):
            return self.add_account(
                host=account.get("imap_host", account.get("host", "")),
                email=account.get("email", account.get("username", "")),
                password=account.get("password", ""),
                port=account.get("imap_port", account.get("port", 993)),
                account_name=account.get("name", "")
            )
        
        # Gmail via IMAP
        if acc_type == "google_caldav" or "gmail" in account.get("email", "").lower():
            return self.add_account(
                host="imap.gmail.com",
                email=account.get("email", ""),
                password=account.get("password", ""),
                port=993,
                account_name=account.get("name", "Gmail")
            )
        
        # Exchange/Office 365 via IMAP
        if acc_type == "exchange":
            return self.add_account(
                host="outlook.office365.com",
                email=account.get("email", ""),
                password=account.get("password", ""),
                port=993,
                account_name=account.get("name", "Exchange")
            )
        
        return False
    
    def _handle_new_email(self, notification: EmailNotification) -> None:
        """Handle a new email notification."""
        if not self.enabled:
            return
        
        # Check quiet hours
        if self._is_quiet_time() and not notification.is_important:
            logger.debug(f"Suppressing notification during quiet hours: {notification.subject}")
            return
        
        # Check important only mode
        if self._important_only and not notification.is_important:
            return
        
        # Build message
        emoji = "🔴" if notification.is_important else "📧"
        message = f"""{emoji} *Nieuwe email - {notification.account_name}*

*Van:* {notification.sender}
*Onderwerp:* {notification.subject}

_{notification.preview}_

_Wil je dat ik deze email samenvat of beantwoord?_"""
        
        # Send notification
        if self.owner_phone:
            try:
                asyncio.create_task(
                    self.on_notification(self.owner_phone, message)
                )
            except RuntimeError:
                # No event loop running, use thread-safe method
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.on_notification(self.owner_phone, message))
                loop.close()
    
    def start(self) -> None:
        """Start all email watchers."""
        for watcher in self._watchers:
            watcher.start_idle()
        logger.info(f"📧 Email watcher service started ({len(self._watchers)} accounts)")
    
    def stop(self) -> None:
        """Stop all email watchers."""
        for watcher in self._watchers:
            watcher.stop()
        self._watchers.clear()
        logger.info("📧 Email watcher service stopped")
    
    @property
    def watching_count(self) -> int:
        """Number of accounts being watched."""
        return len(self._watchers)


def create_email_watcher_from_config(config, notification_callback) -> Optional[EmailWatcherService]:
    """
    Create an EmailWatcherService from the Koda config.
    
    Args:
        config: Koda configuration object
        notification_callback: Async function(phone, message) to send notifications
    
    Returns:
        EmailWatcherService or None if no email accounts configured
    """
    try:
        accounts = config.integrations.accounts or []
        owner_phone = config.channels.whatsapp.owner_phone
        
        # Filter accounts with email capability
        email_accounts = [
            acc for acc in accounts
            if hasattr(acc, 'capabilities') and 'email' in (acc.capabilities or [])
            or hasattr(acc, 'type') and acc.type in ['imap', 'exchange']
            or (hasattr(acc, 'email') and acc.email and 'gmail' in acc.email.lower())
        ]
        
        if not email_accounts:
            logger.debug("No email accounts configured for watching")
            return None
        
        service = EmailWatcherService(
            on_notification=notification_callback,
            owner_phone=owner_phone,
            enabled=True
        )
        
        for acc in email_accounts:
            acc_dict = acc.model_dump() if hasattr(acc, 'model_dump') else acc
            service.add_account_from_config(acc_dict)
        
        return service
        
    except Exception as e:
        logger.error(f"Failed to create email watcher: {e}")
        return None
