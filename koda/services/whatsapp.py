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
        """
        config = load_config()
        
        if command == "/help":
            return """📋 *Beschikbare commando's:*

*Informatie:*
/help - Toon deze hulp
/status - Toon huidige instellingen
/accounts - Toon mail/agenda accounts

*Basis instellingen:*
/name <naam> - Stel je naam in
/assistant <naam> - Stel assistant naam in
/language <code> - Stel taal in (nl, en, de, fr, es)
/style <stijl> - Stel stijl in (professional, friendly, formal)

*Accounts toevoegen:*
/addmail - Voeg email account toe (stap voor stap)
/addmail json - Voeg email toe via JSON
/addcalendar - Voeg agenda account toe (stap voor stap)
/addcalendar json - Voeg agenda toe via JSON

*Accounts verwijderen:*
/removemail <naam> - Verwijder email account
/removecalendar <naam> - Verwijder agenda account

*Setup annuleren:*
/cancel - Annuleer lopende setup"""

        elif command == "/status":
            assistant = config.assistant
            wa = config.channels.whatsapp
            mode = "Bot Mode (iedereen)" if wa.bot_mode else "Restricted Mode"
            allowed = ", ".join(wa.allow_from) if wa.allow_from else "niemand"
            
            # Count accounts
            email_count = len(config.integrations.email_accounts) if hasattr(config.integrations, 'email_accounts') else 0
            cal_count = len(config.integrations.calendar_accounts) if hasattr(config.integrations, 'calendar_accounts') else 0
            
            return f"""⚙️ *Huidige instellingen:*

*Assistant:*
• Naam: {assistant.name}
• Jouw naam: {assistant.user_name or '(niet ingesteld)'}
• Taal: {assistant.language}
• Stijl: {assistant.personality}

*WhatsApp:*
• Modus: {mode}
• Toegestaan: {allowed}

*Accounts:*
• Email accounts: {email_count}
• Agenda accounts: {cal_count}

*Model:* {config.agents.defaults.model}

_Gebruik /accounts voor details_"""

        elif command == "/accounts":
            return self._format_accounts(config)
        
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
                return "❌ Gebruik: `/removemail <naam>`\nGebruik /accounts om namen te zien."
            return self._remove_account(config, "email", args)
        
        elif command == "/removecalendar":
            if not args:
                return "❌ Gebruik: `/removecalendar <naam>`\nGebruik /accounts om namen te zien."
            return self._remove_account(config, "calendar", args)
        
        elif command == "/cancel":
            if phone in self._setup_sessions:
                del self._setup_sessions[phone]
                return "✅ Setup geannuleerd."
            return "ℹ️ Geen actieve setup om te annuleren."
        
        return None  # Not a recognized command
    
    def _format_accounts(self, config) -> str:
        """Format configured accounts for display."""
        lines = ["📧 *Geconfigureerde Accounts:*\n"]
        
        # Email accounts
        email_accounts = getattr(config.integrations, 'email_accounts', []) or []
        if email_accounts:
            lines.append("*Email:*")
            for acc in email_accounts:
                name = acc.get('name', 'unnamed')
                acc_type = acc.get('type', 'unknown')
                email = acc.get('email', acc.get('username', ''))
                lines.append(f"• {name} ({acc_type}): {email}")
        else:
            lines.append("*Email:* Geen accounts geconfigureerd")
        
        lines.append("")
        
        # Calendar accounts
        cal_accounts = getattr(config.integrations, 'calendar_accounts', []) or []
        if cal_accounts:
            lines.append("*Agenda:*")
            for acc in cal_accounts:
                name = acc.get('name', 'unnamed')
                acc_type = acc.get('type', 'unknown')
                lines.append(f"• {name} ({acc_type})")
        else:
            # Check legacy config
            legacy = []
            if config.integrations.exchange.enabled:
                legacy.append(f"• Exchange: {config.integrations.exchange.email}")
            if config.integrations.google.enabled:
                legacy.append("• Google Calendar")
            if config.integrations.caldav.enabled:
                legacy.append(f"• CalDAV: {config.integrations.caldav.url}")
            
            if legacy:
                lines.append("*Agenda:*")
                lines.extend(legacy)
            else:
                lines.append("*Agenda:* Geen accounts geconfigureerd")
        
        lines.append("\n_Gebruik /addmail of /addcalendar om toe te voegen_")
        return "\n".join(lines)
    
    def _start_email_setup(self, phone: str) -> str:
        """Start step-by-step email setup."""
        self._setup_sessions[phone] = {
            "type": "email",
            "step": 1,
            "data": {}
        }
        return """📧 *Email Account Setup*

