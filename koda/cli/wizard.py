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
        
        # Step 5: iCloud Contacts (macOS only)
        import platform
        if platform.system() == "Darwin":
            console.print("\n[bold yellow]Step 5: iCloud Contacts[/bold yellow]")
            console.print("[dim]Sync your iCloud contacts so Koda can look up phone numbers,[/dim]")
            console.print("[dim]send birthday wishes, and address people by name.[/dim]")
            if Confirm.ask("Configure now?", default=False):
                self._setup_icloud_contacts()
        
        # Step 6: Bot's own email
        console.print("\n[bold yellow]Step 6: Koda's Email Address (Send)[/bold yellow]")
        console.print("[dim]Give Koda its own email address to send messages, reminders, and[/dim]")
        console.print("[dim]notifications. This is separate from your personal email.[/dim]")
        if Confirm.ask("Configure now?", default=False):
            self._setup_bot_email()
        
        # Step 7: Messaging channels
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
        
        # Model selection based on provider
        model = self._select_model(provider)
        
        # Set the API key and model
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
        
        # Set the default model
        self.config.agents.defaults.model = model
        
        # Test the connection with a real prompt
        console.print("\nTesting LLM connection...", end=" ")
        success, message = self._test_llm_chat(provider, api_key, model)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            console.print(f"\n[green]✓[/green] Provider configured: {provider}")
            console.print(f"[green]✓[/green] Model: {model}")
        else:
            console.print(f"[red]✗[/red] {message}")
            if Confirm.ask("Try again?"):
                self._setup_provider()
    
    def _select_model(self, provider: str) -> str:
        """Select a model for the provider."""
        console.print("\n[bold]Model Selection[/bold]")
        console.print("[dim]Choose a model based on your needs and budget.[/dim]\n")
        
        if provider == "openrouter":
            console.print("[bold]Popular OpenRouter Models:[/bold]")
            console.print("  [cyan]anthropic/claude-sonnet-4-20250514[/cyan] - Best balance (recommended)")
            console.print("  [cyan]anthropic/claude-opus-4-5[/cyan] - Most capable, expensive")
            console.print("  [cyan]openai/gpt-4o[/cyan] - OpenAI's latest")
            console.print("  [cyan]openai/gpt-4o-mini[/cyan] - Fast and cheap")
            console.print("  [cyan]google/gemini-2.0-flash-001[/cyan] - Google's fast model")
            console.print("  [cyan]meta-llama/llama-3.3-70b-instruct[/cyan] - Open source, good value")
            console.print("  [cyan]deepseek/deepseek-chat[/cyan] - Very cheap, good quality\n")
            
            model = Prompt.ask(
                "Model name",
                default="anthropic/claude-sonnet-4-20250514"
            )
        elif provider == "anthropic":
            console.print("[bold]Anthropic Models:[/bold]")
            console.print("  [cyan]claude-sonnet-4-20250514[/cyan] - Best balance (recommended)")
            console.print("  [cyan]claude-opus-4-5[/cyan] - Most capable")
            console.print("  [cyan]claude-3-5-haiku-20241022[/cyan] - Fast and cheap\n")
            
            model = Prompt.ask(
                "Model name",
                default="claude-sonnet-4-20250514"
            )
        elif provider == "openai":
            console.print("[bold]OpenAI Models:[/bold]")
            console.print("  [cyan]gpt-4o[/cyan] - Latest and best (recommended)")
            console.print("  [cyan]gpt-4o-mini[/cyan] - Fast and cheap")
            console.print("  [cyan]gpt-4-turbo[/cyan] - Previous generation\n")
            
            model = Prompt.ask(
                "Model name",
                default="gpt-4o"
            )
        elif provider == "gemini":
            console.print("[bold]Google Gemini Models:[/bold]")
            console.print("  [cyan]gemini-2.0-flash[/cyan] - Fast (recommended)")
            console.print("  [cyan]gemini-1.5-pro[/cyan] - More capable")
            console.print("  [cyan]gemini-1.5-flash[/cyan] - Previous fast model\n")
            
            model = Prompt.ask(
                "Model name",
                default="gemini-2.0-flash"
            )
        elif provider == "groq":
            console.print("[bold]Groq Models (very fast inference):[/bold]")
            console.print("  [cyan]llama-3.3-70b-versatile[/cyan] - Best quality (recommended)")
            console.print("  [cyan]llama-3.1-8b-instant[/cyan] - Fastest")
            console.print("  [cyan]mixtral-8x7b-32768[/cyan] - Good balance\n")
            
            model = Prompt.ask(
                "Model name",
                default="llama-3.3-70b-versatile"
            )
        else:
            model = "gpt-4o"
        
        return model
    
    def _test_llm_chat(self, provider: str, api_key: str, model: str) -> tuple[bool, str]:
        """Test LLM with an actual chat request."""
        try:
            import httpx
            
            test_message = "Say 'Hello! Koda is ready.' and nothing else."
            
            if provider == "openrouter":
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_message}],
                    "max_tokens": 20
                }
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_message}],
                    "max_tokens": 20
                }
            elif provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_message}],
                    "max_tokens": 20
                }
            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                data = {
                    "contents": [{"parts": [{"text": test_message}]}]
                }
            elif provider == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_message}],
                    "max_tokens": 20
                }
            else:
                return False, "Unknown provider"
            
            response = httpx.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                # Extract response text based on provider
                if provider == "anthropic":
                    text = result.get("content", [{}])[0].get("text", "")
                elif provider == "gemini":
                    text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                else:
                    text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if text:
                    return True, f"LLM responded: '{text.strip()[:50]}'"
                return True, "LLM connected successfully"
            elif response.status_code == 401:
                return False, "Invalid API key"
            elif response.status_code == 404:
                return False, f"Model '{model}' not found"
            else:
                error = response.json().get("error", {}).get("message", response.text[:100])
                return False, f"Error: {error}"
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def _setup_calendar(self) -> None:
        """Configure calendar integration."""
        from koda.config.schema import CalendarAccount
        
        console.print("\n[bold cyan]Calendar Integration[/bold cyan]")
        console.print("[dim]Connect your calendars so Koda can manage appointments.[/dim]\n")
        
        # Show existing accounts
        accounts = self.config.integrations.calendar_accounts
        
        # Also check legacy configs and show them
        legacy_accounts = []
        if self.config.integrations.google.enabled:
            legacy_accounts.append(("Google (API)", "google-legacy"))
        if self.config.integrations.exchange.enabled:
            legacy_accounts.append((f"Exchange ({self.config.integrations.exchange.email})", "exchange-legacy"))
        if self.config.integrations.caldav.enabled:
            legacy_accounts.append((f"CalDAV ({self.config.integrations.caldav.url[:30]}...)", "caldav-legacy"))
        
        if accounts or legacy_accounts:
            console.print("[bold]Current Calendar Accounts:[/bold]")
            for i, acc in enumerate(accounts):
                status = "[green]✓[/green]" if acc.enabled else "[dim]○[/dim]"
                console.print(f"  {status} {i+1}. [cyan]{acc.name}[/cyan] ({acc.type})")
            for name, _ in legacy_accounts:
                console.print(f"  [green]✓[/green] [cyan]{name}[/cyan] (legacy config)")
            console.print()
            
            action = Prompt.ask(
                "What would you like to do?",
                choices=["add", "edit", "done"],
                default="done"
            )
            
            if action == "done":
                return
            elif action == "edit" and accounts:
                idx = int(Prompt.ask("Which account to edit? (number)", default="1")) - 1
                if 0 <= idx < len(accounts):
                    self._edit_calendar_account(idx)
                return
        else:
            console.print("[dim]No calendar accounts configured yet.[/dim]\n")
        
        # Add new account
        self._add_calendar_account()
    
    def _add_calendar_account(self, existing_account: "CalendarAccount | None" = None) -> None:
        """Add a new calendar account. If existing_account provided, use as defaults for retry."""
        from koda.config.schema import CalendarAccount
        
        # Use existing values as defaults if retrying
        if existing_account:
            console.print("\n[dim]Previous values will be used as defaults.[/dim]\n")
            # Map internal type back to selection type
            if existing_account.url and "google" in existing_account.url:
                cal_type = "gmail"
            elif existing_account.url and "icloud" in existing_account.url:
                cal_type = "icloud"
            elif existing_account.type == "exchange":
                cal_type = "exchange"
            elif existing_account.type == "google":
                cal_type = "google"
            else:
                cal_type = "caldav"
            account = existing_account
        else:
            console.print("[bold]Add Calendar Account[/bold]\n")
            console.print("[bold]Supported Types:[/bold]")
            console.print("  [cyan]gmail[/cyan]    - Google Calendar via CalDAV (simple, app password)")
            console.print("  [cyan]icloud[/cyan]   - Apple iCloud Calendar")
            console.print("  [cyan]exchange[/cyan] - Microsoft Exchange / Outlook 365")
            console.print("  [cyan]caldav[/cyan]   - Nextcloud, ownCloud, or custom CalDAV")
            console.print("  [cyan]google[/cyan]   - Google Calendar via API (complex, OAuth)\n")
            
            cal_type = Prompt.ask(
                "Select calendar type",
                choices=["gmail", "icloud", "exchange", "caldav", "google", "cancel"],
                default="gmail"
            )
            
            if cal_type == "cancel":
                return
            
            # Ask for account name
            default_name = {
                "gmail": "Gmail Calendar",
                "icloud": "iCloud Calendar", 
                "exchange": "Work Calendar",
                "caldav": "CalDAV Calendar",
                "google": "Google Calendar"
            }.get(cal_type, "My Calendar")
            
            name = Prompt.ask("Account name", default=default_name)
            
            # Create account based on type
            account = CalendarAccount(name=name, type=cal_type, enabled=True)
        
        if cal_type == "gmail":
            success = self._configure_gmail_calendar(account)
        elif cal_type == "icloud":
            success = self._configure_icloud_calendar(account)
        elif cal_type == "exchange":
            success = self._configure_exchange_calendar(account)
        elif cal_type == "caldav":
            success = self._configure_caldav_calendar(account)
        elif cal_type == "google":
            success = self._configure_google_api_calendar(account)
        else:
            success = False
        
        if success:
            # Only add if not already in list (retry case)
            if account not in self.config.integrations.calendar_accounts:
                self.config.integrations.calendar_accounts.append(account)
            console.print(f"\n[green]✓[/green] Calendar account '{account.name}' added successfully!")
        else:
            if not Confirm.ask("Configuration failed. Try again with same settings?", default=True):
                return
            # Retry with same account (preserves entered values)
            self._add_calendar_account(account)
    
    def _configure_gmail_calendar(self, account: "CalendarAccount") -> bool:
        """Configure Gmail CalDAV calendar."""
        console.print("\n[bold]Gmail Calendar Setup[/bold]")
        console.print("[dim]Use your Gmail and an App Password.[/dim]\n")
        console.print("[bold]Create an App Password:[/bold]")
        console.print("  1. Go to [cyan]https://myaccount.google.com/apppasswords[/cyan]")
        console.print("  2. Select 'Mail' and 'Other (Custom name)'")
        console.print("  3. Enter 'Koda' and copy the 16-character password\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Gmail address", default=account.email or "")
        password = Prompt.ask("App password", password=True, default=account.password or "")
        
        account.type = "caldav"
        account.url = f"https://apidata.googleusercontent.com/caldav/v2/{email}/events"
        account.email = email
        account.password = password
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_caldav(account.url, email, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _configure_icloud_calendar(self, account: "CalendarAccount") -> bool:
        """Configure iCloud CalDAV calendar."""
        console.print("\n[bold]iCloud Calendar Setup[/bold]")
        console.print("[dim]Use your Apple ID and an App-Specific Password.[/dim]\n")
        console.print("[bold]Create an App-Specific Password:[/bold]")
        console.print("  1. Go to [cyan]https://appleid.apple.com/[/cyan]")
        console.print("  2. Sign in → App-Specific Passwords → Create\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Apple ID email", default=account.email or "")
        password = Prompt.ask("App-Specific Password", password=True, default=account.password or "")
        
        account.type = "caldav"
        account.url = "https://caldav.icloud.com"
        account.email = email
        account.password = password
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_caldav(account.url, email, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _configure_exchange_calendar(self, account: "CalendarAccount") -> bool:
        """Configure Exchange calendar."""
        console.print("\n[bold]Exchange Calendar Setup[/bold]")
        console.print("[dim]Connect to Microsoft Exchange or Office 365.[/dim]\n")
        console.print("[bold]Server formats:[/bold]")
        console.print("  [cyan]Office 365:[/cyan]     outlook.office365.com")
        console.print("  [cyan]On-premises:[/cyan]   exchange.yourcompany.com")
        console.print("  [cyan]Autodiscover:[/cyan]  Leave empty to auto-detect\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Email address", default=account.email or "")
        username = Prompt.ask("Username (leave empty if same as email)", default=account.username or "")
        password = Prompt.ask("Password", password=True, default=account.password or "")
        server = Prompt.ask("Server (leave empty for autodiscover)", default=account.server or "")
        
        account.type = "exchange"
        account.email = email
        account.username = username or email
        account.password = password
        account.server = server
        account.version = "auto"
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_exchange(email, username or email, password, server, "auto")
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            
            # Offer to also configure email with same credentials
            if Confirm.ask("\nAlso configure Exchange email with same credentials?", default=True):
                self._add_exchange_email_from_calendar(account)
            
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("\n[dim]Troubleshooting tips:[/dim]")
            console.print("  • For Office 365: use 'outlook.office365.com'")
            console.print("  • For on-premises: try leaving server empty for autodiscover")
            console.print("  • Check if your account requires an app password")
            return False
    
    def _add_exchange_email_from_calendar(self, cal_account: "CalendarAccount") -> None:
        """Add Exchange email using same credentials as calendar."""
        from koda.config.schema import EmailAccount
        
        email_account = EmailAccount(
            name=f"{cal_account.name} Email",
            type="exchange",
            enabled=True,
            email=cal_account.email,
            username=cal_account.username,
            password=cal_account.password,
            server=cal_account.server
        )
        self.config.integrations.email_accounts.append(email_account)
        console.print(f"[green]✓[/green] Email account '{email_account.name}' added!")
    
    def _configure_caldav_calendar(self, account: "CalendarAccount") -> bool:
        """Configure generic CalDAV calendar."""
        console.print("\n[bold]CalDAV Calendar Setup[/bold]")
        console.print("[dim]Connect to any CalDAV server.[/dim]\n")
        console.print("Common CalDAV URLs:")
        console.print("  [cyan]Nextcloud:[/cyan] https://your-server/remote.php/dav")
        console.print("  [cyan]Radicale:[/cyan]  https://your-server/username/calendar.ics\n")
        
        # Use existing values as defaults
        url = Prompt.ask("CalDAV URL", default=account.url or "")
        username = Prompt.ask("Username", default=account.email or "")
        password = Prompt.ask("Password", password=True, default=account.password or "")
        
        account.type = "caldav"
        account.url = url
        account.email = username
        account.password = password
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_caldav(url, username, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _configure_google_api_calendar(self, account: "CalendarAccount") -> bool:
        """Configure Google Calendar via OAuth API."""
        console.print("\n[bold]Google Calendar API Setup[/bold]")
        console.print("[yellow]Note:[/yellow] This is complex. Consider using 'gmail' option instead.\n")
        console.print("Steps:")
        console.print("  1. Go to [cyan]https://console.cloud.google.com/[/cyan]")
        console.print("  2. Create project → Enable Google Calendar API")
        console.print("  3. Create OAuth credentials → Download JSON\n")
        
        creds_file = Prompt.ask("Path to credentials file", default="~/.koda/google_credentials.json")
        
        account.type = "google"
        account.credentials_file = creds_file
        
        if Path(creds_file).expanduser().exists():
            console.print("[green]✓[/green] Credentials file found")
            return True
        else:
            console.print("[yellow]![/yellow] File not found - add it later")
            return Confirm.ask("Continue anyway?", default=True)
    
    def _edit_calendar_account(self, idx: int) -> None:
        """Edit an existing calendar account."""
        account = self.config.integrations.calendar_accounts[idx]
        
        # Show current settings
        console.print(f"\n[bold]Calendar Account: {account.name}[/bold]")
        console.print(f"  [cyan]Type:[/cyan]    {account.type}")
        console.print(f"  [cyan]Status:[/cyan]  {'Enabled' if account.enabled else 'Disabled'}")
        if account.type == "caldav":
            console.print(f"  [cyan]URL:[/cyan]     {account.url[:50]}{'...' if len(account.url) > 50 else ''}")
            console.print(f"  [cyan]User:[/cyan]    {account.email}")
        elif account.type == "exchange":
            console.print(f"  [cyan]Email:[/cyan]   {account.email}")
            console.print(f"  [cyan]Server:[/cyan]  {account.server}")
        elif account.type == "google":
            console.print(f"  [cyan]Credentials:[/cyan] {account.credentials_file}")
        console.print()
        
        action = Prompt.ask(
            "Action",
            choices=["rename", "reconfigure", "toggle", "delete", "back"],
            default="back"
        )
        
        if action == "rename":
            account.name = Prompt.ask("New name", default=account.name)
            console.print(f"[green]✓[/green] Renamed to '{account.name}'")
        elif action == "reconfigure":
            # Re-run configuration for this account type
            if account.type == "caldav":
                self._configure_caldav_calendar(account)
            elif account.type == "exchange":
                self._configure_exchange_calendar(account)
            elif account.type == "google":
                self._configure_google_api_calendar(account)
        elif action == "toggle":
            account.enabled = not account.enabled
            status = "enabled" if account.enabled else "disabled"
            console.print(f"[green]✓[/green] Account {status}")
        elif action == "delete":
            if Confirm.ask(f"Delete '{account.name}'?", default=False):
                self.config.integrations.calendar_accounts.pop(idx)
                console.print("[green]✓[/green] Account deleted")
    
    def _setup_gmail_caldav(self) -> None:
        """Configure Gmail Calendar via CalDAV (simpler than OAuth)."""
        console.print("\n[bold]Gmail Calendar Setup (CalDAV)[/bold]")
        console.print("[dim]This is the easy way - just use your email and an app password.[/dim]\n")
        console.print("[bold]Steps to create an App Password:[/bold]")
        console.print("  1. Go to [cyan]https://myaccount.google.com/apppasswords[/cyan]")
        console.print("  2. Select 'Mail' and 'Other (Custom name)'")
        console.print("  3. Enter 'Koda' as the name")
        console.print("  4. Copy the 16-character password\n")
        console.print("[yellow]Note:[/yellow] 2-Step Verification must be enabled for App Passwords.\n")
        
        email = Prompt.ask("Gmail address")
        password = Prompt.ask("App password (16 characters, no spaces)", password=True)
        
        # Gmail CalDAV URL
        caldav_url = f"https://apidata.googleusercontent.com/caldav/v2/{email}/events"
        
        self.config.integrations.caldav.enabled = True
        self.config.integrations.caldav.url = caldav_url
        self.config.integrations.caldav.username = email
        self.config.integrations.caldav.password = password
        
        # Test connection
        console.print("Testing CalDAV connection...", end=" ")
        success, message = self._test_caldav(caldav_url, email, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("[dim]Make sure 2-Step Verification is on and you're using an App Password[/dim]")
    
    def _setup_icloud_caldav(self) -> None:
        """Configure iCloud Calendar via CalDAV."""
        console.print("\n[bold]iCloud Calendar Setup[/bold]")
        console.print("[dim]Connect to your Apple iCloud Calendar.[/dim]\n")
        console.print("[bold]Steps to create an App-Specific Password:[/bold]")
        console.print("  1. Go to [cyan]https://appleid.apple.com/[/cyan]")
        console.print("  2. Sign in and go to 'App-Specific Passwords'")
        console.print("  3. Click '+' and create a password for 'Koda'")
        console.print("  4. Copy the generated password\n")
        
        email = Prompt.ask("Apple ID email")
        password = Prompt.ask("App-Specific Password", password=True)
        
        # iCloud CalDAV URL
        caldav_url = "https://caldav.icloud.com"
        
        self.config.integrations.caldav.enabled = True
        self.config.integrations.caldav.url = caldav_url
        self.config.integrations.caldav.username = email
        self.config.integrations.caldav.password = password
        
        # Test connection
        console.print("Testing CalDAV connection...", end=" ")
        success, message = self._test_caldav(caldav_url, email, password)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("[dim]Make sure you're using an App-Specific Password, not your Apple ID password[/dim]")
    
    def _setup_google_calendar(self) -> None:
        """Configure Google Calendar via OAuth (complex)."""
        console.print("\n[bold]Google Calendar Setup (OAuth API)[/bold]")
        console.print("[dim]This requires setting up a Google Cloud project.[/dim]")
        console.print("[yellow]Tip:[/yellow] Consider using 'gmail' option instead - it's much simpler!\n")
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
            from exchangelib import Version, Build, NTLM, BASIC
            from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
            import requests
            
            # Disable SSL warnings for testing
            import urllib3
            urllib3.disable_warnings()
            
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
            
            # Try to set up HTTP adapter for self-signed certificates
            BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
            
            console.print("[dim]Trying connection with provided credentials...[/dim]")
            
            if server:
                # Try with explicit server configuration
                # First try basic auth
                try:
                    console.print(f"[dim]Attempting basic auth to {server}...[/dim]")
                    credentials = Credentials(auth_user, password)
                    config = Configuration(
                        server=server,
                        credentials=credentials,
                        auth_type=BASIC,
                        version=version_map.get(version)
                    )
                    account = Account(
                        email,
                        credentials=credentials,
                        config=config,
                        autodiscover=False,
                        access_type=DELEGATE
                    )
                    # Try to access inbox to test connection
                    inbox = account.inbox
                    total_count = inbox.total_count
                    return True, f"Connected to {server} ({total_count} items in inbox)"
                except Exception as e1:
                    console.print(f"[dim]Basic auth failed: {str(e1)[:100]}[/dim]")
                    
                    # Try NTLM auth
                    try:
                        console.print(f"[dim]Attempting NTLM auth to {server}...[/dim]")
                        credentials = Credentials(auth_user, password)
                        config = Configuration(
                            server=server,
                            credentials=credentials,
                            auth_type=NTLM,
                            version=version_map.get(version)
                        )
                        account = Account(
                            email,
                            credentials=credentials,
                            config=config,
                            autodiscover=False,
                            access_type=DELEGATE
                        )
                        # Try to access inbox
                        inbox = account.inbox
                        total_count = inbox.total_count
                        return True, f"Connected to {server} with NTLM ({total_count} items in inbox)"
                    except Exception as e2:
                        console.print(f"[dim]NTLM auth failed: {str(e2)[:100]}[/dim]")
                        
                        # Last resort: try autodiscover even though server was specified
                        try:
                            console.print(f"[dim]Attempting autodiscover...[/dim]")
                            credentials = Credentials(auth_user, password)
                            account = Account(
                                email,
                                credentials=credentials,
                                autodiscover=True,
                                access_type=DELEGATE
                            )
                            inbox = account.inbox
                            total_count = inbox.total_count
                            return True, f"Connected via autodiscover ({total_count} items in inbox)"
                        except Exception as e3:
                            return False, f"All methods failed. Last error: {str(e3)[:200]}"
            else:
                # Use autodiscover
                console.print(f"[dim]Using autodiscover for {email}...[/dim]")
                credentials = Credentials(auth_user, password)
                account = Account(
                    email,
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE
                )
                inbox = account.inbox
                total_count = inbox.total_count
                return True, f"Connected via autodiscover ({total_count} items in inbox)"
        
        except ImportError:
            return False, "exchangelib not installed. Run: pip install exchangelib"
        except Exception as e:
            import traceback
            console.print(f"[red]Full error:[/red]\n{traceback.format_exc()}")
            return False, f"Error: {str(e)[:200]}"
    
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
        from koda.config.schema import EmailAccount
        
        console.print("\n[bold cyan]Email Integration (Read)[/bold cyan]")
        console.print("[dim]Connect your email so Koda can read and manage your inbox.[/dim]\n")
        
        # Show existing accounts
        accounts = self.config.integrations.email_accounts
        
        # Also check legacy configs
        legacy_accounts = []
        if self.config.integrations.google.enabled:
            legacy_accounts.append(("Gmail (API)", "google-legacy"))
        if self.config.integrations.exchange.enabled:
            legacy_accounts.append((f"Exchange ({self.config.integrations.exchange.email})", "exchange-legacy"))
        if self.config.integrations.imap.enabled:
            legacy_accounts.append((f"IMAP ({self.config.integrations.imap.username})", "imap-legacy"))
        
        if accounts or legacy_accounts:
            console.print("[bold]Current Email Accounts:[/bold]")
            for i, acc in enumerate(accounts):
                status = "[green]✓[/green]" if acc.enabled else "[dim]○[/dim]"
                console.print(f"  {status} {i+1}. [cyan]{acc.name}[/cyan] ({acc.type})")
            for name, _ in legacy_accounts:
                console.print(f"  [green]✓[/green] [cyan]{name}[/cyan] (legacy config)")
            console.print()
            
            action = Prompt.ask(
                "What would you like to do?",
                choices=["add", "edit", "done"],
                default="done"
            )
            
            if action == "done":
                return
            elif action == "edit" and accounts:
                idx = int(Prompt.ask("Which account to edit? (number)", default="1")) - 1
                if 0 <= idx < len(accounts):
                    self._edit_email_account(idx)
                return
        else:
            console.print("[dim]No email accounts configured yet.[/dim]\n")
        
        # Add new account
        self._add_email_account()
    
    def _add_email_account(self, existing_account: "EmailAccount | None" = None) -> None:
        """Add a new email account. If existing_account provided, use as defaults for retry."""
        from koda.config.schema import EmailAccount
        
        # Use existing values as defaults if retrying
        if existing_account:
            console.print("\n[dim]Previous values will be used as defaults.[/dim]\n")
            email_type = existing_account.type if existing_account.type != "imap" else "gmail"
            # Map internal type back to selection type
            if existing_account.host == "imap.gmail.com":
                email_type = "gmail"
            elif existing_account.host == "imap.mail.me.com":
                email_type = "icloud"
            elif existing_account.type == "exchange":
                email_type = "exchange"
            else:
                email_type = "imap"
            name = existing_account.name
            account = existing_account
        else:
            console.print("[bold]Add Email Account[/bold]\n")
            console.print("[bold]Supported Types:[/bold]")
            console.print("  [cyan]gmail[/cyan]    - Gmail via IMAP (simple, app password)")
            console.print("  [cyan]icloud[/cyan]   - iCloud Mail via IMAP")
            console.print("  [cyan]exchange[/cyan] - Microsoft Exchange / Outlook 365")
            console.print("  [cyan]imap[/cyan]     - Any other email provider\n")
            
            email_type = Prompt.ask(
                "Select email type",
                choices=["gmail", "icloud", "exchange", "imap", "cancel"],
                default="gmail"
            )
            
            if email_type == "cancel":
                return
            
            # Ask for account name
            default_name = {
                "gmail": "Gmail",
                "icloud": "iCloud Mail",
                "exchange": "Work Email",
                "imap": "Email"
            }.get(email_type, "My Email")
            
            name = Prompt.ask("Account name", default=default_name)
            
            # Create account based on type
            account = EmailAccount(name=name, type=email_type, enabled=True)
        
        if email_type == "gmail":
            success = self._configure_gmail_email(account)
        elif email_type == "icloud":
            success = self._configure_icloud_email(account)
        elif email_type == "exchange":
            success = self._configure_exchange_email(account)
        elif email_type == "imap":
            success = self._configure_imap_email(account)
        else:
            success = False
        
        if success:
            # Only add if not already in list (retry case)
            if account not in self.config.integrations.email_accounts:
                self.config.integrations.email_accounts.append(account)
            console.print(f"\n[green]✓[/green] Email account '{account.name}' added successfully!")
        else:
            if not Confirm.ask("Configuration failed. Try again with same settings?", default=True):
                return
            # Retry with same account (preserves entered values)
            self._add_email_account(account)
    
    def _configure_gmail_email(self, account: "EmailAccount") -> bool:
        """Configure Gmail via IMAP."""
        console.print("\n[bold]Gmail Setup[/bold]")
        console.print("[dim]Use your Gmail and an App Password.[/dim]\n")
        console.print("[bold]Create an App Password:[/bold]")
        console.print("  1. Go to [cyan]https://myaccount.google.com/apppasswords[/cyan]")
        console.print("  2. Select 'Mail' and 'Other (Custom name)'")
        console.print("  3. Enter 'Koda' and copy the 16-character password\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Gmail address", default=account.email or "")
        password = Prompt.ask("App password", password=True, default=account.password or "")
        
        account.type = "imap"
        account.host = "imap.gmail.com"
        account.port = 993
        account.email = email
        account.password = password
        account.use_ssl = True
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_imap("imap.gmail.com", 993, email, password, True)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _configure_icloud_email(self, account: "EmailAccount") -> bool:
        """Configure iCloud Mail via IMAP."""
        console.print("\n[bold]iCloud Mail Setup[/bold]")
        console.print("[dim]Use your Apple ID and an App-Specific Password.[/dim]\n")
        console.print("[bold]Create an App-Specific Password:[/bold]")
        console.print("  1. Go to [cyan]https://appleid.apple.com/[/cyan]")
        console.print("  2. Sign in → App-Specific Passwords → Create\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Apple ID email", default=account.email or "")
        password = Prompt.ask("App-Specific Password", password=True, default=account.password or "")
        
        account.type = "imap"
        account.host = "imap.mail.me.com"
        account.port = 993
        account.email = email
        account.password = password
        account.use_ssl = True
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_imap("imap.mail.me.com", 993, email, password, True)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _configure_exchange_email(self, account: "EmailAccount") -> bool:
        """Configure Exchange email."""
        console.print("\n[bold]Exchange Email Setup[/bold]")
        console.print("[dim]Connect to Microsoft Exchange or Office 365.[/dim]\n")
        console.print("[bold]Server formats:[/bold]")
        console.print("  [cyan]Office 365:[/cyan]     outlook.office365.com")
        console.print("  [cyan]On-premises:[/cyan]   exchange.yourcompany.com")
        console.print("  [cyan]Autodiscover:[/cyan]  Leave empty to auto-detect\n")
        
        # Use existing values as defaults
        email = Prompt.ask("Email address", default=account.email or "")
        username = Prompt.ask("Username (leave empty if same as email)", default=account.username or "")
        password = Prompt.ask("Password", password=True, default=account.password or "")
        server = Prompt.ask("Server (leave empty for autodiscover)", default=account.server or "")
        
        account.type = "exchange"
        account.email = email
        account.username = username or email
        account.password = password
        account.server = server
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_exchange(email, username or email, password, server, "auto")
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            
            # Offer to also configure calendar with same credentials
            if Confirm.ask("\nAlso configure Exchange calendar with same credentials?", default=True):
                self._add_exchange_calendar_from_email(account)
            
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("\n[dim]Troubleshooting tips:[/dim]")
            console.print("  • For Office 365: use 'outlook.office365.com'")
            console.print("  • For on-premises: try leaving server empty for autodiscover")
            console.print("  • Check if your account requires an app password")
            return False
    
    def _add_exchange_calendar_from_email(self, email_account: "EmailAccount") -> None:
        """Add Exchange calendar using same credentials as email."""
        from koda.config.schema import CalendarAccount
        
        cal_account = CalendarAccount(
            name=f"{email_account.name.replace(' Email', '')} Calendar",
            type="exchange",
            enabled=True,
            email=email_account.email,
            username=email_account.username,
            password=email_account.password,
            server=email_account.server
        )
        self.config.integrations.calendar_accounts.append(cal_account)
        console.print(f"[green]✓[/green] Calendar account '{cal_account.name}' added!")
    
    def _configure_imap_email(self, account: "EmailAccount") -> bool:
        """Configure generic IMAP email."""
        console.print("\n[bold]IMAP Email Setup[/bold]")
        console.print("[dim]Connect to any IMAP mail server.[/dim]\n")
        console.print("Common IMAP servers:")
        console.print("  [cyan]Outlook:[/cyan]    outlook.office365.com (port 993)")
        console.print("  [cyan]Yahoo:[/cyan]      imap.mail.yahoo.com (port 993)\n")
        
        # Use existing values as defaults
        host = Prompt.ask("IMAP server", default=account.host or "")
        port = int(Prompt.ask("Port", default=str(account.port) if account.port else "993"))
        email = Prompt.ask("Email address", default=account.email or "")
        password = Prompt.ask("Password", password=True, default=account.password or "")
        
        account.type = "imap"
        account.host = host
        account.port = port
        account.email = email
        account.password = password
        account.use_ssl = True
        
        console.print("Testing connection...", end=" ")
        success, message = self._test_imap(host, port, email, password, True)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            return True
        else:
            console.print(f"[red]✗[/red] {message}")
            return False
    
    def _edit_email_account(self, idx: int) -> None:
        """Edit an existing email account."""
        account = self.config.integrations.email_accounts[idx]
        
        # Show current settings
        console.print(f"\n[bold]Email Account: {account.name}[/bold]")
        console.print(f"  [cyan]Type:[/cyan]    {account.type}")
        console.print(f"  [cyan]Status:[/cyan]  {'Enabled' if account.enabled else 'Disabled'}")
        if account.type == "imap":
            console.print(f"  [cyan]Server:[/cyan]  {account.host}:{account.port}")
            console.print(f"  [cyan]Email:[/cyan]   {account.email}")
        elif account.type == "exchange":
            console.print(f"  [cyan]Email:[/cyan]   {account.email}")
            console.print(f"  [cyan]Server:[/cyan]  {account.server}")
        elif account.type == "gmail":
            console.print(f"  [cyan]Credentials:[/cyan] {account.google_credentials_file}")
        console.print()
        
        action = Prompt.ask(
            "Action",
            choices=["rename", "reconfigure", "toggle", "delete", "back"],
            default="back"
        )
        
        if action == "rename":
            account.name = Prompt.ask("New name", default=account.name)
            console.print(f"[green]✓[/green] Renamed to '{account.name}'")
        elif action == "reconfigure":
            if account.type == "imap":
                self._configure_imap_email(account)
            elif account.type == "exchange":
                self._configure_exchange_email(account)
        elif action == "toggle":
            account.enabled = not account.enabled
            status = "enabled" if account.enabled else "disabled"
            console.print(f"[green]✓[/green] Account {status}")
        elif action == "delete":
            if Confirm.ask(f"Delete '{account.name}'?", default=False):
                self.config.integrations.email_accounts.pop(idx)
                console.print("[green]✓[/green] Account deleted")
    
    def _setup_gmail_imap(self) -> None:
        """Configure Gmail via IMAP (simpler than OAuth)."""
        console.print("\n[bold]Gmail Setup (IMAP)[/bold]")
        console.print("[dim]This is the easy way - just use your email and an app password.[/dim]\n")
        console.print("[bold]Steps to create an App Password:[/bold]")
        console.print("  1. Go to [cyan]https://myaccount.google.com/apppasswords[/cyan]")
        console.print("  2. Select 'Mail' and 'Other (Custom name)'")
        console.print("  3. Enter 'Koda' as the name")
        console.print("  4. Copy the 16-character password\n")
        console.print("[yellow]Note:[/yellow] 2-Step Verification must be enabled for App Passwords.\n")
        
        email = Prompt.ask("Gmail address")
        password = Prompt.ask("App password (16 characters, no spaces)", password=True)
        
        self.config.integrations.imap.enabled = True
        self.config.integrations.imap.host = "imap.gmail.com"
        self.config.integrations.imap.port = 993
        self.config.integrations.imap.username = email
        self.config.integrations.imap.password = password
        self.config.integrations.imap.use_ssl = True
        
        # Test connection
        console.print("Testing IMAP connection...", end=" ")
        success, message = self._test_imap("imap.gmail.com", 993, email, password, True)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("[dim]Make sure 2-Step Verification is on and you're using an App Password[/dim]")
    
    def _setup_icloud_imap(self) -> None:
        """Configure iCloud Mail via IMAP."""
        console.print("\n[bold]iCloud Mail Setup[/bold]")
        console.print("[dim]Connect to your Apple iCloud Mail.[/dim]\n")
        console.print("[bold]Steps to create an App-Specific Password:[/bold]")
        console.print("  1. Go to [cyan]https://appleid.apple.com/[/cyan]")
        console.print("  2. Sign in and go to 'App-Specific Passwords'")
        console.print("  3. Click '+' and create a password for 'Koda'")
        console.print("  4. Copy the generated password\n")
        
        email = Prompt.ask("Apple ID email")
        password = Prompt.ask("App-Specific Password", password=True)
        
        self.config.integrations.imap.enabled = True
        self.config.integrations.imap.host = "imap.mail.me.com"
        self.config.integrations.imap.port = 993
        self.config.integrations.imap.username = email
        self.config.integrations.imap.password = password
        self.config.integrations.imap.use_ssl = True
        
        # Test connection
        console.print("Testing IMAP connection...", end=" ")
        success, message = self._test_imap("imap.mail.me.com", 993, email, password, True)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")
            console.print("[dim]Make sure you're using an App-Specific Password, not your Apple ID password[/dim]")
    
    def _setup_imap(self) -> None:
        """Configure IMAP email."""
        console.print("\n[bold]IMAP Email Setup[/bold]")
        console.print("[dim]IMAP works with almost any email provider.[/dim]\n")
        console.print("Common IMAP servers:")
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
            # Restricted mode - ask for own number first
            console.print("\n[bold]Your WhatsApp Number[/bold]")
            console.print("[dim]This is the phone number linked to WhatsApp that you'll use to chat with Koda.[/dim]")
            console.print("[dim]Messages you send to yourself will also be processed.[/dim]\n")
            
            owner_phone = Prompt.ask(
                "Your phone number (e.g., +31612345678)",
                default=self.config.channels.whatsapp.owner_phone
            )
            self.config.channels.whatsapp.owner_phone = owner_phone
            
            owner_name = Prompt.ask(
                "Your name",
                default=self.config.channels.whatsapp.owner_name or self.config.assistant.user_name
            )
            self.config.channels.whatsapp.owner_name = owner_name
            
            # Build allow_from list - always include owner's phone
            console.print("\n[bold]Additional Allowed Numbers[/bold]")
            console.print("[dim]Your number is automatically allowed. Add others who can also chat with Koda.[/dim]")
            
            # Get existing allow_from without the owner phone
            existing = [x for x in self.config.channels.whatsapp.allow_from 
                       if x.replace("+", "").replace(" ", "") != owner_phone.replace("+", "").replace(" ", "")]
            
            additional = Prompt.ask(
                "Additional phone numbers (comma-separated, or leave empty)",
                default=", ".join(existing) if existing else ""
            )
            
            # Build final allow_from list
            allow_list = []
            if owner_phone:
                allow_list.append(owner_phone.strip())
            if additional:
                allow_list.extend([x.strip() for x in additional.split(",") if x.strip()])
            
            self.config.channels.whatsapp.allow_from = allow_list
            
            console.print(f"\n[dim]Allowed numbers: {', '.join(allow_list)}[/dim]")
        
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
    
    def _setup_icloud_contacts(self) -> None:
        """Configure iCloud contacts integration (macOS only)."""
        console.print("\n[bold]iCloud Contacts Setup[/bold]")
        console.print("[dim]Access your iCloud contacts for birthday wishes and name lookup.[/dim]\n")
        console.print("[bold]How it works:[/bold]")
        console.print("  • Koda uses your iCloud credentials to sync contacts")
        console.print("  • Contacts are cached locally for quick access")
        console.print("  • Birthday wishes can be sent automatically\n")
        console.print("[bold]Steps:[/bold]")
        console.print("  1. Go to [cyan]https://appleid.apple.com/[/cyan]")
        console.print("  2. Sign in and go to 'App-Specific Passwords'")
        console.print("  3. Create a password for 'Koda'\n")
        
        email = Prompt.ask("Apple ID email")
        password = Prompt.ask("App-Specific Password", password=True)
        
        self.config.integrations.icloud.enabled = True
        self.config.integrations.icloud.username = email
        self.config.integrations.icloud.password = password
        
        # Test connection
        console.print("Testing iCloud connection...", end=" ")
        try:
            from pyicloud import PyiCloudService
            api = PyiCloudService(email, password)
            if api.requires_2fa:
                console.print("[yellow]![/yellow] 2FA required - use App-Specific Password instead")
            else:
                console.print(f"[green]✓[/green] Connected to iCloud")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
            console.print("[dim]Make sure you're using an App-Specific Password[/dim]")
    
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
