"""WhatsApp channel implementation using Node.js bridge.

Supports:
- Bot mode: Respond to all incoming messages
- Per-contact rules: Custom instructions per phone number
- Owner escalation: Notify owner for appointments/urgent requests
- Message viewing from all numbers
- WhatsApp commands (/help, /status, /name, etc.)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

from loguru import logger

from koda.messaging.events import InboundMessage, OutboundMessage
from koda.messaging.queue import MessageBus
from koda.services.base import BaseChannel
from koda.config.schema import WhatsAppConfig, WhatsAppContactRule
from koda.config.loader import load_config, save_config


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel that connects to a Node.js bridge.
    
    The bridge uses @whiskeysockets/baileys to handle the WhatsApp Web protocol.
    Communication between Python and Node.js is via WebSocket.
    
    Features:
    - Bot mode: Respond to everyone with AI-powered replies
    - Per-contact rules: Custom instructions per contact
    - Owner escalation: Forward important requests to owner
    - Full message visibility: View all incoming messages
    - WhatsApp commands for configuration (/help, /addmail, /addcalendar, etc.)
    """
    
    name = "whatsapp"
    
    def __init__(
        self,
        config: WhatsAppConfig,
        bus: MessageBus,
        assistant_name: str = "Koda",
        on_escalation: Callable[[str, str, str], Coroutine[Any, Any, None]] | None = None
    ):
        super().__init__(config, bus)
        self.config: WhatsAppConfig = config
        self.assistant_name = assistant_name
        self.on_escalation = on_escalation  # Callback for escalations
        self._ws = None
        self._connected = False
        self._contact_rules: dict[str, WhatsAppContactRule] = {}
        self._setup_sessions: dict[str, dict] = {}  # Track step-by-step setup sessions
        self._load_contact_rules()
    
    async def start(self) -> None:
        """Start the WhatsApp channel by connecting to the bridge."""
        import websockets
        
        bridge_url = self.config.bridge_url
        
        logger.info(f"🔌 Connecting to WhatsApp bridge at {bridge_url}...")
        
        self._running = True
        
        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("✅ Connected to WhatsApp bridge - listening for messages...")
                    
                    # Listen for messages
                    async for message in ws:
                        try:
                            logger.debug(f"📩 Raw bridge message: {message[:200]}...")
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error(f"Error handling bridge message: {e}", exc_info=True)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning(f"WhatsApp bridge connection error: {e}")
                
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
    
    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        self._running = False
        self._connected = False
        
        if self._ws:
            await self._ws.close()
            self._ws = None
    
    def reload_config(self, new_config) -> None:
        """Reload configuration without restarting the channel."""
        self.config = new_config
        self._load_contact_rules()
        logger.info("WhatsApp config reloaded (allow_from, contact_rules, etc.)")
    
    @staticmethod
    def _normalize_jid(chat_id: str) -> str:
        """Normalize a phone number or JID to proper WhatsApp JID format.
        
        Ensures format is: <number>@s.whatsapp.net (for individual chats)
        or <id>@g.us (for groups).
        """
        if not chat_id:
            return chat_id
        
        # Already a proper JID
        if "@" in chat_id:
            return chat_id
        
        # Strip + prefix and any spaces/dashes
        number = chat_id.replace("+", "").replace(" ", "").replace("-", "")
        
        return f"{number}@s.whatsapp.net"
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WhatsApp."""
        if not self._ws or not self._connected:
            logger.warning("⚠️ WhatsApp bridge not connected - cannot send message")
            return
        
        if not msg.content:
            logger.warning("⚠️ Skipping empty WhatsApp message")
            return
        
        # Normalize chat_id to proper JID format
        jid = self._normalize_jid(msg.chat_id)
        
        try:
            payload = {
                "type": "send",
                "to": jid,
                "text": msg.content
            }
            logger.info(f"📤 Sending WhatsApp message to {msg.chat_id[:20]}... ({len(msg.content)} chars)")
            await self._ws.send(json.dumps(payload))
            logger.info(f"✅ WhatsApp message sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending WhatsApp message: {e}")
    
    async def set_typing_indicator(self, chat_id: str, is_typing: bool = True) -> None:
        """Set typing indicator (composing/paused) for a chat."""
        if not self._ws or not self._connected:
            return
        
        try:
            payload = {
                "type": "typing",
                "to": self._normalize_jid(chat_id),
                "isTyping": is_typing
            }
            await self._ws.send(json.dumps(payload))
            status = "typing" if is_typing else "stopped"
            logger.debug(f"📝 Typing indicator {status} for {chat_id[:20]}...")
        except Exception as e:
            logger.debug(f"Typing indicator error (non-critical): {e}")
    
    async def send_image(self, chat_id: str, image_data: bytes, caption: str | None = None) -> None:
        """Send an image through WhatsApp.
        
        Args:
            chat_id: WhatsApp JID to send to
            image_data: Raw image bytes
            caption: Optional caption text
        """
        if not self._ws or not self._connected:
            logger.warning("⚠️ WhatsApp bridge not connected - cannot send image")
            return
        
        try:
            import base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "type": "image",
                "to": self._normalize_jid(chat_id),
                "imageData": image_b64,
                "caption": caption
            }
            logger.info(f"📤 Sending image to {chat_id[:20]}... ({len(image_data)} bytes)")
            await self._ws.send(json.dumps(payload))
            logger.info(f"✅ Image sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending image: {e}")
    
    async def send_file(self, chat_id: str, file_data: bytes, filename: str, caption: str | None = None) -> None:
        """Send a file through WhatsApp.
        
        Args:
            chat_id: WhatsApp JID to send to
            file_data: Raw file bytes
            filename: Name of the file
            caption: Optional caption text
        """
        if not self._ws or not self._connected:
            logger.warning("⚠️ WhatsApp bridge not connected - cannot send file")
            return
        
        try:
            import base64
            file_b64 = base64.b64encode(file_data).decode('utf-8')
            
            payload = {
                "type": "file",
                "to": self._normalize_jid(chat_id),
                "fileData": file_b64,
                "filename": filename,
                "caption": caption
            }
            logger.info(f"📤 Sending file '{filename}' to {chat_id[:20]}... ({len(file_data)} bytes)")
            await self._ws.send(json.dumps(payload))
            logger.info(f"✅ File sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending file: {e}")
    
    async def send_video(self, chat_id: str, video_data: bytes, caption: str | None = None) -> None:
        """Send a video through WhatsApp.
        
        Args:
            chat_id: WhatsApp JID to send to
            video_data: Raw video bytes
            caption: Optional caption text
        """
        if not self._ws or not self._connected:
            logger.warning("⚠️ WhatsApp bridge not connected - cannot send video")
            return
        
        try:
            import base64
            video_b64 = base64.b64encode(video_data).decode('utf-8')
            
            payload = {
                "type": "video",
                "to": self._normalize_jid(chat_id),
                "videoData": video_b64,
                "caption": caption
            }
            logger.info(f"📤 Sending video to {chat_id[:20]}... ({len(video_data)} bytes)")
            await self._ws.send(json.dumps(payload))
            logger.info(f"✅ Video sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending video: {e}")
    
    def _load_contact_rules(self) -> None:
        """Load contact rules into a lookup dict."""
        self._contact_rules = {}
        for rule in self.config.contact_rules:
            # Normalize phone number (remove spaces, ensure + prefix)
            phone = rule.phone.replace(" ", "").replace("-", "")
            if phone and not phone.startswith("+"):
                phone = "+" + phone
            self._contact_rules[phone] = rule
    
    def _get_contact_rule(self, phone: str) -> WhatsAppContactRule | None:
        """Get the contact rule for a phone number."""
        # Normalize the phone number
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            normalized = "+" + normalized
        
        return self._contact_rules.get(normalized)
    
    def _should_escalate(self, content: str, contact_rule: WhatsAppContactRule | None, sender_phone: str = "") -> bool:
        """Check if a message should be escalated to the owner."""
        if not self.config.escalate_to_owner:
            return False
        
        # Never escalate self-messages (from owner or bot phone)
        normalized_sender = sender_phone.replace('+', '').lstrip('0')
        if self.config.owner_phone:
            normalized_owner = self.config.owner_phone.replace('+', '').lstrip('0')
            if normalized_sender == normalized_owner:
                return False
        if self.config.bot_phone:
            normalized_bot = self.config.bot_phone.replace('+', '').lstrip('0')
            if normalized_sender == normalized_bot:
                return False
        
        content_lower = content.lower()
        
        # Check contact-specific escalation keywords
        if contact_rule and contact_rule.escalate_keywords:
            for keyword in contact_rule.escalate_keywords:
                if keyword.lower() in content_lower:
                    return True
        
        # Check global escalation keywords
        for keyword in self.config.escalation_keywords:
            if keyword.lower() in content_lower:
                return True
        
        return False
    
    async def _notify_owner(self, sender_phone: str, sender_name: str, message: str) -> None:
        """Notify the owner about an escalation."""
        if not self.config.owner_phone:
            logger.warning("Escalation triggered but no owner_phone configured")
            return
        
        owner_jid = f"{self.config.owner_phone.replace('+', '')}@s.whatsapp.net"
        
        notification = (
            f"📢 *Message that needs your attention*\n\n"
            f"From: {sender_name or sender_phone}\n"
            f"Number: {sender_phone}\n\n"
            f"Message:\n{message}\n\n"
            f"_Reply directly to this number if action is needed._"
        )
        
        await self.send(OutboundMessage(
            channel="whatsapp",
            chat_id=owner_jid,
            content=notification
        ))
        
        logger.info(f"Escalated message from {sender_phone} to owner")
        
        # Call the escalation callback if set
        if self.on_escalation:
            await self.on_escalation(sender_phone, sender_name, message)
    
    def _get_greeting(self) -> str:
        """Get the greeting message with placeholders filled in."""
        greeting = self.config.default_greeting
        return greeting.format(
            assistant_name=self.assistant_name,
            owner_name=self.config.owner_name or "de eigenaar"
        )
    
    def _get_instructions_for_contact(self, phone: str) -> str:
        """Get custom instructions for a contact, or default instructions."""
        rule = self._get_contact_rule(phone)
        if rule and rule.instructions:
            return rule.instructions
        return self.config.default_instructions
    
    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.
        
        In bot_mode, everyone is allowed.
        Otherwise, check the allow_from list.
        """
        # Bot mode: allow everyone
        if self.config.bot_mode:
            return True
        
        # Check contact rules - if they have a rule, they're allowed
        if self._get_contact_rule(sender_id):
            return True
        
        # Fall back to standard allow list
        return super().is_allowed(sender_id)
    
    async def _handle_command(self, command: str, args: str, chat_id: str, phone: str) -> str | None:
        """
        Handle a WhatsApp command. Returns response text or None if not a command.
        """
        config = load_config()
        
        if command == "/help":
            return """📋 *Available commands:*

*Information:*
/help - Show this help
/status - Show current settings
/accounts - Show all configured accounts

*Basic settings:*
/name <name> - Set your name
/assistant <name> - Set assistant name
/language <code> - Set language (nl, en, de, fr, es)
/style <style> - Set style (professional, friendly, formal)

*Add accounts:*
/addmail - Add email account
/addcalendar - Add calendar account
/addlinkedin - Add LinkedIn account
/addbrave <api_key> - Set Brave Search API key

*Remove accounts:*
/removemail <name> - Remove email account
/removecalendar <name> - Remove calendar account
/removelinkedin - Remove LinkedIn account

*Image Generation:*
/imageproviders - Show image provider status
/addimagekey <provider> <key> - Add API key (gemini, stability, openrouter, replicate)
/setimageprovider <name> - Set default provider (pollinations, gemini, openrouter, etc)

*Public Events:*
/events - Show upcoming events (sports, concerts)
/addevent <source> - Import events (f1, football <team>, ical <url>)
/teams - List your subscribed teams
/addteam <name> - Subscribe to a sports team
/removeteam <name> - Unsubscribe from a team
/search events <keyword> - Search for events

*Your Profile:*
/profile - Show your personal profile
/learnme - Answer a question to help me learn about you

*Schedules:*
/schedules - Show all scheduled tasks
/delschedule <id> - Delete a scheduled task

*Google Workspace (volledig):*
/googlestatus - Show Google connection status
/setupgoogle - Get setup instructions for full Google access

*Google Calendar (eenvoudig):*
/addgoogle <email> <app_password> - Add Google Calendar via App Password
/googlehelp - Setup instructions for Google Calendar
/googlemeet - Get a Google Meet link instantly

*Other:*
/cancel - Cancel active setup
/resetlinkedin - Reset LinkedIn (clear cookies, force re-login)"""

        elif command == "/status":
            assistant = config.assistant
            wa = config.channels.whatsapp
            mode = "Bot Mode (everyone)" if wa.bot_mode else "Restricted Mode"
            allowed = ", ".join(wa.allow_from) if wa.allow_from else "nobody"
            
            # Count accounts
            email_count = len(config.integrations.email_accounts) if hasattr(config.integrations, 'email_accounts') else 0
            cal_count = len(config.integrations.calendar_accounts) if hasattr(config.integrations, 'calendar_accounts') else 0
            
            return f"""⚙️ *Current settings:*

*Assistant:*
• Name: {assistant.name}
• Your name: {assistant.user_name or '(not set)'}
• Language: {assistant.language}
• Style: {assistant.personality}

*WhatsApp:*
• Mode: {mode}
• Allowed: {allowed}

*Accounts:*
• Email accounts: {email_count}
• Calendar accounts: {cal_count}

*Model:* {config.agents.defaults.model}

_Use /accounts for details_"""

        elif command == "/accounts":
            return self._format_accounts(config)
        
        elif command == "/name":
            if not args:
                return "❌ Usage: `/name <your name>`\nExample: `/name Ronald`"
            config.assistant.user_name = args
            save_config(config)
            return f"✅ Your name has been set to: *{args}*"
        
        elif command == "/assistant":
            if not args:
                return "❌ Usage: `/assistant <name>`\nExample: `/assistant Joyce`"
            config.assistant.name = args
            save_config(config)
            return f"✅ Assistant name has been set to: *{args}*"
        
        elif command == "/language":
            valid_langs = ["nl", "en", "de", "fr", "es"]
            if not args or args.lower() not in valid_langs:
                return f"❌ Usage: `/language <code>`\nValid codes: {', '.join(valid_langs)}"
            config.assistant.language = args.lower()
            save_config(config)
            lang_names = {"nl": "Nederlands", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español"}
            return f"✅ Language set to: *{lang_names.get(args.lower(), args)}*"
        
        elif command == "/style":
            valid_styles = ["professional", "friendly", "formal"]
            if not args or args.lower() not in valid_styles:
                return f"❌ Usage: `/style <style>`\nValid styles: {', '.join(valid_styles)}"
            config.assistant.personality = args.lower()
            save_config(config)
            return f"✅ Style set to: *{args.lower()}*"
        
        elif command == "/addmail":
            if args.lower() == "json":
                return self._start_json_setup(phone, "email")
            return self._start_email_setup(phone)
        
        elif command == "/addcalendar":
            if args.lower() == "json":
                return self._start_json_setup(phone, "calendar")
            return self._start_calendar_setup(phone)
        
        elif command == "/removemail":
            if not args:
                return "❌ Usage: `/removemail <name>`\nUse /accounts to see names."
            return self._remove_account(config, "email", args)
        
        elif command == "/removecalendar":
            if not args:
                return "❌ Usage: `/removecalendar <name>`\nUse /accounts to see names."
            return self._remove_account(config, "calendar", args)
        
        elif command == "/cancel":
            if phone in self._setup_sessions:
                del self._setup_sessions[phone]
                return "✅ Setup cancelled."
            return "ℹ️ No active setup to cancel."
        
        elif command == "/addlinkedin":
            return self._start_linkedin_setup(phone)
        
        elif command == "/removelinkedin":
            return self._remove_linkedin(config)
        
        elif command == "/addbrave":
            if not args:
                return """❌ Usage: `/addbrave <api_key>`

Get your API key from: https://brave.com/search/api/

Example: `/addbrave BSA1234567890abcdef`"""
            config.tools.web.search.api_key = args.strip()
            save_config(config)
            return "✅ Brave Search API key saved! Web search is now enabled."
        
        elif command == "/schedules":
            return self._list_schedules()
        
        elif command == "/delschedule":
            if not args:
                return "❌ Usage: `/delschedule <id>`\nUse /schedules to see IDs."
            return self._delete_schedule(args.strip())
        
        elif command == "/resetlinkedin":
            return self._reset_linkedin()
        
        elif command == "/linkedinstatus":
            return self._linkedin_status()
        
        elif command == "/googlehelp":
            return self._google_setup_help()
        
        elif command == "/addgoogle":
            if not args:
                return "❌ Usage: `/addgoogle <email> <app_password>`\n\nExample:\n`/addgoogle jouw.email@gmail.com abcdefghijklmnop`\n\nUse /googlehelp for setup instructions."
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                return "❌ Both email and app_password required.\n\nUsage: `/addgoogle <email> <app_password>`"
            return self._add_google_calendar(parts[0], parts[1])
        
        elif command == "/googlestatus":
            return self._google_workspace_status()
        
        elif command == "/setupgoogle":
            return self._google_workspace_setup_help()
        
        elif command == "/googlemeet":
            return self._create_quick_meet()
        
        elif command == "/imageproviders":
            return self._image_providers_status()
        
        elif command == "/addimagekey":
            if not args:
                return """❌ Usage: `/addimagekey <provider> <api_key>`

Providers:
• openrouter - Uses your OpenRouter key
• stability - Stability AI API key
• replicate - Replicate API key

Example:
`/addimagekey stability sk-xxx...`

Pollinations (free) doesn't need a key:
`/addimagekey pollinations`"""
            return self._add_image_key(args)
        
        elif command == "/setimageprovider":
            if not args:
                return """❌ Usage: `/setimageprovider <provider>`

Set the default image generation provider:
• pollinations - Free, no signup needed (recommended)
• openrouter - Uses existing OpenRouter key
• stability - Stability AI (requires key)
• replicate - Replicate platform (requires key)

Example:
`/setimageprovider pollinations`"""
            return self._set_image_provider(args.strip().lower())
        
        # ============================================================================
        # Public Events
        # ============================================================================
        
        elif command == "/events":
            return await self._list_public_events(args)
        
        elif command == "/addevent":
            if not args:
                return """❌ Usage: `/addevent <source>`

Import public events:
• `f1` - Formula 1 race calendar
• `football <team>` - Football team matches
• `ical <url>` - Import from iCal feed

Examples:
`/addevent f1`
`/addevent football Feyenoord`
`/addevent ical https://example.com/calendar.ics`"""
            return await self._add_public_event(args)
        
        elif command == "/teams":
            return self._list_teams()
        
        elif command == "/addteam":
            if not args:
                return "❌ Usage: `/addteam <team name>`\n\nExample: `/addteam Feyenoord`"
            return await self._add_team(args)
        
        elif command == "/removeteam":
            if not args:
                return "❌ Usage: `/removeteam <team name>`"
            return self._remove_team(args)
        
        elif command == "/search events":
            if not args:
                return "❌ Usage: `/search events <keyword>`"
            return await self._search_public_events(args)
        
        # ============================================================================
        # User Profile
        # ============================================================================
        
        elif command == "/profile":
            return self._show_user_profile()
        
        elif command == "/learnme":
            return await self._trigger_profiling_question()
        
        return None  # Not a recognized command
    
    def _format_accounts(self, config) -> str:
        """Format configured accounts for display."""
        lines = ["📧 *Configured Accounts:*\n"]
        
        # Get unified accounts
        accounts = getattr(config.integrations, 'accounts', []) or []
        
        if accounts:
            for acc in accounts:
                # Handle both dict and Pydantic model
                if hasattr(acc, 'name'):
                    name = acc.name
                    acc_type = acc.type
                    email = acc.email or acc.username or ""
                    caps = acc.capabilities or []
                else:
                    name = acc.get('name', 'unnamed')
                    acc_type = acc.get('type', 'unknown')
                    email = acc.get('email', acc.get('username', ''))
                    caps = acc.get('capabilities', [])
                
                caps_str = ", ".join(caps) if caps else acc_type
                lines.append(f"• *{name}* ({acc_type})")
                lines.append(f"  📧 {email}")
                lines.append(f"  🔧 {caps_str}")
                lines.append("")
        else:
            lines.append("No accounts configured yet.")
        
        lines.append("")
        
        # LinkedIn
        linkedin = getattr(config.integrations, 'linkedin', None)
        if linkedin and linkedin.enabled:
            lines.append(f"*LinkedIn:* ✅ {linkedin.email}")
        else:
            lines.append("*LinkedIn:* Not configured")
        
        # Brave Search
        brave_key = getattr(config.tools.web.search, 'api_key', '')
        if brave_key:
            lines.append(f"*Web Search:* ✅ Brave API configured")
        else:
            lines.append("*Web Search:* Not configured")
        
        lines.append("\n_Use /addmail, /addcalendar, /addlinkedin, /addbrave_")
        return "\n".join(lines)
    
    def _list_schedules(self) -> str:
        """List all scheduled tasks."""
        import json
        from koda.config.loader import get_data_dir
        from datetime import datetime
        
        cron_path = get_data_dir() / "cron" / "jobs.json"
        
        if not cron_path.exists():
            return "📅 *Scheduled Tasks:*\n\nNo scheduled tasks yet."
        
        try:
            data = json.loads(cron_path.read_text())
            jobs = data.get("jobs", [])
            
            if not jobs:
                return "📅 *Scheduled Tasks:*\n\nNo scheduled tasks yet."
            
            lines = ["📅 *Scheduled Tasks:*\n"]
            
            for job in jobs:
                job_id = job.get("id", "?")
                name = job.get("name", "Unnamed")
                enabled = "✅" if job.get("enabled", True) else "⏸️"
                schedule = job.get("schedule", {})
                
                # Format schedule
                kind = schedule.get("kind", "?")
                if kind == "cron":
                    sched_str = f"cron: `{schedule.get('expr', '?')}`"
                elif kind == "every":
                    every_ms = schedule.get("everyMs", 0)
                    if every_ms:
                        hours = every_ms // 3600000
                        mins = (every_ms % 3600000) // 60000
                        if hours:
                            sched_str = f"every {hours}h{mins}m" if mins else f"every {hours}h"
                        else:
                            sched_str = f"every {mins}m"
                    else:
                        sched_str = "every ?"
                elif kind == "at":
                    at_ms = schedule.get("atMs", 0)
                    if at_ms:
                        dt = datetime.fromtimestamp(at_ms / 1000)
                        sched_str = f"at {dt.strftime('%Y-%m-%d %H:%M')}"
                    else:
                        sched_str = "at ?"
                else:
                    sched_str = kind
                
                # Next run
                state = job.get("state", {})
                next_run_ms = state.get("nextRunAtMs")
                if next_run_ms:
                    next_dt = datetime.fromtimestamp(next_run_ms / 1000)
                    next_str = next_dt.strftime("%d/%m %H:%M")
                else:
                    next_str = "-"
                
                lines.append(f"{enabled} *{name}* (`{job_id}`)")
                lines.append(f"   {sched_str}")
                lines.append(f"   Next: {next_str}")
                lines.append("")
            
            lines.append("_Use `/delschedule <id>` to delete_")
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error listing schedules: {e}")
            return f"❌ Error loading schedules: {e}"
    
    def _delete_schedule(self, job_id: str) -> str:
        """Delete a scheduled task by ID."""
        import json
        from koda.config.loader import get_data_dir
        
        cron_path = get_data_dir() / "cron" / "jobs.json"
        
        if not cron_path.exists():
            return "❌ No schedules found."
        
        try:
            data = json.loads(cron_path.read_text())
            jobs = data.get("jobs", [])
            
            # Find and remove job
            original_count = len(jobs)
            jobs = [j for j in jobs if j.get("id") != job_id]
            
            if len(jobs) == original_count:
                return f"❌ Schedule `{job_id}` not found.\nUse /schedules to see IDs."
            
            # Save back
            data["jobs"] = jobs
            cron_path.write_text(json.dumps(data, indent=2))
            
            return f"✅ Schedule `{job_id}` deleted."
            
        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            return f"❌ Error deleting schedule: {e}"
    
    def _start_linkedin_setup(self, phone: str) -> str:
        """Start LinkedIn setup with Playwright browser login."""
        return """🔗 *LinkedIn Setup (Browser Login)*

The LinkedIn integration uses a browser session for more stability.

*One-time setup:*
1. Open a terminal on your computer
2. Run this command:
```
koda setup-linkedin
```
3. Log in via the browser that opens
4. Press Enter in the terminal when done

*Benefits:*
✅ More stable than email/password
✅ No issues with 2FA
✅ Session is preserved
✅ Posting and analytics support

*Current status:*
Use `/linkedinstatus` to check if the session is active."""
    
    def _remove_linkedin(self, config) -> str:
        """Remove LinkedIn configuration and browser profile."""
        from pathlib import Path
        import shutil
        
        removed = []
        
        # Remove config settings
        if config.integrations.linkedin.enabled:
            config.integrations.linkedin.enabled = False
            config.integrations.linkedin.email = ""
            config.integrations.linkedin.password = ""
            save_config(config)
            removed.append("Config settings")
        
        # Remove browser profile
        browser_path = Path.home() / ".koda" / "linkedin_browser"
        if browser_path.exists():
            try:
                shutil.rmtree(browser_path)
                removed.append("Browser session")
            except Exception as e:
                logger.error(f"Failed to remove browser profile: {e}")
        
        # Remove old cookies
        cookies_path = Path.home() / ".koda" / "linkedin_cookies.json"
        if cookies_path.exists():
            cookies_path.unlink()
            removed.append("Cookies")
        
        # Remove style profile
        style_path = Path.home() / ".koda" / "linkedin_style.json"
        if style_path.exists():
            style_path.unlink()
            removed.append("Style profile")
        
        if removed:
            return f"✅ LinkedIn removed:\n• " + "\n• ".join(removed) + "\n\nUse `/addlinkedin` to reconfigure."
        return "ℹ️ LinkedIn was not configured."
    
    def _reset_linkedin(self) -> str:
        """Reset LinkedIn by clearing browser profile for fresh login."""
        from pathlib import Path
        import shutil
        
        browser_path = Path.home() / ".koda" / "linkedin_browser"
        cookies_path = Path.home() / ".koda" / "linkedin_cookies.json"
        
        try:
            cleared = []
            
            if browser_path.exists():
                shutil.rmtree(browser_path)
                cleared.append("Browser session")
            
            if cookies_path.exists():
                cookies_path.unlink()
                cleared.append("Cookies")
            
            if cleared:
                return f"""✅ *LinkedIn Reset*

Removed: {', '.join(cleared)}

*Log in again:*
```
koda setup-linkedin
```

This opens a browser for manual login."""
            else:
                return "ℹ️ No LinkedIn session found. Run `koda setup-linkedin` to log in."
        except Exception as e:
            logger.error(f"Error resetting LinkedIn: {e}")
            return f"❌ Error resetting LinkedIn: {e}"
    
    def _create_quick_meet(self) -> str:
        """Create a quick Google Meet link."""
        try:
            from koda.core.tools.google_meet import GoogleMeetTool
            meet_tool = GoogleMeetTool()
            
            if not meet_tool._available:
                return """❌ **Google Workspace not connected**

To create Meet links you need to connect Google first:
1. Run `koda setup-google` in terminal
2. Or use `/setupgoogle` for instructions"""
            
            meet_link = meet_tool.get_quick_meet_link()
            
            if meet_link:
                return f"""🔗 *Google Meet Link*

{meet_link}

_Ready to use, does not expire._"""
            else:
                return "❌ Could not create Meet link. Check Google connection with `/googlestatus`"
        except Exception as e:
            logger.error(f"Failed to create Meet link: {e}")
            return f"❌ Error: {e}"
    
    def _linkedin_status(self) -> str:
        """Check LinkedIn session status."""
        from pathlib import Path
        
        browser_path = Path.home() / ".koda" / "linkedin_browser"
        style_path = Path.home() / ".koda" / "linkedin_style.json"
        
        status_lines = ["🔗 *LinkedIn Status*\n"]
        
        # Check browser session
        if browser_path.exists():
            # Check if there are actual session files
            session_files = list(browser_path.glob("**/Cookies*")) + list(browser_path.glob("**/Local Storage*"))
            if session_files:
                status_lines.append("✅ Browser session: Active")
            else:
                status_lines.append("⚠️ Browser session: Empty (login required)")
        else:
            status_lines.append("❌ Browser session: Not found")
        
        # Check style profile
        if style_path.exists():
            try:
                import json
                with open(style_path) as f:
                    style = json.load(f)
                lang = style.get("language", "?")
                tone = style.get("tone", "?")
                status_lines.append(f"✅ Style profile: {lang}, {tone}")
            except:
                status_lines.append("⚠️ Style profile: Corrupt")
        else:
            status_lines.append("ℹ️ Style profile: Not learned yet")
        
        status_lines.append("\n*Commands:*")
        status_lines.append("• `koda setup-linkedin` - Log in")
        status_lines.append("• `/resetlinkedin` - Clear session")
        status_lines.append("• `/removelinkedin` - Remove everything")
        
        return "\n".join(status_lines)
    
    def _google_setup_help(self) -> str:
        """Return Google Calendar setup instructions."""
        return """📅 *Google Calendar Setup (Simple)*

This method connects Google Calendar without API keys or OAuth - as simple as an email client!

*Step 1: 2-Step Verification*
Go to myaccount.google.com/security and make sure 2-Step Verification is ON.

*Step 2: Create App Password*
📖 Detailed guide: https://support.google.com/mail/answer/185833

Short:
1. Go to: myaccount.google.com/apppasswords
2. Click "Select app" → "Other (custom name)"
3. Type: "Koda"
4. Click "Generate"
5. You'll get a 16-letter code (e.g.: abcd efgh ijkl mnop)

*Step 3: Connect*
Send:
`/addgoogle your.email@gmail.com abcdefghijklmnop`

(without spaces in the password)

*Important:*
• Store the password safely
• You can revoke it via myaccount.google.com/apppasswords
• This works indefinitely (no expiring tokens)"""
    
    def _add_google_calendar(self, email: str, app_password: str) -> str:
        """Add Google Calendar via CalDAV with App Password."""
        try:
            from koda.integrations.google_caldav import GoogleCalDAVClient
            from koda.config.loader import load_config, save_config
            
            # Clean up password (remove spaces)
            app_password = app_password.replace(" ", "")
            
            # Test connection
            client = GoogleCalDAVClient(email, app_password)
            success, message = client.test_connection()
            
            if not success:
                return f"""❌ *Connection failed*

{message}

*Check:*
• Is 2-Step Verification enabled?
• Are you using an App Password (16 letters)?
• Is the email address correct?

Use /googlehelp for instructions."""
            
            # Save to config as a calendar account
            config = load_config()
            
            # Create account entry
            account = {
                "name": f"Google ({email.split('@')[0]})",
                "type": "google_caldav",
                "email": email,
                "password": app_password,
                "enabled": True,
                "capabilities": ["calendar"]
            }
            
            # Add to accounts list
            if not hasattr(config.integrations, 'accounts') or config.integrations.accounts is None:
                config.integrations.accounts = []
            
            # Check if already exists
            existing_idx = None
            for i, acc in enumerate(config.integrations.accounts):
                acc_email = acc.email if hasattr(acc, 'email') else acc.get('email', '')
                if acc_email == email:
                    existing_idx = i
                    break
            
            if existing_idx is not None:
                config.integrations.accounts[existing_idx] = account
                action = "updated"
            else:
                config.integrations.accounts.append(account)
                action = "added"
            
            save_config(config)
            
            # Get calendar names
            calendars = client.list_calendars()
            cal_names = [c['name'] for c in calendars[:5]]
            
            return f"""✅ *Google Calendar {action}!*

📧 Account: {email}
📅 Calendars: {', '.join(cal_names)}

You can now ask:
• "What's on my calendar today?"
• "Schedule a meeting tomorrow at 2pm"
• "Show my appointments this week"

_Tip: You can add multiple Google accounts!_"""
            
        except ImportError:
            return "❌ caldav package not installed. Run: pip install caldav"
        except Exception as e:
            logger.error(f"Error adding Google Calendar: {e}")
            return f"❌ Error: {e}\n\nUse /googlehelp for setup instructions."
    
    def _google_workspace_status(self) -> str:
        """Get Google Workspace connection status."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            
            client = GoogleWorkspaceClient()
            status = client.get_status()
            
            if status["authorized"]:
                calendars = client.list_calendars()
                cal_list = "\n".join([f"  • {c.name}" + (" (primary)" if c.is_primary else "") for c in calendars[:10]])
                
                return f"""✅ *Google Workspace Connected*

📧 Account: {status['email']}
📅 Calendars: {len(calendars)}

{cal_list}

*Available features:*
• Read and send Gmail
• Calendar events (incl. shared calendars)
• Create Google Meet links

_Use /setupgoogle for re-authorization_"""
            
            elif status["configured"]:
                return """⚠️ *Google Workspace: Not Authorized*

Credentials file found, but not yet authorized.

Run in terminal:
`koda setup-google`

Or open the dashboard:
`http://localhost:8081` → Google tab"""
            
            else:
                return """❌ *Google Workspace: Not Configured*

For full Google integration (Gmail + Calendar + Meet):

1. Create a Google Cloud Project
2. Download credentials.json to ~/.koda/
3. Run: `koda setup-google`

_Or use /googlehelp for simple Calendar-only setup_"""
                
        except ImportError:
            return "❌ Google API libraries not installed.\nRun: pip install google-api-python-client google-auth-oauthlib"
        except Exception as e:
            logger.error(f"Error getting Google status: {e}")
            return f"❌ Error: {e}"
    
    def _google_workspace_setup_help(self) -> str:
        """Return Google Workspace setup instructions."""
        return """🔧 *Google Workspace Setup (Full)*

This method gives access to Gmail, Calendar (incl. shared), and Meet links.

*Step 1: Google Cloud Project*
1. Go to: console.cloud.google.com
2. Create a project named "Koda"
3. Go to "APIs & Services" → "Library"
4. Enable: Gmail API, Google Calendar API

*Step 2: OAuth Consent Screen*
1. Go to "APIs & Services" → "OAuth consent screen"
2. Choose "External"
3. Enter app name "Koda"
4. Add your email as test user

*Step 3: Credentials*
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Type: "Desktop app"
4. Download the JSON
5. Rename to `google_credentials.json`
6. Place in `~/.koda/google_credentials.json`

*Step 4: Authorize*
Run in terminal:
```
koda setup-google
```

Or open the dashboard and go to the Google tab.

📖 *Detailed guide:*
https://developers.google.com/calendar/api/quickstart/python

_For Calendar-only without OAuth, use /googlehelp_"""
    
    def _image_providers_status(self) -> str:
        """Show image generation provider status."""
        from koda.config.loader import load_config
        config = load_config()
        
        img_cfg = getattr(config.tools, 'image_generation', None)
        if not img_cfg:
            return """🎨 *Image Generation Status*

No providers configured yet.

*Quick setup:*
`/setimageprovider pollinations` - Free, no signup needed

Or add a paid provider:
`/addimagekey gemini YOUR_GOOGLE_KEY`
`/addimagekey stability sk-xxx...`"""
        
        lines = ["🎨 *Image Generation Providers*\n"]
        
        providers = [
            ("pollinations", img_cfg.pollinations, "🆓 Free"),
            ("gemini", img_cfg.gemini, "🧠 Google Imagen"),
            ("openrouter", img_cfg.openrouter, "🔑 Uses existing key"),
            ("stability_ai", img_cfg.stability_ai, "💎 Paid"),
            ("replicate", img_cfg.replicate, "💎 Paid"),
        ]
        
        for name, pconf, note in providers:
            if pconf.enabled:
                has_key = "✓" if pconf.api_key else "○"
                is_default = " (default)" if img_cfg.default_provider == name else ""
                lines.append(f"✅ {name}{is_default} [{has_key}] - {note}")
            else:
                lines.append(f"○ {name} - {note}")
        
        lines.append(f"\n_Default: {img_cfg.default_provider}_")
        lines.append("\n*Commands:*")
        lines.append("• `/setimageprovider <name>` - Set default")
        lines.append("• `/addimagekey <provider> <key>` - Add API key")
        return "\n".join(lines)
    
    def _add_image_key(self, args: str) -> str:
        """Add API key for an image provider."""
        from koda.config.loader import load_config, save_config
        from koda.config.schema import ImageProviderConfig
        
        parts = args.split(maxsplit=1)
        if len(parts) < 1:
            return "❌ Provider name required. Usage: `/addimagekey <provider> [api_key]`"
        
        provider = parts[0].lower()
        api_key = parts[1] if len(parts) > 1 else ""
        
        valid_providers = ["pollinations", "openrouter", "stability", "stability_ai", "replicate", "gemini"]
        if provider not in valid_providers:
            return f"❌ Invalid provider. Valid: {', '.join(valid_providers)}"
        
        # Normalize provider name
        if provider == "stability":
            provider = "stability_ai"
        
        # Pollinations doesn't need a key
        if provider == "pollinations":
            api_key = ""
        elif not api_key:
            if provider == "gemini":
                return "❌ API key required for Gemini.\n\nGet your key at: https://aistudio.google.com/app/apikey\nUsage: `/addimagekey gemini YOUR_API_KEY`"
            return f"❌ API key required for {provider}. Usage: `/addimagekey {provider} <key>`"
        
        config = load_config()
        
        # Ensure tools.image exists
        if not hasattr(config, 'tools') or config.tools is None:
            from koda.config.schema import ToolsConfig
            config.tools = ToolsConfig()
        if not hasattr(config.tools, 'image') or config.tools.image_generation is None:
            from koda.config.schema import ImageGenerationConfig
            config.tools.image_generation = ImageGenerationConfig()
        
        # Update provider config
        pconf = ImageProviderConfig(enabled=True, api_key=api_key, default_model="")
        
        if provider == "pollinations":
            config.tools.image_generation.pollinations = pconf
        elif provider == "openrouter":
            config.tools.image_generation.openrouter = pconf
        elif provider == "stability_ai":
            config.tools.image_generation.stability_ai = pconf
        elif provider == "replicate":
            config.tools.image_generation.replicate = pconf
        elif provider == "gemini":
            config.tools.image_generation.gemini = pconf
        
        # Set as default if no default set yet
        if not config.tools.image_generation.default_provider:
            config.tools.image_generation.default_provider = provider
        
        save_config(config)
        
        key_status = "(with API key)" if api_key else "(free, no key needed)"
        return f"✅ *{provider}* enabled {key_status}\n\nUse `/setimageprovider {provider}` to make it the default."
    
    def _set_image_provider(self, provider: str) -> str:
        """Set the default image provider."""
        from koda.config.loader import load_config, save_config
        
        valid_providers = ["pollinations", "openrouter", "stability_ai", "replicate", "gemini"]
        if provider not in valid_providers:
            return f"❌ Invalid provider. Valid: {', '.join(valid_providers)}"
        
        config = load_config()
        
        # Ensure tools.image exists
        if not hasattr(config, 'tools') or config.tools is None:
            from koda.config.schema import ToolsConfig
            config.tools = ToolsConfig()
        if not hasattr(config.tools, 'image') or config.tools.image_generation is None:
            from koda.config.schema import ImageGenerationConfig
            config.tools.image_generation = ImageGenerationConfig()
        
        # Enable the provider if not already
        if provider == "pollinations":
            if not config.tools.image_generation.pollinations.enabled:
                config.tools.image_generation.pollinations.enabled = True
        elif provider == "openrouter":
            if not config.tools.image_generation.openrouter.enabled:
                config.tools.image_generation.openrouter.enabled = True
        elif provider == "stability_ai":
            if not config.tools.image_generation.stability_ai.enabled:
                config.tools.image_generation.stability_ai.enabled = True
        elif provider == "replicate":
            if not config.tools.image_generation.replicate.enabled:
                config.tools.image_generation.replicate.enabled = True
        elif provider == "gemini":
            if not config.tools.image_generation.gemini.enabled:
                config.tools.image_generation.gemini.enabled = True
        
        config.tools.image_generation.default_provider = provider
        save_config(config)
        
        provider_info = {
            "pollinations": "🆓 Free, no signup needed",
            "gemini": "🧠 Google Imagen - get key at aistudio.google.com/app/apikey",
            "openrouter": "🔑 Uses your existing OpenRouter key",
            "stability_ai": "💎 Requires Stability AI API key",
            "replicate": "💎 Requires Replicate API key",
        }
        
        return f"✅ Default image provider set to: *{provider}*\n{provider_info.get(provider, '')}\n\nYou can now generate images! Try:\n\"Generate an image of a sunset\""
    
    # ============================================================================
    # Public Events Methods
    # ============================================================================
    
    async def _list_public_events(self, args: str) -> str:
        """List upcoming public events."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            days = 30
            category = None
            
            # Parse args
            if args:
                parts = args.split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        days = int(part)
                    elif part in ["sports", "music", "entertainment"]:
                        category = part
            
            return tool.execute(action="list", days=days, category=category or "all")
        except Exception as e:
            logger.error(f"Error listing events: {e}")
            return f"❌ Error loading events: {e}"
    
    async def _add_public_event(self, args: str) -> str:
        """Import public events from a source."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            parts = args.split(maxsplit=1)
            source = parts[0].lower()
            
            if source == "f1":
                return await tool.execute(action="import", source="f1")
            
            elif source == "football":
                team = parts[1] if len(parts) > 1 else ""
                if not team:
                    return "❌ Please specify a team name. Example: `/addevent football Feyenoord`"
                return await tool.execute(action="import", source="football", team=team)
            
            elif source == "ical":
                url = parts[1] if len(parts) > 1 else ""
                if not url:
                    return "❌ Please provide an iCal URL. Example: `/addevent ical https://...`"
                return await tool.execute(action="import", source="ical", ical_url=url)
            
            else:
                return f"❌ Unknown source: {source}. Try: f1, football, ical"
        except Exception as e:
            logger.error(f"Error adding event: {e}")
            return f"❌ Error: {e}"
    
    def _list_teams(self) -> str:
        """List subscribed sports teams."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            return tool.execute(action="teams")
        except Exception as e:
            logger.error(f"Error listing teams: {e}")
            return f"❌ Error: {e}"
    
    async def _add_team(self, team_name: str) -> str:
        """Subscribe to a sports team."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            return await tool.execute(action="add_team", team=team_name)
        except Exception as e:
            logger.error(f"Error adding team: {e}")
            return f"❌ Error: {e}"
    
    def _remove_team(self, team_name: str) -> str:
        """Unsubscribe from a sports team."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            return tool.execute(action="remove_team", team=team_name)
        except Exception as e:
            logger.error(f"Error removing team: {e}")
            return f"❌ Error: {e}"
    
    async def _search_public_events(self, keyword: str) -> str:
        """Search for public events."""
        try:
            from pathlib import Path
            from koda.core.tools.public_events import PublicEventsTool
            
            workspace = Path.home() / ".koda" / "workspace"
            tool = PublicEventsTool(workspace)
            
            return tool.execute(action="search", keyword=keyword)
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            return f"❌ Error: {e}"
    
    # ============================================================================
    # User Profile Methods
    # ============================================================================
    
    def _show_user_profile(self) -> str:
        """Show the user's profile."""
        try:
            from koda.services.user_profiling import UserProfilingService
            
            service = UserProfilingService()
            # Initialize without async to load existing data
            service._init_storage()
            
            summary = service.get_profile_summary()
            suggestions = service.get_suggestions()
            
            result = summary
            if suggestions:
                result += "\n\n💡 *Suggestions based on your profile:*\n"
                for s in suggestions[:3]:
                    result += f"• {s}\n"
            
            return result
        except Exception as e:
            logger.error(f"Error showing profile: {e}")
            return f"❌ Error loading profile: {e}"
    
    async def _trigger_profiling_question(self) -> str:
        """Trigger a profiling question."""
        try:
            from koda.services.user_profiling import UserProfilingService
            
            service = UserProfilingService()
            await service.start()
            
            question = await service.ask_question()
            await service.stop()
            
            if question:
                return "📝 I've sent you a question to help me learn more about you!"
            else:
                return "ℹ️ Not time for a new question yet. I ask 1-2 questions per week.\n\nUse /profile to see what I already know about you."
        except Exception as e:
            logger.error(f"Error triggering profiling question: {e}")
            return f"❌ Error: {e}"
    
    async def _auto_reload_config(self) -> None:
        """Automatically reload configuration after changes."""
        try:
            # Reload config from file and extract WhatsApp config
            from koda.config.loader import load_config
            full_config = load_config()
            self.config = full_config.channels.whatsapp
            self._full_config = full_config  # Keep reference to full config for account operations
            logger.info("Configuration reloaded after account change")
        except Exception as e:
            logger.error(f"Error auto-reloading config: {e}")
    
    def _start_email_setup(self, phone: str) -> str:
        """Start step-by-step email setup."""
        self._setup_sessions[phone] = {
            "type": "email",
            "step": 1,
            "data": {}
        }
        return """📧 *Email Account Setup*

Step 1/5: What type of email?
1️⃣ Exchange/Office 365
2️⃣ IMAP (Gmail, etc.)

Send the number (1 or 2) or /cancel to stop."""
    
    def _start_calendar_setup(self, phone: str) -> str:
        """Start step-by-step calendar setup."""
        self._setup_sessions[phone] = {
            "type": "calendar",
            "step": 1,
            "data": {}
        }
        return """📅 *Calendar Account Setup*

Step 1/4: What type of calendar?
1️⃣ Exchange/Office 365
2️⃣ Google Calendar
3️⃣ CalDAV (iCloud, Nextcloud, etc.)

Send the number (1, 2 or 3) or /cancel to stop."""
    
    def _start_json_setup(self, phone: str, account_type: str) -> str:
        """Start JSON-based setup."""
        self._setup_sessions[phone] = {
            "type": f"{account_type}_json",
            "step": 1,
            "data": {}
        }
        
        if account_type == "email":
            return """📧 *Email Account Setup (JSON)*

Send a JSON object with the following fields:

*Exchange:*
```
{
  "type": "exchange",
  "name": "Work",
  "email": "you@company.com",
  "password": "password",
  "server": "outlook.office365.com"
}
```

*IMAP:*
```
{
  "type": "imap",
  "name": "Gmail",
  "host": "imap.gmail.com",
  "port": 993,
  "username": "you@gmail.com",
  "password": "app-password"
}
```

Or /cancel to stop."""
        else:
            return """📅 *Calendar Account Setup (JSON)*

Send a JSON object with the following fields:

*Exchange:*
```
{
  "type": "exchange",
  "name": "Work",
  "email": "you@company.com",
  "password": "password",
  "server": "outlook.office365.com"
}
```

*CalDAV:*
```
{
  "type": "caldav",
  "name": "iCloud",
  "url": "https://caldav.icloud.com",
  "username": "you@icloud.com",
  "password": "app-password"
}
```

Or /cancel to stop."""
    
    async def _handle_setup_response(self, phone: str, content: str, chat_id: str) -> str | None:
        """Handle a response in an active setup session."""
        if phone not in self._setup_sessions:
            return None
        
        session = self._setup_sessions[phone]
        setup_type = session["type"]
        step = session["step"]
        data = session["data"]
        
        # Handle JSON setup
        if setup_type.endswith("_json"):
            try:
                json_data = json.loads(content)
                account_type = setup_type.replace("_json", "")
                result = self._save_account_from_json(account_type, json_data)
                del self._setup_sessions[phone]
                return result
            except json.JSONDecodeError:
                return "❌ Invalid JSON. Try again or /cancel."
        
        # Handle step-by-step email setup
        if setup_type == "email":
            return await self._handle_email_setup_step(phone, content, step, data)
        
        # Handle step-by-step calendar setup
        if setup_type == "calendar":
            return await self._handle_calendar_setup_step(phone, content, step, data)
        
        # Handle step-by-step LinkedIn setup
        if setup_type == "linkedin":
            return await self._handle_linkedin_setup_step(phone, content, step, data)
        
        return None
    
    async def _handle_email_setup_step(self, phone: str, content: str, step: int, data: dict) -> str:
        """Handle email setup steps with connection testing."""
        session = self._setup_sessions[phone]
        
        if step == 1:  # Type selection
            if content == "1":
                data["type"] = "exchange"
                session["step"] = 2
                return "Step 1/7: What is your email address?"
            elif content == "2":
                data["type"] = "imap"
                session["step"] = 2
                return "Step 1/5: What is the IMAP server? (e.g. imap.gmail.com)"
            else:
                return "❌ Choose 1 or 2, or /cancel to stop."
        
        # EXCHANGE EMAIL FLOW
        elif step == 2 and data["type"] == "exchange":
            data["email"] = content
            session["step"] = 3
            return f"Step 2/7: What is your username?\n(Often the same as email, or DOMAIN\\\\username)\nSend 'same' to use {content}."
        
        elif step == 3 and data["type"] == "exchange":
            data["username"] = data["email"] if content.lower() == "same" else content
            session["step"] = 4
            return "Step 3/7: What is your password? (or app password)"
        
        elif step == 4 and data["type"] == "exchange":
            data["password"] = content
            session["step"] = 5
            return """Step 4/7: Do you want to use autodiscover?

1️⃣ Yes, use autodiscover (recommended for O365)
2️⃣ No, I'll enter the server manually

Send 1 or 2:"""
        
        elif step == 5 and data["type"] == "exchange":
            if content == "1":
                data["use_autodiscover"] = True
                data["server"] = ""
                session["step"] = 7  # Skip server input
                return "Step 5/7: Give this account a name (e.g. 'Work'):"
            elif content == "2":
                data["use_autodiscover"] = False
                session["step"] = 6
                return "Step 5/7: What is the Exchange server?\n(e.g. outlook.office365.com or mail.company.com)"
            else:
                return "❌ Choose 1 or 2, or /cancel to stop."
        
        elif step == 6 and data["type"] == "exchange":
            data["server"] = content
            session["step"] = 7
            return "Step 6/7: Give this account a name (e.g. 'Work'):"
        
        elif step == 7 and data["type"] == "exchange":
            data["name"] = content
            session["step"] = 8
            return await self._test_exchange_connection(phone, data, "email")
        
        elif step == 8 and data["type"] == "exchange":
            # Handle retry options after failed test
            return await self._handle_exchange_retry(phone, content, data, "email")
        
        elif step == 9 and data["type"] == "exchange":
            # Ask about using same account for calendar
            if content.lower() in ["ja", "yes", "j", "y", "1"]:
                # Copy email account to calendar
                result = await self._save_exchange_for_both(data, "email")
                del self._setup_sessions[phone]
                return result
            else:
                result = await self._save_account_from_data("email", data)
                del self._setup_sessions[phone]
                return result
        
        # IMAP EMAIL FLOW
        elif step == 2 and data["type"] == "imap":
            data["host"] = content
            session["step"] = 3
            return "Step 2/5: What is your username/email?"
        
        elif step == 3 and data["type"] == "imap":
            data["username"] = content
            session["step"] = 4
            return "Step 3/5: What is your password? (or app password)"
        
        elif step == 4 and data["type"] == "imap":
            data["password"] = content
            session["step"] = 5
            return "Step 4/5: Give this account a name (e.g. 'Gmail'):"
        
        elif step == 5 and data["type"] == "imap":
            data["name"] = content
            data["port"] = 993
            data["use_ssl"] = True
            result = await self._save_account_from_data("email", data)
            del self._setup_sessions[phone]
            return result
        
        return None
    
    async def _handle_calendar_setup_step(self, phone: str, content: str, step: int, data: dict) -> str:
        """Handle calendar setup steps with connection testing."""
        session = self._setup_sessions[phone]
        
        if step == 1:  # Type selection
            if content == "1":
                data["type"] = "exchange"
                session["step"] = 2
                return "Step 1/7: What is your email address?"
            elif content == "2":
                data["type"] = "google"
                del self._setup_sessions[phone]
                return """⚠️ *Google Calendar Setup*

Google Calendar requires OAuth authentication via browser.

Run this command in your terminal:
`koda setup --section calendar`

This will open a browser for Google login.

_Setup via WhatsApp not possible for Google._"""
            elif content == "3":
                data["type"] = "caldav"
                session["step"] = 2
                return "Step 1/5: What is the CalDAV URL?\n(e.g. https://caldav.icloud.com)"
            else:
                return "❌ Choose 1, 2 or 3, or /cancel to stop."
        
        # EXCHANGE CALENDAR FLOW
        elif step == 2 and data["type"] == "exchange":
            data["email"] = content
            session["step"] = 3
            return f"Step 2/7: What is your username?\n(Often the same as email, or DOMAIN\\\\username)\nSend 'same' to use {content}."
        
        elif step == 3 and data["type"] == "exchange":
            data["username"] = data["email"] if content.lower() == "same" else content
            session["step"] = 4
            return "Step 3/7: What is your password? (or app password)"
        
        elif step == 4 and data["type"] == "exchange":
            data["password"] = content
            session["step"] = 5
            return """Step 4/7: Do you want to use autodiscover?

1️⃣ Yes, use autodiscover (recommended for O365)
2️⃣ No, I'll enter the server manually

Send 1 or 2:"""
        
        elif step == 5 and data["type"] == "exchange":
            if content == "1":
                data["use_autodiscover"] = True
                data["server"] = ""
                session["step"] = 7
                return "Step 5/7: Give this account a name (e.g. 'Work'):"
            elif content == "2":
                data["use_autodiscover"] = False
                session["step"] = 6
                return "Step 5/7: What is the Exchange server?\n(e.g. outlook.office365.com or mail.company.com)"
            else:
                return "❌ Choose 1 or 2, or /cancel to stop."
        
        elif step == 6 and data["type"] == "exchange":
            data["server"] = content
            session["step"] = 7
            return "Step 6/7: Give this account a name (e.g. 'Work'):"
        
        elif step == 7 and data["type"] == "exchange":
            data["name"] = content
            session["step"] = 8
            return await self._test_exchange_connection(phone, data, "calendar")
        
        elif step == 8 and data["type"] == "exchange":
            return await self._handle_exchange_retry(phone, content, data, "calendar")
        
        elif step == 9 and data["type"] == "exchange":
            # Ask about using same account for email
            if content.lower() in ["ja", "yes", "j", "y", "1"]:
                result = await self._save_exchange_for_both(data, "calendar")
                del self._setup_sessions[phone]
                return result
            else:
                result = await self._save_account_from_data("calendar", data)
                del self._setup_sessions[phone]
                return result
        
        # CALDAV FLOW
        elif step == 2 and data["type"] == "caldav":
            data["url"] = content
            session["step"] = 3
            return "Step 2/5: What is your username?"
        
        elif step == 3 and data["type"] == "caldav":
            data["username"] = content
            session["step"] = 4
            return "Step 3/5: What is your password? (or app password)"
        
        elif step == 4 and data["type"] == "caldav":
            data["password"] = content
            session["step"] = 5
            return "Step 4/5: Give this account a name:"
        
        elif step == 5 and data["type"] == "caldav":
            data["name"] = content
            result = await self._save_account_from_data("calendar", data)
            del self._setup_sessions[phone]
            return result
        
        return None
    
    async def _handle_linkedin_setup_step(self, phone: str, content: str, step: int, data: dict) -> str:
        """Handle LinkedIn setup steps."""
        session = self._setup_sessions[phone]
        
        if step == 1:  # Email
            data["email"] = content
            session["step"] = 2
            return "Step 2/2: Enter your LinkedIn password:\n\n⚠️ Note: If you have 2FA enabled, you may need to use an app password."
        
        elif step == 2:  # Password
            data["password"] = content
            
            # Save LinkedIn config
            config = load_config()
            config.integrations.linkedin.enabled = True
            config.integrations.linkedin.email = data["email"]
            config.integrations.linkedin.password = data["password"]
            save_config(config)
            
            del self._setup_sessions[phone]
            
            # Trigger config reload
            await self._auto_reload_config()
            
            return f"""✅ *LinkedIn configured!*

Email: {data['email']}

The assistant can now:
• Check and reply to LinkedIn messages
• Manage connection requests
• View and interact with posts
• Search for people

⚠️ *Important:* LinkedIn may require you to verify new logins. If you see issues, check your LinkedIn email for verification requests."""
        
        return None
    
    async def _test_exchange_connection(self, phone: str, data: dict, account_type: str) -> str:
        """Test Exchange connection and return result."""
        import traceback
        session = self._setup_sessions[phone]
        
        logger.info(f"Testing Exchange connection for {data.get('email')}...")
        logger.info(f"Settings: username={data.get('username')}, server={data.get('server')}, autodiscover={data.get('use_autodiscover')}")
        
        try:
            from exchangelib import Credentials, Account, Configuration, DELEGATE, Build, Version
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
            
            # Use NoVerifyHTTPAdapter to avoid SSL issues
            BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
            
            logger.info("Creating credentials...")
            username = data.get("username", data.get("email"))
            password = data.get("password")
            
            credentials = Credentials(username=username, password=password)
            
            if data.get("use_autodiscover", False) or not data.get("server"):
                # Use autodiscover
                logger.info("Using autodiscover...")
                account = Account(
                    primary_smtp_address=data["email"],
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE
                )
            else:
                # Manual server - specify version to avoid version detection issues
                logger.info(f"Connecting to server: {data['server']}")
                
                # Try with explicit version to skip problematic version detection
                version = Version(build=Build(15, 1, 0, 0))  # Exchange 2016
                
                config = Configuration(
                    server=data["server"],
                    credentials=credentials,
                    version=version
                )
                account = Account(
                    primary_smtp_address=data["email"],
                    credentials=credentials,
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE
                )
            
            logger.info("Account created, testing access...")
            
            # Test by accessing inbox/calendar - use simpler test
            if account_type == "email":
                logger.info("Testing inbox access...")
                # Just check if we can access root - simpler test
                root = account.root
                logger.info(f"Root folder accessible: {root.name if root else 'yes'}")
            else:
                logger.info("Testing calendar access...")
                # Just check if calendar folder exists
                cal = account.calendar
                logger.info(f"Calendar accessible: {cal.name if cal else 'yes'}")
            
            logger.info("Exchange connection successful!")
            session["step"] = 9
            
            other_type = "calendar" if account_type == "email" else "email"
            return f"""✅ *Connection successful!*

Account: {data['name']}
Email: {data['email']}
Server: {data.get('server') or 'autodiscover'}

Do you want to use this account for *{other_type}* as well?
(Yes/No)"""
        
        except ImportError as e:
            logger.error(f"exchangelib import error: {e}")
            logger.error(traceback.format_exc())
            session["step"] = 8
            session["last_error"] = str(e)
            return self._format_exchange_error(f"exchangelib not found: {e}\nRun: pip install exchangelib", data)
        
        except Exception as e:
            # Catch all exceptions with full traceback
            error_type = type(e).__name__
            error_msg = str(e) or "(no details)"
            full_traceback = traceback.format_exc()
            
            logger.error(f"Exchange error: {error_type}: {error_msg}")
            logger.error(f"Full traceback:\n{full_traceback}")
            
            session["step"] = 8
            session["last_error"] = f"{error_type}: {error_msg}"
            
            # Provide more specific error messages
            if "Unauthorized" in error_type or "401" in str(e):
                return self._format_exchange_error("Authentication failed. Check email/username and password.", data)
            elif "Transport" in error_type or "Connection" in error_type:
                return self._format_exchange_error(f"Cannot connect to server: {error_msg}", data)
            elif "Autodiscover" in str(e) or "autodiscover" in str(e).lower():
                return self._format_exchange_error(f"Autodiscover failed: {error_msg}\nTry entering a server manually.", data)
            else:
                return self._format_exchange_error(f"{error_type}: {error_msg}", data)
    
    def _format_exchange_error(self, error: str, data: dict) -> str:
        """Format Exchange error message with retry options."""
        return f"""❌ *Connection failed*

Error: {error}

*Current settings:*
• Email: {data.get('email', '-')}
• Username: {data.get('username', '-')}
• Server: {data.get('server') or 'autodiscover'}

*What do you want to do?*
1️⃣ Change email
2️⃣ Change username
3️⃣ Change password
4️⃣ Change server
5️⃣ Toggle autodiscover
6️⃣ Try again
7️⃣ Stop (/cancel)

Send a number:"""
    
    async def _handle_exchange_retry(self, phone: str, content: str, data: dict, account_type: str) -> str:
        """Handle retry options after failed Exchange connection."""
        session = self._setup_sessions[phone]
        
        if content == "1":
            session["retry_field"] = "email"
            return "Enter the new email address:"
        elif content == "2":
            session["retry_field"] = "username"
            return "Enter the new username:"
        elif content == "3":
            session["retry_field"] = "password"
            return "Enter the new password:"
        elif content == "4":
            session["retry_field"] = "server"
            return "Enter the new server (e.g. outlook.office365.com):"
        elif content == "5":
            data["use_autodiscover"] = not data.get("use_autodiscover", False)
            status = "ON" if data["use_autodiscover"] else "OFF"
            return f"Autodiscover is now *{status}*. Send 6 to try again."
        elif content == "6":
            return await self._test_exchange_connection(phone, data, account_type)
        elif content == "7" or content.lower() == "/cancel":
            del self._setup_sessions[phone]
            return "✅ Setup cancelled."
        elif "retry_field" in session:
            # User is providing new value for a field
            field = session.pop("retry_field")
            data[field] = content
            return await self._test_exchange_connection(phone, data, account_type)
        else:
            return "❌ Choose a number (1-7):"
    
    async def _save_exchange_for_both(self, data: dict, primary_type: str) -> str:
        """Save Exchange account using shared AccountManager."""
        from koda.config.accounts import AccountManager
        
        try:
            account_data = {
                "name": data.get("name", "Exchange"),
                "type": "exchange",
                "email": data.get("email"),
                "username": data.get("username"),
                "password": data.get("password"),
                "server": data.get("server", ""),
                "use_autodiscover": data.get("use_autodiscover", False)
            }
            
            manager = AccountManager()
            success, message = manager.add_account(account_data)
            
            if success:
                # Auto-reload config
                await self._auto_reload_config()
                
                return f"""✅ *Exchange account added!*

Account *{data['name']}* is configured for:
• 📧 Email
• 📅 Calendar
• 👥 Contacts

The account is now active."""
            else:
                return f"❌ {message}"
        
        except Exception as e:
            logger.error(f"Error saving Exchange account: {e}")
            return f"❌ Error saving: {e}"
    
    async def _save_account_from_data(self, account_type: str, data: dict) -> str:
        """Save account using shared AccountManager."""
        from koda.config.accounts import AccountManager
        
        try:
            account_data = dict(data)  # Copy to avoid mutation
            
            manager = AccountManager()
            success, message = manager.add_account(account_data)
            
            if success:
                await self._auto_reload_config()
                name = data.get("name", "Account")
                acc_type = data.get("type", "unknown")
                return f"✅ Account *{name}* ({acc_type}) added!\n{message}"
            else:
                return f"❌ {message}"
        
        except Exception as e:
            logger.error(f"Error saving account: {e}")
            return f"❌ Error saving: {e}"
    
    def _save_account_from_json(self, account_type: str, data: dict) -> str:
        """Save account from JSON data using shared AccountManager."""
        from koda.config.accounts import AccountManager
        
        try:
            manager = AccountManager()
            success, message = manager.add_account(data)
            
            if success:
                name = data.get("name", "Account")
                return f"✅ Account *{name}* added!\n{message}"
            else:
                return f"❌ {message}"
        
        except Exception as e:
            logger.error(f"Error saving account: {e}")
            return f"❌ Error saving: {e}"
    
    def _remove_account(self, config, account_type: str, name: str) -> str:
        """Remove an account by name using shared AccountManager."""
        from koda.config.accounts import AccountManager
        
        try:
            manager = AccountManager()
            success, message = manager.remove_account(name)
            
            if success:
                return f"✅ Account *{name}* removed."
            else:
                return f"❌ {message}"
        
        except Exception as e:
            logger.error(f"Error removing account: {e}")
            return f"❌ Error removing: {e}"
    
    async def _handle_bridge_message(self, raw: str) -> None:
        """Handle a message from the bridge."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from bridge: {raw[:100]}")
            return
        
        msg_type = data.get("type")
        
        if msg_type == "message":
            # Incoming message from WhatsApp
            sender = data.get("sender", "")
            content = data.get("content", "")
            
            # sender is typically: <phone>@s.whatsapp.net
            # Extract just the phone number as chat_id
            phone = sender.split("@")[0] if "@" in sender else sender
            
            # Log incoming message
            logger.info(f"📥 WhatsApp message from +{phone}: {content[:100]}{'...' if len(content) > 100 else ''}")
            
            # Check for active setup session first
            if phone in self._setup_sessions and self.is_allowed(phone):
                response = await self._handle_setup_response(phone, content, sender)
                if response:
                    logger.info(f"📤 Sending setup response to +{phone}")
                    await self.send(OutboundMessage(
                        channel="whatsapp",
                        chat_id=sender,
                        content=response
                    ))
                    return  # Don't process as regular message
            
            # Check for commands (only from allowed users)
            if content.startswith("/") and self.is_allowed(phone):
                parts = content.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                response = await self._handle_command(command, args, sender, phone)
                if response:
                    logger.info(f"📤 Sending command response to +{phone}")
                    await self.send(OutboundMessage(
                        channel="whatsapp",
                        chat_id=sender,
                        content=response
                    ))
                    return  # Don't process command as regular message
            
            # Handle voice transcription if it's a voice message
            if content == "[Voice Message]":
                logger.info(f"🎤 Voice message received from +{phone}")
                content = "[Voice Message: Transcription not available for WhatsApp yet]"
            
            # Get contact rule for custom handling
            contact_rule = self._get_contact_rule(phone)
            contact_name = contact_rule.name if contact_rule else None
            
            # Check for escalation (skip for self-messages)
            if self._should_escalate(content, contact_rule, phone):
                await self._notify_owner(phone, contact_name or phone, content)
            
            # Build metadata with contact info and instructions
            metadata = {
                "message_id": data.get("id"),
                "timestamp": data.get("timestamp"),
                "is_group": data.get("isGroup", False),
                "contact_name": contact_name,
                "custom_instructions": self._get_instructions_for_contact(phone),
                "is_bot_mode": self.config.bot_mode,
            }
            
            # If this is a new contact in bot mode, we might want to send a greeting
            # (This would be handled by the agent based on conversation history)
            
            logger.debug(f"📤 Forwarding message to agent for processing...")
            await self._handle_message(
                sender_id=phone,
                chat_id=sender,  # Use full JID for replies
                content=content,
                metadata=metadata
            )
            logger.debug(f"✅ Message forwarded to agent")
        
        elif msg_type == "status":
            # Connection status update
            status = data.get("status")
            logger.info(f"WhatsApp status: {status}")
            
            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False
        
        elif msg_type == "qr":
            # QR code for authentication - display it in console
            qr_data = data.get("qr", "")
            logger.info("\n" + "="*50)
            logger.info("📱 WHATSAPP QR CODE - Scan with your phone")
            logger.info("="*50)
            if qr_data:
                try:
                    import qrcode
                    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
                    qr.add_data(qr_data)
                    qr.make(fit=True)
                    # Print QR code to terminal
                    qr.print_ascii(invert=True)
                except ImportError:
                    logger.info(f"QR Data: {qr_data}")
                    logger.info("Install 'qrcode' package to display QR in terminal: pip install qrcode")
            logger.info("="*50 + "\n")
        
        elif msg_type == "file":
            # Incoming file/media message from WhatsApp
            sender = data.get("sender", "")
            content = data.get("content", "")
            media_type = data.get("mediaType", "file")
            media_filename = data.get("mediaFilename", "unknown")
            media_mimetype = data.get("mediaMimetype", "")
            media_data = data.get("mediaData", "")  # base64 encoded
            
            # sender is typically: <phone>@s.whatsapp.net
            phone = sender.split("@")[0] if "@" in sender else sender
            
            # Save the file
            file_path = None
            if media_data:
                try:
                    import base64
                    from pathlib import Path
                    
                    # Create downloads directory
                    downloads_dir = Path.home() / ".koda" / "workspace" / "downloads"
                    downloads_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Decode and save
                    file_bytes = base64.b64decode(media_data)
                    file_path = downloads_dir / media_filename
                    
                    # Handle duplicate filenames
                    counter = 1
                    original_path = file_path
                    while file_path.exists():
                        stem = original_path.stem
                        suffix = original_path.suffix
                        file_path = downloads_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    file_path.write_bytes(file_bytes)
                    logger.info(f"💾 Saved received file: {file_path} ({len(file_bytes)} bytes)")
                except Exception as e:
                    logger.error(f"Failed to save received file: {e}")
            
            logger.info(f"📥 WhatsApp {media_type} from +{phone}: {media_filename}")
            
            # Check for commands (only from allowed users)
            if content.startswith("/") and self.is_allowed(phone):
                parts = content.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                response = await self._handle_command(command, args, sender, phone)
                if response:
                    await self.send(OutboundMessage(
                        channel="whatsapp",
                        chat_id=sender,
                        content=response
                    ))
                    return
            
            # Build metadata with file info
            contact_rule = self._get_contact_rule(phone)
            contact_name = contact_rule.name if contact_rule else None
            
            metadata = {
                "message_id": data.get("id"),
                "timestamp": data.get("timestamp"),
                "is_group": data.get("isGroup", False),
                "contact_name": contact_name,
                "custom_instructions": self._get_instructions_for_contact(phone),
                "is_bot_mode": self.config.bot_mode,
                "has_media": True,
                "media_type": media_type,
                "media_filename": media_filename,
                "media_mimetype": media_mimetype,
                "media_path": str(file_path) if file_path else None,
            }
            
            # Create content description with file info
            file_description = f"[{media_type.upper()}: {media_filename}"
            if content and content != f"[{media_type.capitalize()}]":
                file_description += f" - Caption: {content}"
            file_description += "]"
            
            await self._handle_message(
                sender_id=phone,
                chat_id=sender,
                content=file_description,
                metadata=metadata
            )
        
        elif msg_type == "error":
            logger.error(f"WhatsApp bridge error: {data.get('error')}")