Stap 1/5: Welk type email?
1️⃣ Exchange/Office 365
2️⃣ IMAP (Gmail, etc.)

Stuur het nummer (1 of 2) of /cancel om te stoppen."""
    
    def _start_calendar_setup(self, phone: str) -> str:
        """Start step-by-step calendar setup."""
        self._setup_sessions[phone] = {
            "type": "calendar",
            "step": 1,
            "data": {}
        }
        return """📅 *Agenda Account Setup*

Stap 1/4: Welk type agenda?
1️⃣ Exchange/Office 365
2️⃣ Google Calendar
3️⃣ CalDAV (iCloud, Nextcloud, etc.)

Stuur het nummer (1, 2 of 3) of /cancel om te stoppen."""
    
    def _start_json_setup(self, phone: str, account_type: str) -> str:
        """Start JSON-based setup."""
        self._setup_sessions[phone] = {
            "type": f"{account_type}_json",
            "step": 1,
            "data": {}
        }
        
        if account_type == "email":
            return """📧 *Email Account Setup (JSON)*

Stuur een JSON object met de volgende velden:

*Exchange:*
```
{
  "type": "exchange",
  "name": "Werk",
  "email": "je@bedrijf.com",
  "password": "wachtwoord",
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
  "username": "je@gmail.com",
  "password": "app-wachtwoord"
}
```

Of /cancel om te stoppen."""
        else:
            return """📅 *Agenda Account Setup (JSON)*

Stuur een JSON object met de volgende velden:

*Exchange:*
```
{
  "type": "exchange",
  "name": "Werk",
  "email": "je@bedrijf.com",
  "password": "wachtwoord",
  "server": "outlook.office365.com"
}
```

*CalDAV:*
```
{
  "type": "caldav",
  "name": "iCloud",
  "url": "https://caldav.icloud.com",
  "username": "je@icloud.com",
  "password": "app-wachtwoord"
}
```

Of /cancel om te stoppen."""
    
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
                return "❌ Ongeldige JSON. Probeer opnieuw of /cancel."
        
        # Handle step-by-step email setup
        if setup_type == "email":
            return await self._handle_email_setup_step(phone, content, step, data)
        
        # Handle step-by-step calendar setup
        if setup_type == "calendar":
            return await self._handle_calendar_setup_step(phone, content, step, data)
        
        return None
    
    async def _handle_email_setup_step(self, phone: str, content: str, step: int, data: dict) -> str:
        """Handle email setup steps with connection testing."""
        session = self._setup_sessions[phone]
        
        if step == 1:  # Type selection
            if content == "1":
                data["type"] = "exchange"
                session["step"] = 2
                return "Stap 1/7: Wat is je email adres?"
            elif content == "2":
                data["type"] = "imap"
                session["step"] = 2
                return "Stap 1/5: Wat is de IMAP server? (bijv. imap.gmail.com)"
            else:
                return "❌ Kies 1 of 2, of /cancel om te stoppen."
        
        # EXCHANGE EMAIL FLOW
        elif step == 2 and data["type"] == "exchange":
            data["email"] = content
            session["step"] = 3
            return f"Stap 2/7: Wat is je gebruikersnaam?\n(Vaak hetzelfde als email, of DOMAIN\\\\username)\nStuur 'same' om {content} te gebruiken."
        
        elif step == 3 and data["type"] == "exchange":
            data["username"] = data["email"] if content.lower() == "same" else content
            session["step"] = 4
            return "Stap 3/7: Wat is je wachtwoord? (of app-wachtwoord)"
        
        elif step == 4 and data["type"] == "exchange":
            data["password"] = content
            session["step"] = 5
            return """Stap 4/7: Wil je autodiscover gebruiken?

1️⃣ Ja, gebruik autodiscover (aanbevolen voor O365)
2️⃣ Nee, ik voer de server handmatig in

