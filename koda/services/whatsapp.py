"""WhatsApp channel implementation using Node.js bridge.

Supports:
- Bot mode: Respond to all incoming messages
- Per-contact rules: Custom instructions per phone number
- Owner escalation: Notify owner for appointments/urgent requests
- Message viewing from all numbers
- WhatsApp commands (/help, /status, /name, etc.)
"""

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
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WhatsApp."""
        if not self._ws or not self._connected:
            logger.warning("⚠️ WhatsApp bridge not connected - cannot send message")
            return
        
        try:
            payload = {
                "type": "send",
                "to": msg.chat_id,
                "text": msg.content
            }
            logger.info(f"📤 Sending WhatsApp message to {msg.chat_id[:20]}... ({len(msg.content)} chars)")
            await self._ws.send(json.dumps(payload))
            logger.info(f"✅ WhatsApp message sent successfully")
        except Exception as e:
            logger.error(f"❌ Error sending WhatsApp message: {e}")
    
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
    
    def _should_escalate(self, content: str, contact_rule: WhatsAppContactRule | None) -> bool:
        """Check if a message should be escalated to the owner."""
        if not self.config.escalate_to_owner:
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
            f"📢 *Bericht dat je aandacht nodig heeft*\n\n"
            f"Van: {sender_name or sender_phone}\n"
            f"Nummer: {sender_phone}\n\n"
            f"Bericht:\n{message}\n\n"
            f"_Reageer direct op dit nummer als actie nodig is._"
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
        
        Commands:
        - /help - Show available commands
        - /status - Show current configuration
        - /name <name> - Set your name
        - /assistant <name> - Set assistant name
        - /language <code> - Set language (nl, en, de, fr, es)
        - /style <style> - Set personality (professional, friendly, formal)
        """
        config = load_config()
        
        if command == "/help":
            return """📋 *Beschikbare commando's:*

*Informatie:*
/help - Toon deze hulp
/status - Toon huidige instellingen

*Instellingen:*
/name <naam> - Stel je naam in
/assistant <naam> - Stel assistant naam in
/language <code> - Stel taal in (nl, en, de, fr, es)
/style <stijl> - Stel stijl in (professional, friendly, formal)

*Voorbeeld:*
`/name Ronald`
`/language nl`"""

        elif command == "/status":
            assistant = config.assistant
            wa = config.channels.whatsapp
            mode = "Bot Mode (iedereen)" if wa.bot_mode else "Restricted Mode"
            allowed = ", ".join(wa.allow_from) if wa.allow_from else "niemand"
            
            return f"""⚙️ *Huidige instellingen:*

*Assistant:*
• Naam: {assistant.name}
• Jouw naam: {assistant.user_name or '(niet ingesteld)'}
• Taal: {assistant.language}
• Stijl: {assistant.personality}

*WhatsApp:*
• Modus: {mode}
• Toegestaan: {allowed}
• Owner: {wa.owner_name or wa.owner_phone or '(niet ingesteld)'}

*Model:* {config.agents.defaults.model}"""

        elif command == "/name":
            if not args:
                return "❌ Gebruik: `/name <jouw naam>`\nVoorbeeld: `/name Ronald`"
            config.assistant.user_name = args
            save_config(config)
            return f"✅ Je naam is ingesteld op: *{args}*"
        
        elif command == "/assistant":
            if not args:
                return "❌ Gebruik: `/assistant <naam>`\nVoorbeeld: `/assistant Joyce`"
            config.assistant.name = args
            save_config(config)
            return f"✅ Assistant naam is ingesteld op: *{args}*"
        
        elif command == "/language":
            valid_langs = ["nl", "en", "de", "fr", "es"]
            if not args or args.lower() not in valid_langs:
                return f"❌ Gebruik: `/language <code>`\nGeldige codes: {', '.join(valid_langs)}"
            config.assistant.language = args.lower()
            save_config(config)
            lang_names = {"nl": "Nederlands", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español"}
            return f"✅ Taal ingesteld op: *{lang_names.get(args.lower(), args)}*"
        
        elif command == "/style":
            valid_styles = ["professional", "friendly", "formal"]
            if not args or args.lower() not in valid_styles:
                return f"❌ Gebruik: `/style <stijl>`\nGeldige stijlen: {', '.join(valid_styles)}"
            config.assistant.personality = args.lower()
            save_config(config)
            return f"✅ Stijl ingesteld op: *{args.lower()}*"
        
        return None  # Not a recognized command
    
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
            
            # Check for escalation
            if self._should_escalate(content, contact_rule):
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
        
        elif msg_type == "error":
            logger.error(f"WhatsApp bridge error: {data.get('error')}")
