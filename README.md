<div align="center">
  <img src="koda_logo.png" alt="Koda" width="500">
  <h1>Koda: Elite AI Executive Assistant</h1>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/version-0.1.0--alpha-orange" alt="Version">
  </p>
</div>

🐕 **Koda** is an elite AI Assistant designed to function as a high-level Executive Secretary while simultaneously acting as a full-stack Dev, Marketing, and Data team. Koda is a Single Point of Execution and an autonomous agent capable of managing your professional life and technical infrastructure.

## ✨ Key Features

### Executive Management
- 📅 **Calendar Management** - Google Calendar & Microsoft Exchange integration
- 📧 **Email Assistant** - Read, search, and send emails via Gmail or Exchange
- 👥 **Contact Intelligence** - Access iCloud/macOS contacts with birthday tracking
- 🔔 **Active Reminders** - Webhook and email-based reminder system

### Technical Powerhouse
- 🛠️ **Script Automation** - Generate and execute Python, Bash, and Node.js scripts
- 🧠 **Vector Memory** - Persistent semantic memory with ChromaDB embeddings
- 🔍 **Web Search** - Multiple options: Brave Search (paid) or DuckDuckGo (free)
- 📖 **Wikipedia** - Direct Wikipedia article access (free, multi-language)
- 🌐 **Web Fetch** - Extract content from any URL using Trafilatura
- 💻 **Shell Execution** - Direct system command execution

### Communication Hub
- � **Messaging Integration** - WhatsApp & Telegram bot capabilities
- 🌐 **Webhook API** - REST API for external integrations
- 🎂 **Birthday Wishes** - Automatic personalized birthday messages

### Task Automation
- ⏰ **Cron Scheduler** - Native cronjob system for recurring tasks
- 📝 **Script Generation** - Autonomous script creation and execution
- 🔄 **Subagent Spawning** - Delegate tasks to specialized subagents

## 📦 Prerequisites

- **Python 3.11+** - Required for the main application
- **Node.js 20+** - Required for WhatsApp integration (optional)

### macOS

```bash
# Install Python 3.12 via Homebrew
brew install python@3.12

# Install Node.js (optional, for WhatsApp)
brew install node
```

### Linux (Debian/Ubuntu)

```bash
# Install Python 3.12
sudo apt update
sudo apt install python3.12 python3.12-venv

# Install Node.js 20+ (optional, for WhatsApp)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs
```

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/koda.git
cd koda

# Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Koda
pip install -e .

# (Optional) Build the WhatsApp bridge
cd bridge
npm install
npm run build
cd ..
```

### Alternative: Install with uv (faster)

```bash
# Install uv first: https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

## 🚀 Quick Start

> **Note:** Make sure the virtual environment is activated before running koda commands:
> `source .venv/bin/activate`

**1. Run the Setup Wizard**

```bash
koda onboard
```

The interactive wizard will guide you through:
- **Assistant personalization** - Set the assistant's name and how it addresses you
- **LLM provider** - Configure your API key (OpenRouter, Anthropic, OpenAI, etc.)
- **Calendar** - Google, Exchange (2013/2016/2019/O365), or CalDAV
- **Email** - Gmail, Exchange, or IMAP
- **Messaging** - Telegram and WhatsApp
- **Bot email** - Configure the assistant's own email address

Each configuration is **tested automatically** - if something fails, you can adjust immediately.

**2. Or Configure Later**

```bash
# Configure specific sections
koda config assistant
koda config provider
koda config calendar
koda config email

# Show current configuration
koda config --show

# Test all connections
koda config --test
```

**3. Chat with the Assistant**

```bash
koda agent -m "What's on my calendar today?"
```

## 📅 Calendar Integration

### Google Calendar

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download and save as `~/.koda/google_credentials.json`

### Microsoft Exchange (2013/2016/2019/O365)

```bash
koda config exchange
```

Or configure manually:
```json
{
  "integrations": {
    "exchange": {
      "enabled": true,
      "email": "you@company.com",
      "password": "app-password",
      "server": "mail.company.com",
      "version": "2016",
      "auth_type": "basic"
    }
  }
}
```

Supported versions: `auto`, `2013`, `2016`, `2019`, `o365`

### CalDAV (Nextcloud, ownCloud, Radicale, etc.)

```bash
koda config caldav
```

Works with any CalDAV-compatible server:
```json
{
  "integrations": {
    "caldav": {
      "enabled": true,
      "url": "https://nextcloud.example.com/remote.php/dav",
      "username": "your-username",
      "password": "your-password"
    }
  }
}
```

## 📧 Email Integration

The assistant can read, search, and send emails through multiple providers:

### Gmail
Uses the same OAuth credentials as Google Calendar.

### Exchange
Uses the same configuration as Exchange Calendar.

### IMAP (Any Mail Server)

```bash
koda config imap
```

Works with any IMAP server (Gmail, Outlook, Yahoo, ProtonMail Bridge, etc.):
```json
{
  "integrations": {
    "imap": {
      "enabled": true,
      "host": "imap.gmail.com",
      "port": 993,
      "username": "your-email@gmail.com",
      "password": "app-specific-password",
      "use_ssl": true
    }
  }
}
```

