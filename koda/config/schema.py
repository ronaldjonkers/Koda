"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AssistantConfig(BaseModel):
    """Assistant personalization configuration."""
    name: str = "Koda"  # The assistant's name
    user_name: str = ""  # How to address the user
    language: str = "en"  # Preferred language (en, nl, de, etc.)
    personality: str = "professional"  # professional, friendly, formal


class WhatsAppContactRule(BaseModel):
    """Auto-reply rule for a specific WhatsApp contact."""
    phone: str = ""  # Phone number (e.g., +31612345678)
    name: str = ""  # Contact name for reference
    instructions: str = ""  # Custom instructions for this contact
    auto_reply: bool = True  # Whether to auto-reply to this contact
    escalate_keywords: list[str] = Field(default_factory=lambda: ["afspraak", "appointment", "meeting", "urgent", "dringend"])


class WhatsAppConfig(BaseModel):
    """WhatsApp channel configuration."""
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    
    # Bot mode: respond to everyone, not just allowlist
    bot_mode: bool = False  # If True, respond to all incoming messages
    bot_phone: str = ""  # The bot's own WhatsApp number
    
    # Access control (only used when bot_mode=False)
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers
    
    # Owner configuration for escalation
    owner_phone: str = ""  # Owner's phone number for escalations
    owner_name: str = ""  # Owner's name
    
    # Per-contact rules with custom instructions
    contact_rules: list[WhatsAppContactRule] = Field(default_factory=list)
    
    # Default behavior for unknown contacts (when bot_mode=True)
    default_greeting: str = "Hallo! Ik ben {assistant_name}, de AI-assistent van {owner_name}. Hoe kan ik je helpen?"
    default_instructions: str = "Be helpful and professional. If someone wants to schedule an appointment or needs something urgent that requires the owner, escalate to the owner."
    
    # Escalation settings
    escalate_to_owner: bool = True  # Notify owner for important requests
    escalation_keywords: list[str] = Field(default_factory=lambda: [
        "afspraak", "appointment", "meeting", "urgent", "dringend", 
        "bellen", "call", "terugbellen", "callback"
    ])


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class AgentDefaults(BaseModel):
    """Default agent configuration."""
    workspace: str = "~/.koda/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent configuration."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""
    api_key: str = ""
    api_base: str | None = None


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)


class GatewayConfig(BaseModel):
    """Gateway/server configuration.
    
    SECURITY: By default, the gateway only listens on localhost (127.0.0.1).
    To expose externally, use 'koda setup proxy' to configure a secure reverse proxy.
    """
    host: str = "127.0.0.1"  # Localhost only for security
    port: int = 18790


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""
    api_key: str = ""  # Brave Search API key
    max_results: int = 5


# =============================================================================
# Named Account Models - Allow multiple accounts with custom names
# =============================================================================

class CalendarAccount(BaseModel):
    """A named calendar account that can be Google, Exchange, or CalDAV."""
    name: str = ""  # User-friendly name like "Werk", "Privé", "Familie"
    type: str = ""  # "google", "exchange", "caldav"
    enabled: bool = True
    
    # Google-specific
    credentials_file: str = "~/.koda/google_credentials.json"
    token_file: str = "~/.koda/google_token.json"
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])
    
    # Exchange-specific
    email: str = ""
    password: str = ""
    server: str = ""
    calendar_name: str = "Calendar"
    version: str = "auto"  # auto, 2013, 2016, 2019, o365
    auth_type: str = "basic"  # basic, ntlm, oauth2
    use_autodiscover: bool = True
    
    # CalDAV-specific
    url: str = ""
    username: str = ""
    # password is shared with Exchange
    calendar_path: str = ""


class EmailAccount(BaseModel):
    """A named email account that can be Gmail, Exchange, or IMAP."""
    name: str = ""  # User-friendly name like "Werk Mail", "Privé Mail"
    type: str = ""  # "gmail", "exchange", "imap"
    enabled: bool = True
    
    # Gmail uses same credentials as Google Calendar
    google_credentials_file: str = "~/.koda/google_credentials.json"
    google_token_file: str = "~/.koda/google_token.json"
    
    # Exchange-specific (shares with calendar)
    email: str = ""
    password: str = ""
    server: str = ""
    
    # IMAP-specific
    host: str = ""
    port: int = 993
    username: str = ""
    # password is shared
    use_ssl: bool = True
    folder: str = "INBOX"


