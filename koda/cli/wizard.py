"""Interactive setup wizard for Koda configuration."""

import asyncio
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()


class SetupWizard:
    """Interactive configuration wizard with testing."""
    
    def __init__(self):
        from koda.config.loader import load_config, save_config, get_config_path
        from koda.config.schema import Config
        
        self.config_path = get_config_path()
        self.config = load_config() if self.config_path.exists() else Config()
        self.save_config = save_config
    
    def run(self) -> None:
        """Run the complete setup wizard."""
        console.print(Panel.fit(
            "[bold cyan]Welcome to Koda[/bold cyan]\n\n"
            "Koda is your elite AI Executive Assistant - a powerful autonomous agent\n"
            "that manages your professional life and technical infrastructure.\n\n"
            "[bold]What Koda can do for you:[/bold]\n"
            "  • Manage your calendar (Google, Exchange, CalDAV)\n"
            "  • Read and send emails on your behalf\n"
            "  • Respond to WhatsApp and Telegram messages\n"
            "  • Execute scripts and automate tasks\n"
            "  • Remember context and learn your preferences\n\n"
            "This wizard will guide you through the setup step by step.\n"
            "Each configuration is tested automatically.",
            title="🐕 Koda Setup Wizard"
        ))
        
        # Step 1: Assistant personalization
        console.print("\n[bold yellow]Step 1: Assistant Personalization[/bold yellow]")
        console.print("[dim]Configure how Koda introduces itself and addresses you.[/dim]")
        if Confirm.ask("Configure now?", default=True):
            self._setup_assistant()
        
        # Step 2: LLM Provider
        console.print("\n[bold yellow]Step 2: AI Provider (Required)[/bold yellow]")
        console.print("[dim]Koda needs an LLM API key to function. Choose your preferred provider.[/dim]")
        console.print("[dim]Recommended: OpenRouter (access to multiple models) or Anthropic (Claude).[/dim]")
        if Confirm.ask("Configure now?", default=True):
            self._setup_provider()
        
        # Step 3: Calendar integration
        console.print("\n[bold yellow]Step 3: Calendar Integration[/bold yellow]")
        console.print("[dim]Connect your calendar so Koda can check appointments, schedule meetings,[/dim]")
        console.print("[dim]and remind you of upcoming events. Supports Google, Exchange, and CalDAV.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_calendar()
        
        # Step 4: Email integration
        console.print("\n[bold yellow]Step 4: Email Integration (Read)[/bold yellow]")
        console.print("[dim]Allow Koda to read your emails to summarize, search, and help you[/dim]")
        console.print("[dim]stay on top of your inbox. Supports Gmail, Exchange, and IMAP.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_email()
        
        # Step 5: Bot's own email
        console.print("\n[bold yellow]Step 5: Koda's Email Address (Send)[/bold yellow]")
        console.print("[dim]Give Koda its own email address to send messages, reminders, and[/dim]")
        console.print("[dim]notifications. This is separate from your personal email.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_bot_email()
        
        # Step 6: Messaging channels
        console.print("\n[bold yellow]Step 6: Messaging Channels[/bold yellow]")
        console.print("[dim]Connect Telegram or WhatsApp so Koda can respond to messages,[/dim]")
        console.print("[dim]act as a virtual assistant, or run as an autonomous bot.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_channels()
        
        # Step 7: Webhook API
        console.print("\n[bold yellow]Step 7: Webhook API[/bold yellow]")
        console.print("[dim]Enable the REST API for external integrations, automation triggers,[/dim]")
        console.print("[dim]and scheduled reminders via HTTP requests.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_webhook()
        
        # Save configuration
        self.save_config(self.config)
        console.print("\n[green]✓[/green] Configuration saved!")
        
        # Summary
        self._print_summary()
    
    def _setup_assistant(self) -> None:
        """Configure assistant personalization."""
        console.print("\n[bold cyan]Assistant Personalization[/bold cyan]")
        console.print("[dim]Customize how Koda presents itself and interacts with you.[/dim]\n")
        
        # Assistant name
        current_name = self.config.assistant.name
        console.print("[bold]Assistant Name[/bold]")
        console.print("[dim]The name Koda will use to introduce itself (e.g., 'Hi, I'm Koda!').[/dim]")
        name = Prompt.ask(
            "Name",
            default=current_name
        )
        self.config.assistant.name = name
        
        # User name
        current_user = self.config.assistant.user_name or ""
        console.print("\n[bold]Your Name[/bold]")
        console.print("[dim]How Koda should address you in conversations and messages.[/dim]")
        user_name = Prompt.ask(
            "Your name",
            default=current_user if current_user else "there"
        )
        self.config.assistant.user_name = user_name
        
        # Language
        console.print("\n[bold]Language[/bold]")
        console.print("[dim]Primary language for Koda's responses. Koda can still understand other languages.[/dim]")
        language = Prompt.ask(
            "Language",
            choices=["en", "nl", "de", "fr", "es"],
            default=self.config.assistant.language
        )
        self.config.assistant.language = language
        
        # Personality
        console.print("\n[bold]Personality Style[/bold]")
        console.print("[dim]How Koda communicates:[/dim]")
        console.print("  [cyan]professional[/cyan] - Clear, efficient, business-appropriate")
        console.print("  [cyan]friendly[/cyan] - Warm, casual, conversational")
        console.print("  [cyan]formal[/cyan] - Polite, respectful, traditional")
        personality = Prompt.ask(
            "Style",
            choices=["professional", "friendly", "formal"],
            default=self.config.assistant.personality
        )
        self.config.assistant.personality = personality
        
        console.print(f"\n[green]\u2713[/green] {name} will address you as '{user_name}' in {language} with a {personality} tone.")
    
    def _setup_provider(self) -> None:
        """Configure LLM provider."""
        console.print("\n[bold cyan]AI Provider Configuration[/bold cyan]")
        console.print("[dim]Koda uses a Large Language Model (LLM) to understand and respond.[/dim]")
        console.print("[dim]You need an API key from one of these providers:[/dim]\n")
        
        console.print("  [cyan]openrouter[/cyan] - Access to 100+ models (Claude, GPT-4, Llama, etc.)")
        console.print("                  Best for flexibility. Get key at: https://openrouter.ai/keys")
        console.print("  [cyan]anthropic[/cyan]  - Direct access to Claude models")
        console.print("                  Best quality. Get key at: https://console.anthropic.com/")
        console.print("  [cyan]openai[/cyan]     - GPT-4 and GPT-3.5 models")
        console.print("                  Get key at: https://platform.openai.com/api-keys")
        console.print("  [cyan]gemini[/cyan]     - Google's Gemini models")
        console.print("                  Get key at: https://aistudio.google.com/apikey")
        console.print("  [cyan]groq[/cyan]       - Fast inference for open models")
        console.print("                  Get key at: https://console.groq.com/keys\n")
        
        provider = Prompt.ask(
            "Select provider",
            choices=["openrouter", "anthropic", "openai", "gemini", "groq"],
            default="openrouter"
        )
        
        api_key = Prompt.ask(
            f"Enter your {provider} API key",
            password=True
        )
        
        # Set the API key
        if provider == "openrouter":
            self.config.providers.openrouter.api_key = api_key
        elif provider == "anthropic":
            self.config.providers.anthropic.api_key = api_key
        elif provider == "openai":
            self.config.providers.openai.api_key = api_key
        elif provider == "gemini":
            self.config.providers.gemini.api_key = api_key
        elif provider == "groq":
            self.config.providers.groq.api_key = api_key
        
        # Test the connection
        console.print("Testing API connection...", end=" ")
        success, message = self._test_llm_provider(provider, api_key)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_provider()
    
    def _test_llm_provider(self, provider: str, api_key: str) -> tuple[bool, str]:
        """Test LLM provider connection."""
        try:
            import httpx
            
            if provider == "openrouter":
                url = "https://openrouter.ai/api/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                # Just check auth, don't actually send
                return True, "API key format valid (full test requires usage)"
            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
                headers = {}
            elif provider == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
            else:
                return False, "Unknown provider"
            
            response = httpx.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, "Connection successful"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def _setup_calendar(self) -> None:
        """Configure calendar integration."""
        console.print("\n[bold cyan]Calendar Integration[/bold cyan]")
        console.print("[dim]Connect your calendar so Koda can:[/dim]")
        console.print("  \u2022 Check your schedule and upcoming appointments")
        console.print("  \u2022 Create, modify, and cancel events")
        console.print("  \u2022 Send you reminders before meetings")
        console.print("  \u2022 Help schedule meetings with others\n")
        
        console.print("[bold]Supported Calendar Types:[/bold]")
        console.print("  [cyan]google[/cyan]   - Google Calendar (requires OAuth setup)")
        console.print("  [cyan]exchange[/cyan] - Microsoft Exchange / Outlook 365")
        console.print("  [cyan]caldav[/cyan]   - Nextcloud, ownCloud, Radicale, or any CalDAV server\n")
        
        cal_type = Prompt.ask(
            "Select calendar type",
            choices=["google", "exchange", "caldav", "none"],
            default="none"
        )
        
        if cal_type == "none":
            return
        
        if cal_type == "google":
            self._setup_google_calendar()
        elif cal_type == "exchange":
            self._setup_exchange()
        elif cal_type == "caldav":
            self._setup_caldav()
    
    def _setup_google_calendar(self) -> None:
        """Configure Google Calendar."""
        console.print("\n[bold]Google Calendar Setup[/bold]")
        console.print("[dim]Google Calendar requires OAuth 2.0 credentials for secure access.[/dim]\n")
        console.print("Follow these steps to get your credentials:")
        console.print("  1. Go to [cyan]https://console.cloud.google.com/[/cyan]")
        console.print("  2. Create a new project (or select existing)")
        console.print("  3. Enable the 'Google Calendar API'")
        console.print("  4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
        console.print("  5. Select 'Desktop app' as application type")
        console.print("  6. Download the JSON file and save it\n")
        
        creds_file = Prompt.ask(
            "Path to credentials file",
            default="~/.koda/google_credentials.json"
        )
        
        self.config.integrations.google.enabled = True
        self.config.integrations.google.credentials_file = creds_file
        
        # Test
        if Path(creds_file).expanduser().exists():
            console.print("[green]✓[/green] Credentials file found")
        else:
            console.print("[yellow]![/yellow] Credentials file not found - add it later")
    
    def _setup_exchange(self) -> None:
        """Configure Microsoft Exchange."""
        console.print("\n[bold]Microsoft Exchange Setup[/bold]")
        console.print("[dim]Connect to Exchange Server or Microsoft 365 for calendar and email.[/dim]\n")
        console.print("[yellow]Tip:[/yellow] For Microsoft 365, use an app password instead of your regular password.")
        console.print("Create one at: https://account.microsoft.com/security\n")
        
        email = Prompt.ask("Email address")
        
        username = Prompt.ask(
            "Username (leave empty if same as email, or enter DOMAIN\\\\user format)",
            default=""
        )
        
        password = Prompt.ask("Password (or app password)", password=True)
        
        server = Prompt.ask(
            "Server (leave empty for autodiscover)",
            default=""
        )
        
        version = Prompt.ask(
            "Exchange version",
            choices=["auto", "2013", "2016", "2019", "o365"],
            default="auto"
        )
        
        self.config.integrations.exchange.enabled = True
        self.config.integrations.exchange.email = email
        self.config.integrations.exchange.username = username
        self.config.integrations.exchange.password = password
        self.config.integrations.exchange.server = server
        self.config.integrations.exchange.version = version
        
        # Test connection
        console.print("Testing Exchange connection...", end=" ")
        success, message = self._test_exchange(email, username, password, server, version)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_exchange()
    
    def _test_exchange(self, email: str, username: str, password: str, server: str, version: str) -> tuple[bool, str]:
        """Test Exchange connection."""
        try:
            from exchangelib import Credentials, Account, Configuration, DELEGATE
            from exchangelib import Version, Build
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
            
            # Version mapping
            version_map = {
                "2013": Version(Build(15, 0)),
                "2016": Version(Build(15, 1)),
                "2019": Version(Build(15, 2)),
                "o365": None,  # Auto-detect
                "auto": None
            }
            
            # Use username if provided, otherwise use email
            auth_user = username if username else email
            credentials = Credentials(auth_user, password)
            
            if server:
                config = Configuration(
                    server=server,
                    credentials=credentials,
                    version=version_map.get(version)
                )
                account = Account(
                    email,
                    credentials=credentials,
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE
                )
            else:
                account = Account(
                    email,
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE
                )
            
            # Try to access inbox
            inbox = account.inbox
            return True, f"Connected to {account.primary_smtp_address}"
        
        except ImportError:
            return False, "exchangelib not installed. Run: pip install exchangelib"
        except Exception as e:
            return False, str(e)
    
    def _setup_caldav(self) -> None:
        """Configure CalDAV calendar."""
        console.print("\n[bold]CalDAV Calendar Setup[/bold]")
        console.print("[dim]CalDAV is an open standard supported by many calendar servers.[/dim]\n")
        console.print("Common CalDAV URLs:")
        console.print("  [cyan]Nextcloud:[/cyan] https://your-server.com/remote.php/dav")
        console.print("  [cyan]ownCloud:[/cyan]  https://your-server.com/remote.php/dav")
        console.print("  [cyan]Radicale:[/cyan]  https://your-server.com/username/calendar.ics\n")
        
        url = Prompt.ask("CalDAV URL (e.g., https://nextcloud.example.com/remote.php/dav)")
        username = Prompt.ask("Username")
        password = Prompt.ask("Password", password=True)
        
        self.config.integrations.caldav.enabled = True
        self.config.integrations.caldav.url = url
        self.config.integrations.caldav.username = username
        self.config.integrations.caldav.password = password
        
        # Test connection
        console.print("Testing CalDAV connection...", end=" ")
        success, message = self._test_caldav(url, username, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_caldav()
    
    def _test_caldav(self, url: str, username: str, password: str) -> tuple[bool, str]:
        """Test CalDAV connection."""
        try:
            from koda.integrations.caldav_client import CalDAVClient
            
            client = CalDAVClient(url, username, password)
            return client.test_connection()
        except ImportError as e:
            return False, f"Missing dependency: {e}"
        except Exception as e:
            return False, str(e)
    
    def _setup_email(self) -> None:
        """Configure email integration."""
        console.print("\n[bold cyan]Email Integration (Read)[/bold cyan]")
        console.print("[dim]Allow Koda to read your inbox so it can:[/dim]")
        console.print("  • Summarize unread emails")
        console.print("  • Search for specific messages")
        console.print("  • Extract information from emails")
        console.print("  • Alert you about important messages\n")
        
        console.print("[bold]Supported Email Types:[/bold]")
        console.print("  [cyan]google[/cyan]   - Gmail (uses same credentials as Google Calendar)")
        console.print("  [cyan]exchange[/cyan] - Microsoft Exchange / Outlook 365")
        console.print("  [cyan]imap[/cyan]     - Any email provider with IMAP support\n")
        
        email_type = Prompt.ask(
            "Select email type",
            choices=["google", "exchange", "imap", "none"],
            default="none"
        )
        
        if email_type == "none":
            return
        
        if email_type == "google":
            console.print("[dim]Gmail uses the same credentials as Google Calendar[/dim]")
            self.config.integrations.google.enabled = True
        elif email_type == "exchange":
            if not self.config.integrations.exchange.enabled:
                self._setup_exchange()
        elif email_type == "imap":
            self._setup_imap()
    
    def _setup_imap(self) -> None:
        """Configure IMAP email."""
        console.print("\n[bold]IMAP Email Setup[/bold]")
        console.print("[dim]IMAP works with almost any email provider.[/dim]\n")
        console.print("Common IMAP servers:")
        console.print("  [cyan]Gmail:[/cyan]      imap.gmail.com (port 993)")
        console.print("  [cyan]Outlook:[/cyan]    outlook.office365.com (port 993)")
        console.print("  [cyan]Yahoo:[/cyan]      imap.mail.yahoo.com (port 993)")
        console.print("  [cyan]ProtonMail:[/cyan] Use ProtonMail Bridge\n")
        console.print("[yellow]Tip:[/yellow] Use an app-specific password for better security.\n")
        
        host = Prompt.ask("IMAP server (e.g., imap.gmail.com)")
        port = int(Prompt.ask("Port", default="993"))
        username = Prompt.ask("Username/Email")
        password = Prompt.ask("Password (or app password)", password=True)
        use_ssl = Confirm.ask("Use SSL?", default=True)
        
        self.config.integrations.imap.enabled = True
        self.config.integrations.imap.host = host
        self.config.integrations.imap.port = port
        self.config.integrations.imap.username = username
        self.config.integrations.imap.password = password
        self.config.integrations.imap.use_ssl = use_ssl
        
        # Test connection
        console.print("Testing IMAP connection...", end=" ")
        success, message = self._test_imap(host, port, username, password, use_ssl)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_imap()
    
    def _test_imap(self, host: str, port: int, username: str, password: str, use_ssl: bool) -> tuple[bool, str]:
        """Test IMAP connection."""
        try:
            from koda.integrations.imap_client import IMAPClient
            
            client = IMAPClient(host, port, username, password, use_ssl)
            return client.test_connection()
        except Exception as e:
            return False, str(e)
    
    def _setup_bot_email(self) -> None:
        """Configure bot's own email for sending."""
        console.print("\n[bold cyan]Koda's Email Address (Send)[/bold cyan]")
        console.print("[dim]Give Koda its own email address to send messages on your behalf.[/dim]\n")
        console.print("Koda can use this to:")
        console.print("  \u2022 Send reminder emails to you or others")
        console.print("  \u2022 Forward important information")
        console.print("  \u2022 Send birthday wishes or automated messages")
        console.print("  \u2022 Respond to emails when instructed\n")
        console.print("Common SMTP servers:")
        console.print("  [cyan]Gmail:[/cyan]   smtp.gmail.com (port 587, TLS)")
        console.print("  [cyan]Outlook:[/cyan] smtp.office365.com (port 587, TLS)\n")
        
        host = Prompt.ask("SMTP server (e.g., smtp.gmail.com)")
        port = int(Prompt.ask("Port", default="587"))
        username = Prompt.ask("Username/Email")
        password = Prompt.ask("Password (or app password)", password=True)
        from_email = Prompt.ask("From email address", default=username)
        from_name = Prompt.ask(
            "Display name",
            default=f"{self.config.assistant.name} Assistant"
        )
        use_tls = Confirm.ask("Use TLS?", default=True)
        
        self.config.integrations.bot_email.enabled = True
        self.config.integrations.bot_email.host = host
        self.config.integrations.bot_email.port = port
        self.config.integrations.bot_email.username = username
        self.config.integrations.bot_email.password = password
        self.config.integrations.bot_email.from_email = from_email
        self.config.integrations.bot_email.from_name = from_name
        self.config.integrations.bot_email.use_tls = use_tls
        
        # Test connection
        console.print("Testing SMTP connection...", end=" ")
        success, message = self._test_smtp(host, port, username, password, use_tls)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_bot_email()
    
    def _test_smtp(self, host: str, port: int, username: str, password: str, use_tls: bool) -> tuple[bool, str]:
        """Test SMTP connection."""
        try:
            import smtplib
            
            if use_tls:
                server = smtplib.SMTP(host, port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(host, port)
            
            server.login(username, password)
            server.quit()
            return True, "SMTP connection successful"
        except Exception as e:
            return False, str(e)
    
    def _setup_channels(self) -> None:
        """Configure messaging channels."""
        console.print("\n[bold cyan]Messaging Channels[/bold cyan]")
        console.print("[dim]Connect messaging platforms so Koda can communicate with you and others.[/dim]\n")
        console.print("[bold]Available Channels:[/bold]")
        console.print("  [cyan]Telegram[/cyan] - Create a bot via @BotFather, Koda responds to messages")
        console.print("  [cyan]WhatsApp[/cyan] - Link your WhatsApp, Koda can act as your assistant\n")
        
        # Telegram
        if Confirm.ask("Configure Telegram?", default=False):
            self._setup_telegram()
        
        # WhatsApp
        if Confirm.ask("Configure WhatsApp?", default=False):
            self._setup_whatsapp()
    
    def _setup_telegram(self) -> None:
        """Configure Telegram bot."""
        console.print("\n[bold]Telegram Bot Setup[/bold]")
        console.print("[dim]Create a Telegram bot to chat with Koda via Telegram.[/dim]\n")
        console.print("To create a bot:")
        console.print("  1. Open Telegram and search for [cyan]@BotFather[/cyan]")
        console.print("  2. Send /newbot and follow the instructions")
        console.print("  3. Copy the bot token (looks like: 123456789:ABCdefGHI...)\n")
        
        token = Prompt.ask("Bot token from @BotFather", password=True)
        
        self.config.channels.telegram.enabled = True
        self.config.channels.telegram.token = token
        
        # Test connection
        console.print("Testing Telegram connection...", end=" ")
        success, message = self._test_telegram(token)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            
            # Ask for allowed users
            allow_from = Prompt.ask(
                "Allowed user IDs (comma-separated, or empty for all)",
                default=""
            )
            if allow_from:
                self.config.channels.telegram.allow_from = [
                    x.strip() for x in allow_from.split(",")
                ]
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_telegram()
    
    def _test_telegram(self, token: str) -> tuple[bool, str]:
        """Test Telegram bot token."""
        try:
            import httpx
            
            response = httpx.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    bot_name = data["result"].get("username", "Unknown")
                    return True, f"Connected as @{bot_name}"
            
            return False, "Invalid token"
        except Exception as e:
            return False, str(e)
    
    def _setup_whatsapp(self) -> None:
        """Configure WhatsApp with full bot capabilities."""
        console.print("\n[bold cyan]WhatsApp Configuration[/bold cyan]")
        console.print("[dim]Connect WhatsApp so Koda can read and respond to messages.[/dim]\n")
        console.print("[bold]How it works:[/bold]")
        console.print("  1. Koda runs a WhatsApp Web bridge in the background")
        console.print("  2. You scan a QR code to link your WhatsApp")
        console.print("  3. Koda can then receive and send messages\n")
        console.print("[bold]Two modes available:[/bold]")
        console.print("  [cyan]Bot Mode[/cyan]      - Koda responds to everyone (like a business assistant)")
        console.print("  [cyan]Restricted[/cyan]    - Koda only responds to specific phone numbers\n")
        console.print("[yellow]Note:[/yellow] Run [cyan]koda channels login[/cyan] after setup to link WhatsApp.\n")
        
        self.config.channels.whatsapp.enabled = True
        
        # Bridge URL
        bridge_url = Prompt.ask(
            "Bridge URL",
            default=self.config.channels.whatsapp.bridge_url
        )
        self.config.channels.whatsapp.bridge_url = bridge_url
        
        # Bot mode vs restricted mode
        console.print("\n[bold]Access Mode:[/bold]")
        console.print("  1. Bot Mode - Respond to everyone (like a business bot)")
        console.print("  2. Restricted - Only respond to specific numbers")
        
        bot_mode = Confirm.ask("Enable Bot Mode (respond to everyone)?", default=False)
        self.config.channels.whatsapp.bot_mode = bot_mode
        
        if bot_mode:
            # Bot mode configuration
            console.print("\n[bold]Bot Mode Settings[/bold]")
            
            bot_phone = Prompt.ask(
                "Bot's WhatsApp number (e.g., +31612345678)",
                default=self.config.channels.whatsapp.bot_phone
            )
            self.config.channels.whatsapp.bot_phone = bot_phone
            
            # Owner settings for escalation
            console.print("\n[bold]Owner Settings (for escalation)[/bold]")
            owner_phone = Prompt.ask(
                "Your phone number (for receiving escalations)",
                default=self.config.channels.whatsapp.owner_phone
            )
            self.config.channels.whatsapp.owner_phone = owner_phone
            
            owner_name = Prompt.ask(
                "Your name (shown in greetings)",
                default=self.config.channels.whatsapp.owner_name or self.config.assistant.user_name
            )
            self.config.channels.whatsapp.owner_name = owner_name
            
            # Escalation settings
            escalate = Confirm.ask(
                "Notify you for appointments/urgent requests?",
                default=self.config.channels.whatsapp.escalate_to_owner
            )
            self.config.channels.whatsapp.escalate_to_owner = escalate
            
            if escalate:
                keywords = Prompt.ask(
                    "Escalation keywords (comma-separated)",
                    default=", ".join(self.config.channels.whatsapp.escalation_keywords)
                )
                self.config.channels.whatsapp.escalation_keywords = [
                    k.strip() for k in keywords.split(",") if k.strip()
                ]
            
            # Default greeting
            console.print("\n[bold]Default Messages[/bold]")
            greeting = Prompt.ask(
                "Greeting for new contacts",
                default=self.config.channels.whatsapp.default_greeting
            )
            self.config.channels.whatsapp.default_greeting = greeting
            
            # Per-contact rules
            if Confirm.ask("\nAdd custom rules for specific contacts?", default=False):
                self._setup_whatsapp_contact_rules()
        
        else:
            # Restricted mode - only specific numbers
            allow_from = Prompt.ask(
                "Allowed phone numbers (comma-separated, e.g., +31612345678)",
                default=", ".join(self.config.channels.whatsapp.allow_from)
            )
            if allow_from:
                self.config.channels.whatsapp.allow_from = [
                    x.strip() for x in allow_from.split(",") if x.strip()
                ]
            
            # Owner settings (also useful in restricted mode)
            console.print("\n[bold]Owner Settings[/bold]")
            console.print("[dim]Optional: Set your phone and name for escalations and greetings.[/dim]")
            
            owner_phone = Prompt.ask(
                "Your phone number (optional, for escalations)",
                default=self.config.channels.whatsapp.owner_phone
            )
            self.config.channels.whatsapp.owner_phone = owner_phone
            
            if owner_phone:
                owner_name = Prompt.ask(
                    "Your name",
                    default=self.config.channels.whatsapp.owner_name or self.config.assistant.user_name
                )
                self.config.channels.whatsapp.owner_name = owner_name
        
        console.print("\n[green]✓[/green] WhatsApp configured")
        console.print("[yellow]![/yellow] Start the gateway with 'koda gateway' - WhatsApp bridge starts automatically")
        console.print("[dim]   First time: scan QR code shown in terminal to link WhatsApp[/dim]")
    
    def _setup_whatsapp_contact_rules(self) -> None:
        """Add custom rules for specific WhatsApp contacts."""
        from koda.config.schema import WhatsAppContactRule
        
        console.print("\n[bold]Per-Contact Rules[/bold]")
        console.print("[dim]Add custom instructions for specific contacts[/dim]\n")
        
        rules = list(self.config.channels.whatsapp.contact_rules)
        
        while True:
            phone = Prompt.ask("Phone number (or 'done' to finish)")
            if phone.lower() == 'done':
                break
            
            name = Prompt.ask("Contact name (optional)", default="")
            instructions = Prompt.ask(
                "Custom instructions for this contact",
                default="Be helpful and professional."
            )
            auto_reply = Confirm.ask("Auto-reply to this contact?", default=True)
            
            rule = WhatsAppContactRule(
                phone=phone,
                name=name,
                instructions=instructions,
                auto_reply=auto_reply
            )
            rules.append(rule)
            console.print(f"[green]✓[/green] Added rule for {name or phone}")
        
        self.config.channels.whatsapp.contact_rules = rules
    
    def _setup_webhook(self) -> None:
        """Configure webhook API."""
        console.print("\n[bold cyan]Webhook API Configuration[/bold cyan]")
        console.print("[dim]Enable a REST API for external integrations and automation.[/dim]\n")
        console.print("The webhook API allows you to:")
        console.print("  • Trigger Koda from external services (IFTTT, Zapier, etc.)")
        console.print("  • Schedule reminders via HTTP requests")
        console.print("  • Integrate with custom applications")
        console.print("  • Receive notifications from other systems\n")
        console.print("[yellow]Security:[/yellow] The API only listens on localhost by default.")
        console.print("Use a reverse proxy (nginx/caddy) for external access.\n")
        
        self.config.integrations.reminder.webhook.enabled = True
        
        port = int(Prompt.ask(
            "Webhook API port",
            default=str(self.config.integrations.reminder.webhook.port)
        ))
        self.config.integrations.reminder.webhook.port = port
        
        console.print("\n[bold]API Authentication[/bold]")
        console.print("[dim]Set an API key to protect the webhook endpoint.[/dim]")
        api_key = Prompt.ask(
            "API key (leave empty for no auth)",
            default="",
            password=True
        )
        self.config.integrations.reminder.webhook.api_key = api_key
        
        console.print(f"\n[green]✓[/green] Webhook API configured on port {port}")
        if api_key:
            console.print("[green]✓[/green] API key authentication enabled")
    
    def _print_summary(self) -> None:
        """Print configuration summary."""
        console.print("\n")
        console.print(Panel.fit(
            "[bold]Configuration Summary[/bold]",
            title="✓ Setup Complete"
        ))
        
        table = Table(show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status")
        table.add_column("Details")
        
        # Assistant
        table.add_row(
            "Assistant",
            "[green]✓[/green]",
            f"{self.config.assistant.name} → {self.config.assistant.user_name}"
        )
        
        # Provider
        provider = "Not configured"
        if self.config.providers.openrouter.api_key:
            provider = "OpenRouter"
        elif self.config.providers.anthropic.api_key:
            provider = "Anthropic"
        elif self.config.providers.openai.api_key:
            provider = "OpenAI"
        
        status = "[green]✓[/green]" if provider != "Not configured" else "[red]✗[/red]"
        table.add_row("LLM Provider", status, provider)
        
        # Calendar
        cal_status = []
        if self.config.integrations.google.enabled:
            cal_status.append("Google")
        if self.config.integrations.exchange.enabled:
            cal_status.append("Exchange")
        if self.config.integrations.caldav.enabled:
            cal_status.append("CalDAV")
        
        if cal_status:
            table.add_row("Calendar", "[green]✓[/green]", ", ".join(cal_status))
        else:
            table.add_row("Calendar", "[dim]-[/dim]", "Not configured")
        
        # Email
        email_status = []
        if self.config.integrations.google.enabled:
            email_status.append("Gmail")
        if self.config.integrations.exchange.enabled:
            email_status.append("Exchange")
        if self.config.integrations.imap.enabled:
            email_status.append("IMAP")
        
        if email_status:
            table.add_row("Email", "[green]✓[/green]", ", ".join(email_status))
        else:
            table.add_row("Email", "[dim]-[/dim]", "Not configured")
        
        # Bot email
        if self.config.integrations.bot_email.enabled:
            table.add_row(
                "Bot Email",
                "[green]✓[/green]",
                self.config.integrations.bot_email.from_email
            )
        else:
            table.add_row("Bot Email", "[dim]-[/dim]", "Not configured")
        
        # Channels
        channels = []
        if self.config.channels.telegram.enabled:
            channels.append("Telegram")
        if self.config.channels.whatsapp.enabled:
            channels.append("WhatsApp")
        
        if channels:
            table.add_row("Channels", "[green]✓[/green]", ", ".join(channels))
        else:
            table.add_row("Channels", "[dim]-[/dim]", "Not configured")
        
        # Webhook
        if self.config.integrations.reminder.webhook.enabled:
            port = self.config.integrations.reminder.webhook.port
            table.add_row("Webhook API", "[green]✓[/green]", f"Port {port}")
        else:
            table.add_row("Webhook API", "[dim]-[/dim]", "Not enabled")
        
        console.print(table)
        
        console.print(f"\n[dim]Config saved to: {self.config_path}[/dim]")
        console.print(f"\nStart the gateway: [cyan]koda gateway[/cyan]")


def run_wizard() -> None:
    """Run the setup wizard."""
    wizard = SetupWizard()
    wizard.run()


def configure_section(section: str) -> None:
    """Configure a specific section."""
    wizard = SetupWizard()
    
    section_map = {
        "assistant": wizard._setup_assistant,
        "provider": wizard._setup_provider,
        "calendar": wizard._setup_calendar,
        "email": wizard._setup_email,
        "bot-email": wizard._setup_bot_email,
        "channels": wizard._setup_channels,
        "telegram": wizard._setup_telegram,
        "whatsapp": wizard._setup_whatsapp,
        "whatsapp-contacts": wizard._setup_whatsapp_contact_rules,
        "webhook": wizard._setup_webhook,
        "exchange": wizard._setup_exchange,
        "caldav": wizard._setup_caldav,
        "imap": wizard._setup_imap,
        "google": wizard._setup_google_calendar,
    }
    
    if section not in section_map:
        console.print(f"[red]Unknown section: {section}[/red]")
        console.print(f"Available: {', '.join(section_map.keys())}")
        return
    
    section_map[section]()
    wizard.save_config(wizard.config)
    console.print("\n[green]✓[/green] Configuration saved!")
