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
    timezone: str = "Europe/Amsterdam"  # IANA timezone (e.g., Europe/Amsterdam, America/New_York)


class WhatsAppContactRule(BaseModel):
    """Auto-reply rule for a specific WhatsApp contact."""
    phone: str = ""  # Phone number (e.g., +31612345678)
    name: str = ""  # Contact name for reference
    instructions: str = ""  # Custom instructions for this contact
    auto_reply: bool = True  # Whether to auto-reply to this contact
    escalate_keywords: list[str] = Field(default_factory=lambda: ["appointment", "meeting", "urgent", "dringend", "afspraak"])


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
    default_greeting: str = "Hello! I'm {assistant_name}, the AI assistant of {owner_name}. How can I help you?"
    default_instructions: str = "Be helpful and professional. If someone wants to schedule an appointment or needs something urgent that requires the owner, escalate to the owner."
    
    # Escalation settings
    escalate_to_owner: bool = True  # Notify owner for important requests
    escalation_keywords: list[str] = Field(default_factory=lambda: [
        "appointment", "meeting", "urgent", "call", "callback",
        "afspraak", "dringend", "bellen", "terugbellen"
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
# Unified Account Model - One account, multiple capabilities
# =============================================================================

class Account(BaseModel):
    """A unified account that can provide email, calendar, and/or contacts.
    
    This replaces separate CalendarAccount and EmailAccount models.
    An Exchange account is stored ONCE and provides all its capabilities.
    
    Types:
    - exchange: Email + Calendar + Contacts
    - google: Email (Gmail) + Calendar
    - imap: Email only
    - caldav: Calendar only
    - icloud: Contacts only
    """
    name: str = ""  # User-friendly name like "Werk", "Privé"
    type: str = ""  # "exchange", "google", "imap", "caldav", "icloud"
    enabled: bool = True
    
    # What this account provides
    capabilities: list[str] = Field(default_factory=list)  # ["email", "calendar", "contacts"]
    
    # Common fields
    email: str = ""
    username: str = ""  # Optional: if different from email (e.g., DOMAIN\\user)
    password: str = ""
    
    # Exchange-specific
    server: str = ""  # e.g., "exchange.company.com" or "outlook.office365.com"
    use_autodiscover: bool = False  # Default to False - use specified server
    calendar_name: str = "Calendar"
    version: str = "auto"  # auto, 2013, 2016, 2019, o365
    auth_type: str = "basic"  # basic, ntlm, oauth2
    
    # Google-specific
    credentials_file: str = "~/.koda/google_credentials.json"
    token_file: str = "~/.koda/google_token.json"
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])
    
    # IMAP-specific
    host: str = ""  # IMAP server hostname
    port: int = 993
    use_ssl: bool = True
    folder: str = "INBOX"
    
    # CalDAV-specific
    url: str = ""  # CalDAV URL
    calendar_path: str = ""
    
    # iCloud-specific
    apple_id: str = ""
    
    def has_capability(self, cap: str) -> bool:
        """Check if this account has a specific capability."""
        return cap in self.capabilities
    
    @property
    def has_email(self) -> bool:
        return "email" in self.capabilities
    
    @property
    def has_calendar(self) -> bool:
        return "calendar" in self.capabilities
    
    @property
    def has_contacts(self) -> bool:
        return "contacts" in self.capabilities


# Legacy aliases for backward compatibility
CalendarAccount = Account
EmailAccount = Account


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
    username: str = ""  # Optional: if different from email (e.g., DOMAIN\\user)
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


class LinkedInConfig(BaseModel):
    """LinkedIn integration configuration.
    
    Allows the assistant to:
    - Check and reply to messages
    - Manage connection requests
    - View and interact with posts
    - Create posts and search for people
    """
    enabled: bool = False
    email: str = ""  # LinkedIn login email
    password: str = ""  # LinkedIn password


class WhatsAppAutoReplyConfig(BaseModel):
    """WhatsApp auto-reply configuration for specific contacts."""
    enabled: bool = False
    contacts: list[str] = Field(default_factory=list)  # Phone numbers to auto-reply
    greeting: str = "Hello! I'm the AI assistant of {owner}. How can I help you?"
    owner_name: str = ""