# =============================================================================
# Legacy configs (kept for backward compatibility)
# =============================================================================

class GoogleConfig(BaseModel):
    """Google integration configuration (Calendar, Gmail)."""
    enabled: bool = False
    credentials_file: str = "~/.koda/google_credentials.json"
    token_file: str = "~/.koda/google_token.json"
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])


class ExchangeConfig(BaseModel):
    """Microsoft Exchange configuration (Calendar, Email).
    
    Compatible with Exchange 2013, 2016, 2019, and Office 365.
    Uses EWS (Exchange Web Services) protocol.
    """
    enabled: bool = False
    email: str = ""
    password: str = ""
    server: str = ""  # e.g., "outlook.office365.com" or "mail.company.com"
    calendar_name: str = "Calendar"
    version: str = "auto"  # auto, 2013, 2016, 2019, o365
    auth_type: str = "basic"  # basic, ntlm, oauth2
    use_autodiscover: bool = True


class CalDAVConfig(BaseModel):
    """CalDAV calendar configuration for generic calendar servers.
    
    Works with: Nextcloud, ownCloud, Radicale, Baikal, macOS Server, etc.
    """
    enabled: bool = False
    url: str = ""  # Full CalDAV URL, e.g., https://nextcloud.example.com/remote.php/dav
    username: str = ""
    password: str = ""
    calendar_path: str = ""  # Calendar path, e.g., /calendars/user/personal/


class IMAPConfig(BaseModel):
    """IMAP email configuration for generic mail servers.
    
    Works with any IMAP-compatible mail server.
    """
    enabled: bool = False
    host: str = ""  # IMAP server, e.g., imap.gmail.com
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    folder: str = "INBOX"  # Default folder to monitor
    

class SMTPConfig(BaseModel):
    """SMTP configuration for the bot's own email sending."""
    enabled: bool = False
    host: str = ""  # SMTP server, e.g., smtp.gmail.com
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""  # The bot's email address
    from_name: str = ""  # Display name, e.g., "Koda Assistant"
    use_tls: bool = True
    use_ssl: bool = False


class ICloudConfig(BaseModel):
    """iCloud configuration (Contacts)."""
    enabled: bool = False
    apple_id: str = ""
    password: str = ""  # App-specific password recommended


class WhatsAppAutoReplyConfig(BaseModel):
    """WhatsApp auto-reply configuration for specific contacts."""
    enabled: bool = False
    contacts: list[str] = Field(default_factory=list)  # Phone numbers to auto-reply
    greeting: str = "Hallo! Ik ben de AI-assistent van {owner}. Hoe kan ik je helpen?"
    owner_name: str = ""


class BirthdayConfig(BaseModel):
    """Birthday reminder configuration."""
    enabled: bool = False
    reminder_days_before: int = 1
    send_via: str = "whatsapp"  # whatsapp, telegram, or email
    default_message_template: str = "Gefeliciteerd met je verjaardag, {name}! 🎂🎉"


class EmailConfig(BaseModel):
    """Email sender configuration for reminders."""
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""  # App-specific password
    from_email: str = ""
    use_tls: bool = True


class WebhookConfig(BaseModel):
    """Webhook API server configuration.
    
    SECURITY: By default, only listens on localhost (127.0.0.1).
    Use 'koda setup proxy' to expose externally via reverse proxy.
    """
    enabled: bool = False
    host: str = "127.0.0.1"  # Localhost only for security
    port: int = 8080
    api_key: str = ""  # Optional API key for authentication


class ReminderConfig(BaseModel):
    """Reminder service configuration."""
    enabled: bool = True
    email: EmailConfig = Field(default_factory=EmailConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)


