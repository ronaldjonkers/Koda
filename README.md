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

### One-Line Install (Recommended)

The easiest way to install Koda with all dependencies:

```bash
git clone https://github.com/ronaldjonkers/Koda.git
cd Koda
./install.sh
```

The install script automatically:
- Detects your OS (macOS / Linux distros)
- Installs Homebrew (macOS) if not present
- Installs Python 3.11+
- Installs Node.js 20+ (required for WhatsApp)
- Installs uv (fast package manager)
- Creates a virtual environment
- Installs Koda with all optional dependencies
- Builds the WhatsApp bridge

**Supported systems:**
- macOS (Intel & Apple Silicon)
- Ubuntu / Debian / Pop!_OS
- Fedora
- CentOS / RHEL / Rocky / Alma
- Arch / Manjaro
- openSUSE

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/ronaldjonkers/Koda.git
cd Koda

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

### Install with uv (faster)

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

## 🛠️ CLI Commands

### Main Commands

| Command | Description |
|---------|-------------|
| `koda onboard` | Run interactive setup wizard |
| `koda gateway` | Start the main Koda service (messaging, cron, webhooks) |
| `koda agent -m "..."` | Chat with the AI assistant |
| `koda config [section]` | Configure a specific section (assistant, provider, calendar, email, whatsapp, telegram) |
| `koda status` | Show current configuration and connection status |
| `koda setup-proxy` | Generate reverse proxy config for external access |

### Configuration Sections

```bash
koda config assistant    # Name, personality, language
koda config provider     # LLM provider and API key
koda config calendar     # Google, Exchange, CalDAV, iCloud calendars
koda config email        # Gmail, Exchange, IMAP email accounts
koda config whatsapp     # WhatsApp bot configuration
koda config telegram     # Telegram bot configuration
koda config webhook      # Webhook API settings
koda config --show       # Show current configuration
koda config --test       # Test all connections
```

### Cron Scheduler

```bash
koda cron list           # List all scheduled jobs
koda cron add            # Add a new scheduled job
koda cron remove <id>    # Remove a job
koda cron enable <id>    # Enable/disable a job
koda cron run <id>       # Manually run a job
```

### Channels (WhatsApp/Telegram)

```bash
koda channels status     # Show channel connection status
```

### Gateway Options

WhatsApp QR code login starts automatically when you run `koda gateway`.

```bash
koda gateway                    # Start with defaults
koda gateway --verbose          # Enable debug logging
koda gateway --no-bridge        # Don't auto-start WhatsApp bridge
koda gateway --port 18790       # Custom port
```

## 🤖 LLM Providers

Koda works with any LLM provider that supports the OpenAI API format.

### Supported Providers