Stuur 1 of 2:"""
        
        elif step == 5 and data["type"] == "exchange":
            if content == "1":
                data["use_autodiscover"] = True
                data["server"] = ""
                session["step"] = 7  # Skip server input
                return "Stap 5/7: Geef dit account een naam (bijv. 'Werk'):"
            elif content == "2":
                data["use_autodiscover"] = False
                session["step"] = 6
                return "Stap 5/7: Wat is de Exchange server?\n(bijv. outlook.office365.com of mail.bedrijf.nl)"
            else:
                return "❌ Kies 1 of 2, of /cancel om te stoppen."
        
        elif step == 6 and data["type"] == "exchange":
            data["server"] = content
            session["step"] = 7
            return "Stap 6/7: Geef dit account een naam (bijv. 'Werk'):"
        
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
                result = self._save_exchange_for_both(data, "email")
                del self._setup_sessions[phone]
                return result
            else:
                result = self._save_account_from_data("email", data)
                del self._setup_sessions[phone]
                return result
        
        # IMAP EMAIL FLOW
        elif step == 2 and data["type"] == "imap":
            data["host"] = content
            session["step"] = 3
            return "Stap 2/5: Wat is je gebruikersnaam/email?"
        
        elif step == 3 and data["type"] == "imap":
            data["username"] = content
            session["step"] = 4
            return "Stap 3/5: Wat is je wachtwoord? (of app-wachtwoord)"
        
        elif step == 4 and data["type"] == "imap":
            data["password"] = content
            session["step"] = 5
            return "Stap 4/5: Geef dit account een naam (bijv. 'Gmail'):"
        
        elif step == 5 and data["type"] == "imap":
            data["name"] = content
            data["port"] = 993
            data["use_ssl"] = True
            result = self._save_account_from_data("email", data)
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
                return "Stap 1/7: Wat is je email adres?"
            elif content == "2":
                data["type"] = "google"
                del self._setup_sessions[phone]
                return """⚠️ *Google Calendar Setup*

Google Calendar vereist OAuth authenticatie via de browser.

Run dit commando in je terminal:
`koda setup --section calendar`

Dit opent een browser voor Google login.

_Setup via WhatsApp niet mogelijk voor Google._"""
            elif content == "3":
                data["type"] = "caldav"
                session["step"] = 2
                return "Stap 1/5: Wat is de CalDAV URL?\n(bijv. https://caldav.icloud.com)"
            else:
                return "❌ Kies 1, 2 of 3, of /cancel om te stoppen."
        
        # EXCHANGE CALENDAR FLOW
        elif step == 2 and data["type"] == "exchange":
            data["email"] = content
            session["step"] = 3
            return f"Stap 2/7: Wat is je gebruikersnaam?\n(Vaak hetzelfde als email, of DOMAIN\\\\username)\nStuur 'same' om {content} te gebruiken."
        
        elif step == 3 and data["type"] == "exchange":
            data["username"] = data["email"] if content.lower() == "same" else content
            session["step"] = 4
            return "Stap 3/7: Wat is je wachtwoord? (of app-wachtwoord)"
        
        elif step == 4 and data["type"] == "exchange":
            data["password"] = content
            session["step"] = 5
            return """Stap 4/7: Wil je autodiscover gebruiken?

1️⃣ Ja, gebruik autodiscover (aanbevolen voor O365)
2️⃣ Nee, ik voer de server handmatig in

Stuur 1 of 2:"""
        
        elif step == 5 and data["type"] == "exchange":
            if content == "1":
                data["use_autodiscover"] = True
                data["server"] = ""
                session["step"] = 7
                return "Stap 5/7: Geef dit account een naam (bijv. 'Werk'):"
            elif content == "2":
                data["use_autodiscover"] = False
                session["step"] = 6
                return "Stap 5/7: Wat is de Exchange server?\n(bijv. outlook.office365.com of mail.bedrijf.nl)"
            else:
                return "❌ Kies 1 of 2, of /cancel om te stoppen."
        
        elif step == 6 and data["type"] == "exchange":
            data["server"] = content
            session["step"] = 7
            return "Stap 6/7: Geef dit account een naam (bijv. 'Werk'):"
        
        elif step == 7 and data["type"] == "exchange":
            data["name"] = content
            session["step"] = 8
            return await self._test_exchange_connection(phone, data, "calendar")
        
        elif step == 8 and data["type"] == "exchange":
            return await self._handle_exchange_retry(phone, content, data, "calendar")
        
        elif step == 9 and data["type"] == "exchange":
            # Ask about using same account for email
            if content.lower() in ["ja", "yes", "j", "y", "1"]:
                result = self._save_exchange_for_both(data, "calendar")
                del self._setup_sessions[phone]
                return result
            else:
                result = self._save_account_from_data("calendar", data)
                del self._setup_sessions[phone]
                return result
        
        # CALDAV FLOW
        elif step == 2 and data["type"] == "caldav":
            data["url"] = content
            session["step"] = 3
            return "Stap 2/5: Wat is je gebruikersnaam?"
        
        elif step == 3 and data["type"] == "caldav":
            data["username"] = content
            session["step"] = 4
            return "Stap 3/5: Wat is je wachtwoord? (of app-wachtwoord)"
        
        elif step == 4 and data["type"] == "caldav":
            data["password"] = content
            session["step"] = 5
            return "Stap 4/5: Geef dit account een naam:"
        
        elif step == 5 and data["type"] == "caldav":
            data["name"] = content
            result = self._save_account_from_data("calendar", data)
            del self._setup_sessions[phone]
            return result
        
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
                    version=version,
                    auth_type='basic'  # Force basic auth
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
            
            other_type = "agenda" if account_type == "email" else "email"
            return f"""✅ *Verbinding geslaagd!*