class BirthdayConfig(BaseModel):
    """Birthday reminder configuration."""
    enabled: bool = False
    reminder_days_before: int = 1
    send_via: str = "whatsapp"  # whatsapp, telegram, or email
    default_message_template: str = "Happy birthday, {name}! 🎂🎉"


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
    # Unified accounts list - one account provides multiple capabilities
    accounts: list[Account] = Field(default_factory=list)
    
    # Legacy lists (kept for migration, will be merged into accounts)
    calendar_accounts: list[Account] = Field(default_factory=list)
    email_accounts: list[Account] = Field(default_factory=list)
    
    # Legacy single-account configs (for backward compatibility)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    caldav: CalDAVConfig = Field(default_factory=CalDAVConfig)
    imap: IMAPConfig = Field(default_factory=IMAPConfig)
    bot_email: SMTPConfig = Field(default_factory=SMTPConfig)
    icloud: ICloudConfig = Field(default_factory=ICloudConfig)
    linkedin: LinkedInConfig = Field(default_factory=LinkedInConfig)
    whatsapp_auto_reply: WhatsAppAutoReplyConfig = Field(default_factory=WhatsAppAutoReplyConfig)
    birthday: BirthdayConfig = Field(default_factory=BirthdayConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    
    def get_all_accounts(self) -> list[Account]:
        """Get all unified accounts (new + legacy merged + old configs converted)."""
        all_accounts: dict[str, Account] = {}
        
        # 0. Auto-detect Google Workspace (OAuth-based, not in config)
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            if status.get("authorized"):
                all_accounts["Google Workspace"] = Account(
                    name="Google Workspace",
                    type="google",
                    enabled=True,
                    email=status.get("email", ""),
                    capabilities=["email", "calendar"],
                )
        except Exception:
            pass
        
        # 1. New unified accounts list
        for acc in self.accounts:
            if acc.name and acc.enabled:
                all_accounts[acc.name] = acc
        
        # 2. Migrate legacy calendar_accounts (add calendar capability)
        for acc in self.calendar_accounts:
            if isinstance(acc, dict):
                name = acc.get("name", "")
                if name in all_accounts:
                    # Merge: add calendar capability
                    if "calendar" not in all_accounts[name].capabilities:
                        all_accounts[name].capabilities.append("calendar")
                else:
                    # Create new with calendar capability
                    caps = acc.get("capabilities", [])
                    if "calendar" not in caps:
                        caps = caps + ["calendar"]
                    all_accounts[name] = Account(**{**acc, "capabilities": caps})
            elif acc.name:
                if acc.name in all_accounts:
                    if "calendar" not in all_accounts[acc.name].capabilities:
                        all_accounts[acc.name].capabilities.append("calendar")
                else:
                    if "calendar" not in acc.capabilities:
                        acc.capabilities.append("calendar")
                    all_accounts[acc.name] = acc
        
        # 3. Migrate legacy email_accounts (add email capability)
        for acc in self.email_accounts:
            if isinstance(acc, dict):
                name = acc.get("name", "")
                if name in all_accounts:
                    if "email" not in all_accounts[name].capabilities:
                        all_accounts[name].capabilities.append("email")
                else:
                    caps = acc.get("capabilities", [])
                    if "email" not in caps:
                        caps = caps + ["email"]
                    all_accounts[name] = Account(**{**acc, "capabilities": caps})
            elif acc.name:
                if acc.name in all_accounts:
                    if "email" not in all_accounts[acc.name].capabilities:
                        all_accounts[acc.name].capabilities.append("email")
                else:
                    if "email" not in acc.capabilities:
                        acc.capabilities.append("email")
                    all_accounts[acc.name] = acc
        
        # 4. Convert old legacy single configs
        if self.google.enabled:
            if "Google" not in all_accounts:
                all_accounts["Google"] = Account(
                    name="Google",
                    type="google",
                    enabled=True,
                    capabilities=["email", "calendar"],
                    credentials_file=self.google.credentials_file,
                    token_file=self.google.token_file,
                    calendar_ids=self.google.calendar_ids
                )
        
        if self.exchange.enabled:
            if "Exchange" not in all_accounts:
                all_accounts["Exchange"] = Account(
                    name="Exchange",
                    type="exchange",
                    enabled=True,
                    capabilities=["email", "calendar", "contacts"],
                    email=self.exchange.email,
                    username=self.exchange.username,
                    password=self.exchange.password,
                    server=self.exchange.server,
                    calendar_name=self.exchange.calendar_name,
                    version=self.exchange.version,
                    auth_type=self.exchange.auth_type,
                    use_autodiscover=self.exchange.use_autodiscover
                )
        
        if self.caldav.enabled:
            if "CalDAV" not in all_accounts:
                all_accounts["CalDAV"] = Account(
                    name="CalDAV",
                    type="caldav",
                    enabled=True,
                    capabilities=["calendar"],
                    url=self.caldav.url,
                    username=self.caldav.username,
                    password=self.caldav.password,
                    calendar_path=self.caldav.calendar_path
                )
        
        if self.imap.enabled:
            if "IMAP" not in all_accounts:
                all_accounts["IMAP"] = Account(
                    name="IMAP",
                    type="imap",
                    enabled=True,
                    capabilities=["email"],
                    host=self.imap.host,
                    port=self.imap.port,
                    username=self.imap.username,
                    password=self.imap.password,
                    use_ssl=self.imap.use_ssl,
                    folder=self.imap.folder
                )
        
        if self.icloud.enabled:
            if "iCloud" not in all_accounts:
                all_accounts["iCloud"] = Account(
                    name="iCloud",
                    type="icloud",
                    enabled=True,
                    capabilities=["contacts"],
                    apple_id=self.icloud.apple_id,
                    password=self.icloud.password
                )
        
        return list(all_accounts.values())
    
    def get_accounts_with_capability(self, capability: str) -> list[Account]:
        """Get all accounts that have a specific capability."""
        return [acc for acc in self.get_all_accounts() if capability in acc.capabilities]
    
    def get_all_calendars(self) -> list[Account]:
        """Get all accounts with calendar capability."""
        return self.get_accounts_with_capability("calendar")
    
    def get_all_email_accounts(self) -> list[Account]:
        """Get all accounts with email capability."""
        return self.get_accounts_with_capability("email")
    
    def get_all_contacts_accounts(self) -> list[Account]:
        """Get all accounts with contacts capability."""
        return self.get_accounts_with_capability("contacts")
    
    def get_account_by_name(self, name: str) -> Account | None:
        """Find an account by name."""
        for acc in self.get_all_accounts():
            if acc.name == name:
                return acc
        return None


class WebToolsConfig(BaseModel):
    """Web tools configuration."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ImageProviderConfig(BaseModel):
    """Configuration for a single image provider."""
    enabled: bool = False
    api_key: str = ""
    default_model: str = ""


class ImageGenerationConfig(BaseModel):
    """Image generation configuration with multi-provider support."""
    pollinations: ImageProviderConfig = Field(default_factory=lambda: ImageProviderConfig(enabled=True))
    openrouter: ImageProviderConfig = Field(default_factory=ImageProviderConfig)
    stability_ai: ImageProviderConfig = Field(default_factory=ImageProviderConfig)
    replicate: ImageProviderConfig = Field(default_factory=ImageProviderConfig)
    gemini: ImageProviderConfig = Field(default_factory=ImageProviderConfig)  # Google Gemini Imagen
    default_provider: str = "pollinations"
    save_images: bool = True
    image_directory: str = "images"


class PublicEventsConfig(BaseModel):
    """Public events configuration."""
    enabled: bool = True
    football_api_key: str = ""  # Football-Data.org API key (optional)
    auto_import_f1: bool = True
    reminder_days_ahead: int = 3
    categories: list[str] = Field(default_factory=lambda: ["sports", "music", "entertainment"])


class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    image_generation: ImageGenerationConfig = Field(default_factory=ImageGenerationConfig)
    public_events: PublicEventsConfig = Field(default_factory=PublicEventsConfig)


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