| Provider | Purpose | Get API Key |
|----------|---------|-------------|
| `openrouter` | Access to all models (recommended) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `anthropic` | Claude direct | [console.anthropic.com](https://console.anthropic.com) |
| `openai` | GPT direct | [platform.openai.com](https://platform.openai.com) |
| `groq` | Fast inference + **Voice transcription** | [console.groq.com](https://console.groq.com) |
| `gemini` | Google Gemini | [aistudio.google.com](https://aistudio.google.com) |
| `vllm` | Local models via vLLM | Self-hosted |
| `ollama` | Local models via Ollama | Self-hosted |
| `lmstudio` | Local models via LM Studio | Self-hosted |

### Setup Wizard

The setup wizard guides you through provider and model selection:

```bash
koda config provider
```

**Example flow:**
```
AI Provider Configuration

Select provider [openrouter/anthropic/openai/gemini/groq] (openrouter): openrouter
Enter your openrouter API key: ********

Model Selection
Choose a model based on your needs and budget.

Popular OpenRouter Models:
  anthropic/claude-sonnet-4-20250514 - Best balance (recommended)
  anthropic/claude-opus-4-5 - Most capable, expensive
  openai/gpt-4o - OpenAI's latest
  deepseek/deepseek-chat - Very cheap, good quality

Model name (anthropic/claude-sonnet-4-20250514): 

Testing LLM connection... ✓ LLM responded: 'Hello! Koda is ready.'

✓ Provider configured: openrouter
✓ Model: anthropic/claude-sonnet-4-20250514
```

### Recommended Models by Provider

| Provider | Model | Cost | Use Case |
|----------|-------|------|----------|
| OpenRouter | `anthropic/claude-sonnet-4-20250514` | $$ | Best balance |
| OpenRouter | `deepseek/deepseek-chat` | $ | Budget-friendly |
| OpenRouter | `anthropic/claude-opus-4-5` | $$$$ | Most capable |
| Anthropic | `claude-sonnet-4-20250514` | $$ | Direct Claude |
| OpenAI | `gpt-4o` | $$$ | Latest GPT |
| OpenAI | `gpt-4o-mini` | $ | Fast & cheap |
| Groq | `llama-3.3-70b-versatile` | $ | Very fast |

### Manual Configuration

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agent": {
    "model": "anthropic/claude-sonnet-4-20250514"
  }
}
```

## 🖥️ Local Models

Run Koda with your own local models using vLLM, Ollama, or LM Studio.

### Option 1: vLLM (Recommended for production)

**1. Start your vLLM server**

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000
```

**2. Configure** (`~/.koda/config.json`)

```json
{
  "providers": {
    "vllm": {
      "apiKey": "dummy",
      "apiBase": "http://localhost:8000/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "meta-llama/Llama-3.1-8B-Instruct"
    }
  }
}
```

**3. Chat**

```bash
koda agent -m "Hello from my local LLM!"
```

### Option 2: Ollama (Easy setup)

**1. Install and run Ollama**

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.1
ollama serve
```

**2. Configure** (`~/.koda/config.json`)

```json
{
  "providers": {
    "ollama": {
      "apiKey": "ollama",
      "apiBase": "http://localhost:11434/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "llama3.1"
    }
  }
}
```

### Option 3: LM Studio (GUI-based)

**1. Download and run LM Studio**
- Download from [lmstudio.ai](https://lmstudio.ai)
- Load a model and start the local server

**2. Configure** (`~/.koda/config.json`)

```json
{
  "providers": {
    "lmstudio": {
      "apiKey": "lm-studio",
      "apiBase": "http://localhost:1234/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "local-model"
    }
  }
}
```

> **Tip:** The `apiKey` can be any non-empty string for local servers that don't require authentication.

### Any OpenAI-Compatible Server

Koda works with any server that implements the OpenAI API format:

```json
{
  "providers": {
    "custom": {
      "apiKey": "your-key-or-dummy",
      "apiBase": "http://your-server:port/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "your-model-name"
    }
  }
}
```

## 🎤 Voice Transcription

Koda supports voice message transcription via Groq's Whisper API (free tier available).

**1. Get a Groq API key** from [console.groq.com](https://console.groq.com)

**2. Configure** (`~/.koda/config.json`)

```json
{
  "providers": {
    "groq": {
      "apiKey": "gsk_xxx"
    }
  }
}
```

**3. Send voice messages** via Telegram or WhatsApp — they will be automatically transcribed.

> **Note:** Groq provides free voice transcription via Whisper. If configured, voice messages will be automatically transcribed before processing.

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
      "username": "DOMAIN\\username",
      "password": "app-password",
      "server": "mail.company.com",
      "version": "2016",
      "auth_type": "basic"
    }
  }
}
```

> **Note:** The `username` field is optional. Use it when your Exchange server requires a username different from your email address (e.g., `DOMAIN\\user` format for on-premises Exchange).

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

#### Quick Start

```bash
# 1. Configure WhatsApp (choose Bot Mode or Restricted Mode)
koda config whatsapp

# 2. Start the gateway - bridge starts automatically
koda gateway

# 3. First time: scan QR code shown in terminal with WhatsApp
#    Open WhatsApp > Settings > Linked Devices > Link a Device
```

#### How It Works

1. **Gateway starts** → WhatsApp bridge starts automatically
2. **QR code appears** in terminal (first time or when session expires)
3. **Scan with phone** → WhatsApp linked
4. **Messages flow**: WhatsApp → Bridge → Koda → LLM → Response

#### Logging & Debugging

When messages arrive, you'll see detailed logs:
```
📥 WhatsApp message from +31612345678: Hello, can you help me?
🤖 Processing message from whatsapp:31612345678: Hello, can you...
🧠 Calling LLM (anthropic/claude-sonnet-4-20250514)...
💬 LLM response ready (156 chars)
📤 Sending response to whatsapp:31612345678@s.whatsapp.net...
```

Use `--verbose` for even more detail: `koda gateway --verbose`

#### Options

| Flag | Description |
|------|-------------|
| `--verbose` | Show debug-level logs |
| `--no-bridge` | Don't auto-start WhatsApp bridge |

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

## � LinkedIn Integration

Koda can manage your LinkedIn presence with intelligent automation.

### Features

- **Message Monitoring**: Identify and respond to interesting messages
- **Auto-Accept Connections**: Accept relevant connection requests automatically
- **Feed Curation**: Collect interesting posts for daily review
- **Daily Digest**: Get a WhatsApp/Telegram summary with suggested actions
- **Smart Replies**: AI-generated reply suggestions
- **Post Creation**: Generate and publish posts (when trust level allows)

### Installation

```bash
pip install koda-assistant[linkedin]
```

### Setup

```bash
koda config linkedin
```

The setup wizard will ask for:
1. **LinkedIn credentials** (email/password)
2. **Your role** - What you do professionally
3. **Your goals** - What you're looking for on LinkedIn
4. **Interests** - Topics you care about
5. **Automation preferences** - What to auto-accept/reply

### Configuration

```json
{
  "integrations": {
    "linkedin": {
      "enabled": true,
      "email": "your-email@example.com",
      "password": "your-linkedin-password",
      
      "user_role": "Software Engineer at TechCorp",
      "user_goals": "Connect with other developers, find collaboration opportunities",
      "user_interests": ["AI", "Python", "startups"],
      
      "auto_accept_connections": true,
      "auto_reply_messages": false,
      "auto_post": false,
      "auto_react": false,
      
      "daily_digest_enabled": true,
      "daily_digest_time": "09:00",
      "daily_digest_channel": "whatsapp",
      "daily_digest_recipient": "+31612345678",
      
      "connection_keywords": ["developer", "engineer", "founder"],
      "ignore_keywords": ["sales", "recruitment"],
      
      "trust_level": 0
    }
  }
}
```

### Trust Levels

Control how much automation Koda performs:

| Level | Capabilities |
|-------|-------------|
| 0 | Manual only - suggestions via digest |
| 1 | Auto-accept connections matching keywords |
| 2 | Auto-accept all relevant connections |
| 3 | Auto-reply to messages |
| 4 | Auto-like relevant posts |
| 5 | Full automation including posting |

Increase trust level as you gain confidence in Koda's responses:

```bash
koda agent -m "Set my LinkedIn trust level to 2"
```

### Daily Digest

Every day at your configured time, Koda sends a digest via WhatsApp/Telegram:

```
📊 LinkedIn Daily Digest - 03 February 2026

✅ Auto-accepted 5 connections:
  • John Smith
  • Jane Doe
  • ...

💬 3 new messages:
  • John Smith: Hi! I saw your post about...
  • ...

🤝 2 connection requests to review:
  • Mark Johnson - CEO at StartupXYZ
  • ...

📰 5 interesting posts:
  • Sarah Chen: Great insights on AI development...
  • ...

💡 4 suggested actions:
  • [reply] John Smith
    Suggestion: Thanks for reaching out! I'd love to...
  • ...

Reply with action numbers to execute, or 'skip' to dismiss.
```

### Usage Examples

```bash
# Check LinkedIn messages
koda agent -m "Check my LinkedIn messages"

# Accept all pending connections
koda agent -m "Accept all pending LinkedIn connection requests"

# Get interesting posts
koda agent -m "Show me interesting posts from my LinkedIn feed"

# Create a post
koda agent -m "Write and post a LinkedIn update about my new project"

# Search for people
koda agent -m "Find Python developers in Amsterdam on LinkedIn"
```

> **Note:** LinkedIn automation uses an unofficial API. Use responsibly and respect LinkedIn's terms of service.

## � Contacts & Birthdays

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
| `koda gateway` | Start messaging gateway (WhatsApp QR login included) |
| `koda status` | Show status |
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
| `linkedin` | LinkedIn messages, connections, posts, search |

## 📝 License

MIT License - see LICENSE file

---

<p align="center">
  <em>Koda - Your elite AI executive assistant 🐕</em>
</p>