### Bot's Own Email Address

Give the assistant its own email for sending messages:

```bash
koda config bot-email
```

```json
{
  "integrations": {
    "bot_email": {
      "enabled": true,
      "host": "smtp.gmail.com",
      "port": 587,
      "username": "assistant@yourdomain.com",
      "password": "app-password",
      "from_email": "assistant@yourdomain.com",
      "from_name": "Koda Assistant"
    }
  }
}
```

Example usage:

```bash
koda agent -m "Show me unread emails from today"
koda agent -m "Send an email to john@example.com about the meeting"
```

## 💬 Messaging Platforms

### Telegram

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

### WhatsApp

```bash
# Configure WhatsApp
koda config whatsapp

# Link your WhatsApp
koda channels login

# Start the gateway
koda gateway
```

**Bot Mode** - Give the assistant its own WhatsApp number to respond to everyone:

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "bot_mode": true,
      "bot_phone": "+31612345678",
      "owner_phone": "+31687654321",
      "owner_name": "Jan",
      "escalate_to_owner": true,
      "escalation_keywords": ["afspraak", "appointment", "urgent"],
      "default_greeting": "Hallo! Ik ben {assistant_name}, de AI-assistent van {owner_name}."
    }
  }
}
```

**Per-Contact Rules** - Custom instructions for specific contacts:

```json
{
  "channels": {
    "whatsapp": {
      "contact_rules": [
        {
          "phone": "+31611111111",
          "name": "Klant A",
          "instructions": "This is a VIP customer. Be extra helpful.",
          "auto_reply": true
        }
      ]
    }
  }
}
```

**Features:**
- **Bot Mode**: Respond to all incoming messages
- **Per-Contact Rules**: Custom instructions per phone number
- **Owner Escalation**: Forward appointment requests to the owner
- **Automatic Greeting**: Customizable welcome message

## 👥 Contacts & Birthdays

Koda accesses your macOS/iCloud contacts for:

- Contact lookup by name, phone, or email
- Birthday reminders and automatic wishes
- Personalized messaging based on contact info

```bash
# Set up daily birthday check
koda cron add --name "birthdays" \
  --message "Check for birthdays today and send wishes" \
  --cron "0 8 * * *"
```

## 🧠 Vector Memory System

Koda uses ChromaDB for persistent semantic memory with embeddings:

```bash
# The agent automatically stores and retrieves memories
koda agent -m "Remember that I prefer morning meetings"
koda agent -m "What are my preferences?"
```

Memory categories:
- **facts** - Important information about users and context
- **preferences** - Learned user preferences
- **context** - Conversation and task context
- **tasks** - Ongoing and completed tasks

## 🔔 Reminder System

Active reminders via webhook, email, or messaging channels:

```bash
# Via agent
koda agent -m "Remind me to call John tomorrow at 9am via email"

# Via CLI (coming soon)
# Or via webhook API
curl -X POST http://localhost:8080/webhook/remind \
  -H "Content-Type: application/json" \
  -d '{"title": "Call John", "message": "Follow up on project", "trigger_at": "2024-12-25T09:00:00", "channel": "email", "recipient": "me@example.com"}'
```

## 🌐 Webhook API

External integrations via REST API:

```bash
# Trigger agent with webhook
curl -X POST http://localhost:8080/webhook/trigger \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"event": "task", "message": "Process new data file"}'

# Send message to agent
curl -X POST http://localhost:8080/webhook/agent \
  -d '{"message": "What is on my calendar today?"}'
```

Enable in config:
```json
{
  "integrations": {
    "reminder": {
      "webhook": {
        "enabled": true,
        "port": 8080,
        "api_key": "your-secret-key"
      }
    }
  }
}
```

## 🛠️ Script Automation

Generate and execute scripts autonomously:

```bash
# Ask Koda to create and run scripts
koda agent -m "Write a Python script to analyze my CSV file"
koda agent -m "Create a bash script to backup my documents"
```

Supported languages:
- **Python** - Data processing, API calls, automation
- **Bash** - System operations, file management
- **Node.js** - Web scraping, async operations

## ⚙️ Full Configuration

```json
{
  "providers": {
    "openrouter": { "apiKey": "sk-or-v1-xxx" }
  },
  "agents": {
    "defaults": { "model": "anthropic/claude-sonnet-4-20250514" }
  },
  "channels": {
    "telegram": { "enabled": true, "token": "...", "allowFrom": ["..."] },
    "whatsapp": { "enabled": true, "allowFrom": ["+31..."] }
  },
  "integrations": {
    "google": { "enabled": true },
    "exchange": { "enabled": false },
    "icloud": { "enabled": false },
    "birthday": {
      "enabled": true,
      "send_via": "whatsapp",
      "default_message_template": "Happy birthday, {name}! 🎂"
    },
    "reminder": {
      "enabled": true,
      "email": {
        "enabled": true,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "your-email@gmail.com",
        "password": "app-specific-password",
        "from_email": "your-email@gmail.com"
      },
      "webhook": {
        "enabled": true,
        "port": 8080,
        "api_key": "your-secret-key"
      }
    }
  }
}
```

## 🖥️ CLI Reference

| Command | Description |
|---------|-------------|
| `koda onboard` | Interactive setup wizard |
| `koda onboard --quick` | Quick setup with defaults |
| `koda config` | List configurable sections |
| `koda config <section>` | Configure a specific feature |
| `koda config --show` | Show current configuration |
| `koda config --test` | Test all connections |
| `koda agent -m "..."` | Chat with assistant |
| `koda agent` | Interactive chat mode |
| `koda gateway` | Start messaging gateway |
| `koda status` | Show status |
| `koda channels login` | Link WhatsApp |
| `koda cron add` | Add scheduled task |
| `koda cron list` | List scheduled tasks |
| `koda setup-proxy` | Generate reverse proxy config for external access |

**Config sections:** `assistant`, `provider`, `calendar`, `email`, `bot-email`, `channels`, `webhook`, `exchange`, `caldav`, `imap`, `google`, `telegram`, `whatsapp`, `whatsapp-contacts`

## 🐳 Docker

```bash
# Build
docker build -t koda .