Account: {data['name']}
Email: {data['email']}
Server: {data.get('server') or 'autodiscover'}

Wil je dit account ook gebruiken voor *{other_type}*?
(Ja/Nee)"""
        
        except ImportError as e:
            logger.error(f"exchangelib import error: {e}")
            logger.error(traceback.format_exc())
            session["step"] = 8
            session["last_error"] = str(e)
            return self._format_exchange_error(f"exchangelib niet gevonden: {e}\nRun: pip install exchangelib", data)
        
        except Exception as e:
            # Catch all exceptions with full traceback
            error_type = type(e).__name__
            error_msg = str(e) or "(geen details)"
            full_traceback = traceback.format_exc()
            
            logger.error(f"Exchange error: {error_type}: {error_msg}")
            logger.error(f"Full traceback:\n{full_traceback}")
            
            session["step"] = 8
            session["last_error"] = f"{error_type}: {error_msg}"
            
            # Provide more specific error messages
            if "Unauthorized" in error_type or "401" in str(e):
                return self._format_exchange_error("Authenticatie mislukt. Controleer email/gebruikersnaam en wachtwoord.", data)
            elif "Transport" in error_type or "Connection" in error_type:
                return self._format_exchange_error(f"Kan geen verbinding maken met server: {error_msg}", data)
            elif "Autodiscover" in str(e) or "autodiscover" in str(e).lower():
                return self._format_exchange_error(f"Autodiscover mislukt: {error_msg}\nProbeer handmatig een server in te voeren.", data)
            else:
                return self._format_exchange_error(f"{error_type}: {error_msg}", data)
    
    def _format_exchange_error(self, error: str, data: dict) -> str:
        """Format Exchange error message with retry options."""
        return f"""❌ *Verbinding mislukt*

Fout: {error}

*Huidige instellingen:*
• Email: {data.get('email', '-')}
• Gebruikersnaam: {data.get('username', '-')}
• Server: {data.get('server') or 'autodiscover'}

*Wat wil je doen?*
1️⃣ Email wijzigen
2️⃣ Gebruikersnaam wijzigen
3️⃣ Wachtwoord wijzigen
4️⃣ Server wijzigen
5️⃣ Autodiscover aan/uit
6️⃣ Opnieuw proberen
7️⃣ Stoppen (/cancel)

Stuur een nummer:"""
    
    async def _handle_exchange_retry(self, phone: str, content: str, data: dict, account_type: str) -> str:
        """Handle retry options after failed Exchange connection."""
        session = self._setup_sessions[phone]
        
        if content == "1":
            session["retry_field"] = "email"
            return "Voer het nieuwe email adres in:"
        elif content == "2":
            session["retry_field"] = "username"
            return "Voer de nieuwe gebruikersnaam in:"
        elif content == "3":
            session["retry_field"] = "password"
            return "Voer het nieuwe wachtwoord in:"
        elif content == "4":
            session["retry_field"] = "server"
            return "Voer de nieuwe server in (bijv. outlook.office365.com):"
        elif content == "5":
            data["use_autodiscover"] = not data.get("use_autodiscover", False)
            status = "AAN" if data["use_autodiscover"] else "UIT"
            return f"Autodiscover staat nu *{status}*. Stuur 6 om opnieuw te proberen."
        elif content == "6":
            return await self._test_exchange_connection(phone, data, account_type)
        elif content == "7" or content.lower() == "/cancel":
            del self._setup_sessions[phone]
            return "✅ Setup geannuleerd."
        elif "retry_field" in session:
            # User is providing new value for a field
            field = session.pop("retry_field")
            data[field] = content
            return await self._test_exchange_connection(phone, data, account_type)
        else:
            return "❌ Kies een nummer (1-7):"
    
    def _save_exchange_for_both(self, data: dict, primary_type: str) -> str:
        """Save Exchange account for both email and calendar."""
        config = load_config()
        
        try:
            account_data = {
                "name": data.get("name", "Exchange"),
                "type": "exchange",
                "enabled": True,
                "email": data.get("email"),
                "username": data.get("username"),
                "password": data.get("password"),
                "server": data.get("server", ""),
                "use_autodiscover": data.get("use_autodiscover", False)
            }
            
            # Add to email accounts
            if not hasattr(config.integrations, 'email_accounts') or config.integrations.email_accounts is None:
                config.integrations.email_accounts = []
            config.integrations.email_accounts.append(account_data.copy())
            
            # Add to calendar accounts
            if not hasattr(config.integrations, 'calendar_accounts') or config.integrations.calendar_accounts is None:
                config.integrations.calendar_accounts = []
            config.integrations.calendar_accounts.append(account_data.copy())
            
            save_config(config)
            
            return f"""✅ *Exchange account toegevoegd!*