class IntegrationsConfig(BaseModel):
    """External integrations configuration."""
    # Named accounts - unlimited, user-defined names
    calendar_accounts: list[CalendarAccount] = Field(default_factory=list)
    email_accounts: list[EmailAccount] = Field(default_factory=list)
    
    # Legacy single-account configs (for backward compatibility)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    caldav: CalDAVConfig = Field(default_factory=CalDAVConfig)
    imap: IMAPConfig = Field(default_factory=IMAPConfig)
    bot_email: SMTPConfig = Field(default_factory=SMTPConfig)
    icloud: ICloudConfig = Field(default_factory=ICloudConfig)
    whatsapp_auto_reply: WhatsAppAutoReplyConfig = Field(default_factory=WhatsAppAutoReplyConfig)
    birthday: BirthdayConfig = Field(default_factory=BirthdayConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    
    def get_all_calendars(self) -> list[CalendarAccount]:
        """Get all calendar accounts (named + legacy converted to named)."""
        calendars = list(self.calendar_accounts)
        
        # Convert legacy configs to named accounts
        if self.google.enabled:
            calendars.append(CalendarAccount(
                name="Google",
                type="google",
                enabled=True,
                credentials_file=self.google.credentials_file,
                token_file=self.google.token_file,
                calendar_ids=self.google.calendar_ids
            ))
        
        if self.exchange.enabled:
            calendars.append(CalendarAccount(
                name="Exchange",
                type="exchange",
                enabled=True,
                email=self.exchange.email,
                password=self.exchange.password,
                server=self.exchange.server,
                calendar_name=self.exchange.calendar_name,
                version=self.exchange.version,
                auth_type=self.exchange.auth_type,
                use_autodiscover=self.exchange.use_autodiscover
            ))
        
        if self.caldav.enabled:
            calendars.append(CalendarAccount(
                name="CalDAV",
                type="caldav",
                enabled=True,
                url=self.caldav.url,
                username=self.caldav.username,
                password=self.caldav.password,
                calendar_path=self.caldav.calendar_path
            ))
        
        return calendars
    
    def get_all_email_accounts(self) -> list[EmailAccount]:
        """Get all email accounts (named + legacy converted to named)."""
        emails = list(self.email_accounts)
        
        # Convert legacy configs to named accounts
        if self.google.enabled:
            emails.append(EmailAccount(
                name="Gmail",
                type="gmail",
                enabled=True,
                google_credentials_file=self.google.credentials_file,
                google_token_file=self.google.token_file
            ))
        
        if self.exchange.enabled:
            emails.append(EmailAccount(
                name="Exchange",
                type="exchange",
                enabled=True,
                email=self.exchange.email,
                password=self.exchange.password,
                server=self.exchange.server
            ))
        
        if self.imap.enabled:
            emails.append(EmailAccount(
                name="IMAP",
                type="imap",
                enabled=True,
                host=self.imap.host,
                port=self.imap.port,
                username=self.imap.username,
                password=self.imap.password,
                use_ssl=self.imap.use_ssl,
                folder=self.imap.folder
            ))
        
        return emails


class WebToolsConfig(BaseModel):
    """Web tools configuration."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)


class Config(BaseSettings):
    """Root configuration for the assistant."""
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    
    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()
    
    def get_api_key(self) -> str | None:
        """Get API key in priority order: OpenRouter > Anthropic > OpenAI > Gemini > Zhipu > Groq > vLLM."""
        return (
            self.providers.openrouter.api_key or
            self.providers.anthropic.api_key or
            self.providers.openai.api_key or
            self.providers.gemini.api_key or
            self.providers.zhipu.api_key or
            self.providers.groq.api_key or
            self.providers.vllm.api_key or
            None
        )
    
    def get_api_base(self) -> str | None:
        """Get API base URL if using OpenRouter, Zhipu or vLLM."""
        if self.providers.openrouter.api_key:
            return self.providers.openrouter.api_base or "https://openrouter.ai/api/v1"
        if self.providers.zhipu.api_key:
            return self.providers.zhipu.api_base
        if self.providers.vllm.api_base:
            return self.providers.vllm.api_base
        return None
    
    class Config:
        env_prefix = "KODA_"
        env_nested_delimiter = "__"