# Initialize
docker run -v ~/.koda:/root/.koda --rm koda onboard

# Run gateway
docker run -v ~/.koda:/root/.koda -p 18790:18790 koda gateway
```

## 📁 Project Structure

```
koda/
├── core/                   # Core engine and orchestration
│   ├── loop.py             # Main agent processing loop
│   ├── context.py          # Context management
│   ├── memory.py           # File-based memory
│   ├── vector_memory.py    # Vector memory with ChromaDB
│   ├── skills.py           # Skills loader
│   ├── subagent.py         # Subagent management
│   └── tools/              # Agent tools
│       ├── calendar.py     # Google & Exchange calendar
│       ├── email.py        # Gmail & Exchange email
│       ├── contacts.py     # iCloud contacts
│       ├── memory.py       # Vector memory operations
│       ├── reminder.py     # Reminder management
│       ├── script.py       # Script generation/execution
│       ├── shell.py        # Shell command execution
│       ├── web.py          # Web search & fetch
│       └── filesystem.py   # File operations
├── services/               # External service integrations
│   ├── telegram.py         # Telegram channel
│   ├── whatsapp.py         # WhatsApp channel
│   ├── reminder.py         # Reminder service
│   └── webhook_api.py      # FastAPI webhook server
├── integrations/           # Third-party integrations
│   ├── google_calendar.py  # Google Calendar API
│   ├── google_gmail.py     # Gmail API
│   ├── exchange_client.py  # Microsoft Exchange
│   ├── icloud_contacts.py  # iCloud/macOS contacts
│   └── birthday_service.py # Birthday automation
├── scheduler/              # Cron & scheduled tasks
│   ├── service.py          # Cron service
│   └── types.py            # Job definitions
├── skills/                 # Modular skill definitions
├── config/                 # Configuration schema
└── cli/                    # Command-line interface
```

## 🔐 Security

### Localhost by Default
**Koda only listens on localhost (127.0.0.1) by default** - it is not accessible from external networks.

### External Access (Optional)
If you need external access, use the proxy setup command:

```bash
# Generate nginx reverse proxy config
koda setup-proxy --server nginx --domain your-domain.com

# Or use Caddy (automatic SSL)
koda setup-proxy --server caddy --domain your-domain.com
```

This generates a secure reverse proxy configuration with:
- **HTTPS/SSL** - Never expose over plain HTTP
- **Security headers** - X-Frame-Options, XSS protection, etc.
- **WebSocket support** - For real-time messaging

### Best Practices
- Use app-specific passwords for Exchange, Gmail, and iCloud
- Store credentials securely in `~/.koda/`
- Limit `allowFrom` to trusted contacts only
- Never commit config.json to version control
- Use strong API keys for webhook endpoints
- Scripts execute in workspace sandbox
- Consider VPN or IP whitelisting for external access

## 🔧 Available Tools

Koda comes with a comprehensive set of tools:

| Tool | Description |
|------|-------------|
| `google_calendar` | Google Calendar read/write |
| `exchange_calendar` | Microsoft Exchange calendar |
| `gmail` | Gmail read/send |
| `exchange_email` | Exchange email |
| `contacts` | iCloud/macOS contacts |
| `memory` | Vector-based semantic memory |
| `reminder` | Schedule reminders |
| `script` | Generate/execute scripts |
| `exec` | Shell command execution |
| `web_search` | Brave Search API (requires API key) |
| `ddg_search` | DuckDuckGo search (free, no API key) |
| `wikipedia` | Wikipedia articles (free, multi-language) |
| `web_fetch` | Fetch & extract web content (trafilatura) |
| `read_file` | Read files |
| `write_file` | Write files |
| `edit_file` | Edit files |
| `list_dir` | List directories |
| `message` | Send messages via channels |
| `spawn` | Spawn subagents |

## 📝 License

MIT License - see LICENSE file

---

<p align="center">
  <em>Koda - Your elite AI executive assistant 🐕</em>
</p>