Account *{data['name']}* is geconfigureerd voor:
• 📧 Email
• 📅 Agenda

Gebruik /accounts om je accounts te bekijken."""
        
        except Exception as e:
            logger.error(f"Error saving Exchange account: {e}")
            return f"❌ Fout bij opslaan: {e}"
    
    def _save_account_from_data(self, account_type: str, data: dict) -> str:
        """Save account from setup data."""
        config = load_config()
        
        try:
            name = data.get("name", "Account")
            acc_type = data.get("type", "unknown")
            
            account_data = {
                "name": name,
                "type": acc_type,
                "enabled": True,
            }
            
            # Copy relevant fields
            for key in ["email", "username", "password", "server", "host", "port", "url", "use_ssl", "use_autodiscover"]:
                if key in data:
                    account_data[key] = data[key]
            
            if account_type == "email":
                if not hasattr(config.integrations, 'email_accounts') or config.integrations.email_accounts is None:
                    config.integrations.email_accounts = []
                config.integrations.email_accounts.append(account_data)
            else:
                if not hasattr(config.integrations, 'calendar_accounts') or config.integrations.calendar_accounts is None:
                    config.integrations.calendar_accounts = []
                config.integrations.calendar_accounts.append(account_data)
            
            save_config(config)
            return f"✅ {account_type.title()} account *{name}* ({acc_type}) toegevoegd!"
        
        except Exception as e:
            logger.error(f"Error saving account: {e}")
            return f"❌ Fout bij opslaan: {e}"
    
    def _save_account_from_json(self, account_type: str, data: dict) -> str:
        """Save account from JSON data."""
        config = load_config()
        
        try:
            name = data.get("name", "Account")
            acc_type = data.get("type", "unknown")
            
            if account_type == "email":
                # Ensure email_accounts list exists
                if not hasattr(config.integrations, 'email_accounts') or config.integrations.email_accounts is None:
                    config.integrations.email_accounts = []
                
                account = {
                    "name": name,
                    "type": acc_type,
                    "enabled": True,
                    **data
                }
                config.integrations.email_accounts.append(account)
                save_config(config)
                return f"✅ Email account *{name}* ({acc_type}) toegevoegd!"
            
            else:  # calendar
                # Ensure calendar_accounts list exists
                if not hasattr(config.integrations, 'calendar_accounts') or config.integrations.calendar_accounts is None:
                    config.integrations.calendar_accounts = []
                
                account = {
                    "name": name,
                    "type": acc_type,
                    "enabled": True,
                    **data
                }
                config.integrations.calendar_accounts.append(account)
                save_config(config)
                return f"✅ Agenda account *{name}* ({acc_type}) toegevoegd!"
        
        except Exception as e:
            logger.error(f"Error saving account: {e}")
            return f"❌ Fout bij opslaan: {e}"
    
    def _remove_account(self, config, account_type: str, name: str) -> str:
        """Remove an account by name."""
        try:
            if account_type == "email":
                accounts = getattr(config.integrations, 'email_accounts', []) or []
                new_accounts = [a for a in accounts if a.get('name', '').lower() != name.lower()]
                if len(new_accounts) == len(accounts):
                    return f"❌ Email account '{name}' niet gevonden."
                config.integrations.email_accounts = new_accounts
                save_config(config)
                return f"✅ Email account *{name}* verwijderd."
            
            else:  # calendar
                accounts = getattr(config.integrations, 'calendar_accounts', []) or []
                new_accounts = [a for a in accounts if a.get('name', '').lower() != name.lower()]
                if len(new_accounts) == len(accounts):
                    return f"❌ Agenda account '{name}' niet gevonden."
                config.integrations.calendar_accounts = new_accounts
                save_config(config)
                return f"✅ Agenda account *{name}* verwijderd."
        
        except Exception as e:
            logger.error(f"Error removing account: {e}")
            return f"❌ Fout bij verwijderen: {e}"
    
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
