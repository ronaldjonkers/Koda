"""CLI commands for koda."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from koda import __version__, __logo__

app = typer.Typer(
    name="koda",
    help=f"{__logo__} koda - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} koda v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """koda - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard(
    wizard: bool = typer.Option(True, "--wizard/--no-wizard", "-w", help="Run interactive setup wizard"),
    quick: bool = typer.Option(False, "--quick", "-q", help="Quick setup with defaults only"),
):
    """Initialize configuration and workspace with interactive setup wizard."""
    from koda.config.loader import get_config_path, save_config
    from koda.config.schema import Config
    from koda.utils.helpers import get_workspace_path
    
    config_path = get_config_path()
    
    if config_path.exists() and not quick:
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not typer.confirm("Run setup wizard to update configuration?"):
            raise typer.Exit()
    
    # Create workspace first
    workspace = get_workspace_path()
    console.print(f"[green]✓[/green] Workspace ready at {workspace}")
    
    # Create default bootstrap files
    _create_workspace_templates(workspace)
    
    if quick or not wizard:
        # Quick setup - just create default config
        if not config_path.exists():
            config = Config()
            save_config(config)
            console.print(f"[green]✓[/green] Created config at {config_path}")
        
        console.print(f"\n{__logo__} Ready!")
        console.print("\nNext steps:")
        console.print("  1. Run [cyan]koda config[/cyan] to configure features")
        console.print("  2. Or edit [cyan]~/.koda/config.json[/cyan] directly")
        console.print("  3. Chat: [cyan]koda agent -m \"Hello!\"[/cyan]")
    else:
        # Run interactive wizard
        from koda.cli.wizard import run_wizard
        run_wizard()




def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files
""",
        "SOUL.md": """# Soul

I am koda, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }
    
    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")
    
    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
        console.print("  [dim]Created memory/MEMORY.md[/dim]")


# ============================================================================
# Configuration Commands
# ============================================================================


@app.command()
def config(
    section: str = typer.Argument(
        None,
        help="Section to configure: assistant, provider, calendar, email, bot-email, channels, webhook, exchange, caldav, imap, google, telegram, whatsapp"
    ),
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration"),
    test: bool = typer.Option(False, "--test", "-t", help="Test current configuration"),
):
    """Configure features interactively or show current settings."""
    from koda.config.loader import load_config, get_config_path
    
    config_path = get_config_path()
    
    if not config_path.exists():
        console.print("[yellow]No configuration found. Run 'koda onboard' first.[/yellow]")
        raise typer.Exit(1)
    
    if show:
        _show_config()
        return
    
    if test:
        _test_config()
        return
    
    if section:
        # Configure specific section
        from koda.cli.wizard import configure_section
        configure_section(section)
    else:
        # Show available sections
        console.print("[bold]Available configuration sections:[/bold]\n")
        sections = [
            ("assistant", "Assistant name and personalization"),
            ("provider", "LLM API provider (OpenRouter, Anthropic, etc.)"),
            ("calendar", "Calendar integration (Google, Exchange, CalDAV)"),
            ("email", "Email reading (Gmail, Exchange, IMAP)"),
            ("bot-email", "Bot's email address for sending"),
            ("channels", "Messaging channels (Telegram, WhatsApp)"),
            ("webhook", "Webhook API for external integrations"),
        ]
        
        table = Table(show_header=False, box=None)
        table.add_column("Section", style="cyan")
        table.add_column("Description")
        
        for name, desc in sections:
            table.add_row(name, desc)
        
        console.print(table)
        console.print("\n[dim]Usage: koda config <section>[/dim]")
        console.print("[dim]       koda config --show    (show all settings)[/dim]")
        console.print("[dim]       koda config --test    (test all connections)[/dim]")


def _show_config():
    """Show current configuration."""
    from koda.config.loader import load_config
    
    cfg = load_config()
    
    console.print("[bold]Current Configuration[/bold]\n")
    
    table = Table(show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    
    # Assistant
    table.add_row("Assistant Name", cfg.assistant.name)
    table.add_row("User Name", cfg.assistant.user_name or "(not set)")
    table.add_row("Language", cfg.assistant.language)
    
    # Provider
    provider = "Not configured"
    if cfg.providers.openrouter.api_key:
        provider = "OpenRouter (***)"
    elif cfg.providers.anthropic.api_key:
        provider = "Anthropic (***)"
    elif cfg.providers.openai.api_key:
        provider = "OpenAI (***)"
    table.add_row("LLM Provider", provider)
    table.add_row("Model", cfg.agents.defaults.model)
    
    # Integrations
    table.add_row("Google Calendar", "✓ Enabled" if cfg.integrations.google.enabled else "Disabled")
    table.add_row("Exchange", "✓ Enabled" if cfg.integrations.exchange.enabled else "Disabled")
    table.add_row("CalDAV", "✓ Enabled" if cfg.integrations.caldav.enabled else "Disabled")
    table.add_row("IMAP Email", "✓ Enabled" if cfg.integrations.imap.enabled else "Disabled")
    table.add_row("Bot Email", cfg.integrations.bot_email.from_email if cfg.integrations.bot_email.enabled else "Disabled")
    
    # Channels
    table.add_row("Telegram", "✓ Enabled" if cfg.channels.telegram.enabled else "Disabled")
    table.add_row("WhatsApp", "✓ Enabled" if cfg.channels.whatsapp.enabled else "Disabled")
    
    # Webhook
    if cfg.integrations.reminder.webhook.enabled:
        table.add_row("Webhook API", f"Port {cfg.integrations.reminder.webhook.port}")
    else:
        table.add_row("Webhook API", "Disabled")
    
    console.print(table)


def _test_config():
    """Test all configured integrations."""
    from koda.config.loader import load_config
    
    cfg = load_config()
    
    console.print("[bold]Testing Configuration[/bold]\n")
    
    # Test LLM Provider
    console.print("LLM Provider: ", end="")
    if cfg.get_api_key():
        console.print("[green]✓[/green] API key configured")
    else:
        console.print("[red]✗[/red] No API key")
    
    # Test Exchange
    if cfg.integrations.exchange.enabled:
        console.print("Exchange: ", end="")
        try:
            from exchangelib import Credentials, Account, DELEGATE
            credentials = Credentials(
                cfg.integrations.exchange.email,
                cfg.integrations.exchange.password
            )
            account = Account(
                cfg.integrations.exchange.email,
                credentials=credentials,
                autodiscover=True,
                access_type=DELEGATE
            )
            console.print(f"[green]✓[/green] Connected as {account.primary_smtp_address}")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
    
    # Test CalDAV
    if cfg.integrations.caldav.enabled:
        console.print("CalDAV: ", end="")
        try:
            from koda.integrations.caldav_client import CalDAVClient
            client = CalDAVClient(
                cfg.integrations.caldav.url,
                cfg.integrations.caldav.username,
                cfg.integrations.caldav.password
            )
            success, msg = client.test_connection()
            if success:
                console.print(f"[green]✓[/green] {msg}")
            else:
                console.print(f"[red]✗[/red] {msg}")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
    
    # Test IMAP
    if cfg.integrations.imap.enabled:
        console.print("IMAP: ", end="")
        try:
            from koda.integrations.imap_client import IMAPClient
            client = IMAPClient(
                cfg.integrations.imap.host,
                cfg.integrations.imap.port,
                cfg.integrations.imap.username,
                cfg.integrations.imap.password,
                cfg.integrations.imap.use_ssl
            )
            success, msg = client.test_connection()
            if success:
                console.print(f"[green]✓[/green] {msg}")
            else:
                console.print(f"[red]✗[/red] {msg}")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
    
    # Test Bot Email (SMTP)
    if cfg.integrations.bot_email.enabled:
        console.print("Bot Email (SMTP): ", end="")
        try:
            import smtplib
            if cfg.integrations.bot_email.use_tls:
                server = smtplib.SMTP(cfg.integrations.bot_email.host, cfg.integrations.bot_email.port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(cfg.integrations.bot_email.host, cfg.integrations.bot_email.port)
            server.login(cfg.integrations.bot_email.username, cfg.integrations.bot_email.password)
            server.quit()
            console.print(f"[green]✓[/green] SMTP connected")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
    
    # Test Telegram
    if cfg.channels.telegram.enabled:
        console.print("Telegram: ", end="")
        try:
            import httpx
            response = httpx.get(
                f"https://api.telegram.org/bot{cfg.channels.telegram.token}/getMe",
                timeout=10
            )
            if response.status_code == 200 and response.json().get("ok"):
                bot = response.json()["result"]["username"]
                console.print(f"[green]✓[/green] @{bot}")
            else:
                console.print("[red]✗[/red] Invalid token")
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")
    
    console.print("\n[dim]Run 'koda config <section>' to fix any issues[/dim]")


# ============================================================================
# Cron / Scheduled Tasks
# ============================================================================

@app.command()
def cron(
    action: str = typer.Argument(..., help="Action: list, add, remove, enable, disable, run, status"),
    name: str = typer.Option(None, "--name", "-n", help="Task name (for add)"),
    schedule: str = typer.Option(None, "--schedule", "-s", help="Schedule: cron expression, 'daily', 'hourly', or ISO datetime"),
    prompt: str = typer.Option(None, "--prompt", "-p", help="What the agent should do"),
    task_id: str = typer.Option(None, "--id", help="Task ID (for remove, enable, disable, run)"),
    deliver: str = typer.Option(None, "--deliver", "-d", help="Deliver to: whatsapp:+316... or telegram:..."),
):
    """Manage scheduled tasks (cron jobs).
    
    Schedule recurring or one-time tasks for the agent to execute.
    
    Examples:
        koda cron list                    # Show all tasks
        koda cron status                  # Show scheduler status
        koda cron add -n "Morning Briefing" -s "0 8 * * *" -p "Send morning briefing to WhatsApp" -d "whatsapp:+31612345678"
        koda cron add -n "Hourly Check" -s "hourly" -p "Check for important emails"
        koda cron remove --id abc123      # Remove a task
        koda cron disable --id abc123     # Pause a task
        koda cron run --id abc123         # Run a task manually
    """
    from koda.scheduler.service import CronService
    from koda.scheduler.types import CronSchedule
    from koda.config.loader import get_data_dir
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    if action == "list":
        jobs = service.list_jobs(include_disabled=True)
        if not jobs:
            console.print("[yellow]No scheduled tasks found.[/yellow]")
            console.print("\nUse [cyan]koda cron add[/cyan] to create a task.")
            return
        
        console.print(f"[bold]Scheduled Tasks[/bold] ({len(jobs)} total)\n")
        
        from datetime import datetime
        table = Table(show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Schedule")
        table.add_column("Status")
        table.add_column("Next Run")
        
        for job in jobs:
            status = "✅ Enabled" if job.enabled else "❌ Disabled"
            
            # Format schedule
            if job.schedule.kind == "cron":
                sched = f"cron: {job.schedule.expr}"
            elif job.schedule.kind == "every":
                mins = job.schedule.every_ms // 60000 if job.schedule.every_ms else 0
                sched = f"every {mins}m"
            elif job.schedule.kind == "at":
                dt = datetime.fromtimestamp(job.schedule.at_ms / 1000)
                sched = f"at {dt.strftime('%Y-%m-%d %H:%M')}"
            else:
                sched = job.schedule.kind
            
            # Format next run
            if job.enabled and job.state.next_run_at_ms:
                next_dt = datetime.fromtimestamp(job.state.next_run_at_ms / 1000)
                next_str = next_dt.strftime('%Y-%m-%d %H:%M')
            else:
                next_str = "-"
            
            table.add_row(job.id, job.name, sched, status, next_str)
        
        console.print(table)
        
    elif action == "status":
        status = service.status()
        console.print("[bold]Scheduler Status[/bold]\n")
        console.print(f"Running: {'✅ Yes' if status['enabled'] else '❌ No'}")
        console.print(f"Total jobs: {status['jobs_total']}")
        console.print(f"Enabled jobs: {status['jobs_enabled']}")
        if status['next_wake_at']:
            console.print(f"Next wake: {status['next_wake_at']}")
    
    elif action == "add":
        if not name:
            console.print("[red]Error: --name is required[/red]")
            console.print("Example: koda cron add -n 'My Task' -s '0 9 * * *' -p 'Do something'")
            raise typer.Exit(1)
        
        if not schedule:
            console.print("[red]Error: --schedule is required[/red]")
            console.print("Examples:\n  -s '0 8 * * *'  (daily at 8am)\n  -s 'hourly'\n  -s '2024-12-25T09:00:00'")
            raise typer.Exit(1)
        
        if not prompt:
            console.print("[red]Error: --prompt is required[/red]")
            console.print("This is what the agent will do when the task runs.")
            raise typer.Exit(1)
        
        # Parse schedule
        schedule_obj = CronSchedule(kind="cron")
        
        if schedule == "daily":
            schedule_obj = CronSchedule(kind="cron", expr="0 8 * * *", tz="Europe/Amsterdam")
        elif schedule == "hourly":
            schedule_obj = CronSchedule(kind="every", every_ms=3600000)
        elif schedule.startswith("every "):
            # Parse "every 30m" or "every 2h"
            parts = schedule.split()
            if len(parts) == 2:
                interval = parts[1]
                if interval.endswith("m"):
                    ms = int(interval[:-1]) * 60000
                    schedule_obj = CronSchedule(kind="every", every_ms=ms)
                elif interval.endswith("h"):
                    ms = int(interval[:-1]) * 3600000
                    schedule_obj = CronSchedule(kind="every", every_ms=ms)
                else:
                    schedule_obj = CronSchedule(kind="cron", expr="0 8 * * *")
            else:
                schedule_obj = CronSchedule(kind="cron", expr="0 8 * * *")
        elif "T" in schedule or "-" in schedule[:10]:
            # ISO datetime - one-time task
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(schedule)
                at_ms = int(dt.timestamp() * 1000)
                schedule_obj = CronSchedule(kind="at", at_ms=at_ms)
            except ValueError:
                console.print(f"[red]Invalid datetime format: {schedule}[/red]")
                console.print("Use ISO format: 2024-12-25T09:00:00")
                raise typer.Exit(1)
        else:
            # Assume cron expression
            schedule_obj = CronSchedule(kind="cron", expr=schedule, tz="Europe/Amsterdam")
        
        # Parse delivery
        channel = None
        to = None
        deliver = bool(deliver)
        if deliver:
            if ":" in deliver:
                channel, to = deliver.split(":", 1)
            else:
                console.print("[red]Invalid --deliver format. Use: whatsapp:+31612345678[/red]")
                raise typer.Exit(1)
        
        job = service.add_job(
            name=name,
            schedule=schedule_obj,
            message=prompt,
            deliver=deliver,
            channel=channel,
            to=to
        )
        
        console.print(f"[green]✅ Created scheduled task:[/green] {name}")
        console.print(f"   ID: {job.id}")
        if job.state.next_run_at_ms:
            from datetime import datetime
            next_run = datetime.fromtimestamp(job.state.next_run_at_ms / 1000)
            console.print(f"   Next run: {next_run.strftime('%Y-%m-%d %H:%M')}")
    
    elif action == "remove":
        if not task_id:
            console.print("[red]Error: --id is required[/red]")
            console.print("Use 'koda cron list' to see task IDs")
            raise typer.Exit(1)
        
        if service.remove_job(task_id):
            console.print(f"[green]✅ Removed task {task_id}[/green]")
        else:
            console.print(f"[red]❌ Task {task_id} not found[/red]")
    
    elif action == "enable":
        if not task_id:
            console.print("[red]Error: --id is required[/red]")
            raise typer.Exit(1)
        
        if service.set_job_enabled(task_id, True):
            console.print(f"[green]✅ Enabled task {task_id}[/green]")
        else:
            console.print(f"[red]❌ Task {task_id} not found[/red]")
    
    elif action == "disable":
        if not task_id:
            console.print("[red]Error: --id is required[/red]")
            raise typer.Exit(1)
        
        if service.set_job_enabled(task_id, False):
            console.print(f"[yellow]⏸️ Disabled task {task_id}[/yellow]")
        else:
            console.print(f"[red]❌ Task {task_id} not found[/red]")
    
    elif action == "run":
        if not task_id:
            console.print("[red]Error: --id is required[/red]")
            raise typer.Exit(1)
        
        import asyncio
        
        async def do_run():
            success = await service.run_job(task_id, force=True)
            return success
        
        success = asyncio.run(do_run())
        if success:
            console.print(f"[green]✅ Executed task {task_id}[/green]")
        else:
            console.print(f"[red]❌ Task {task_id} not found or disabled[/red]")
    
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Valid actions: list, status, add, remove, enable, disable, run")


# ============================================================================
# Setup Proxy (for external access)
# ============================================================================


@app.command("setup-proxy")
def setup_proxy(
    server: str = typer.Option("nginx", "--server", "-s", help="Web server: nginx, caddy"),
    domain: str = typer.Option("", "--domain", "-d", help="Domain name for SSL"),
    port: int = typer.Option(18790, "--port", "-p", help="Koda gateway port"),
):
    """Generate reverse proxy configuration for external access.
    
    By default, Koda only listens on localhost for security.
    Use this command to generate a reverse proxy configuration
    that allows secure external access with SSL.
    """
    from pathlib import Path
    
    console.print(f"\n[bold cyan]🔒 Secure External Access Setup[/bold cyan]\n")
    console.print("[yellow]⚠️  Security Warning:[/yellow]")
    console.print("  Exposing Koda externally requires proper security measures:")
    console.print("  - Use HTTPS (SSL/TLS) - never expose over plain HTTP")
    console.print("  - Use strong API keys for webhook endpoints")
    console.print("  - Consider IP whitelisting or VPN access")
    console.print("")
    
    if server == "nginx":
        config = f"""# Nginx reverse proxy configuration for Koda
# Save this as: /etc/nginx/sites-available/koda

server {{
    listen 80;
    server_name {domain or 'your-domain.com'};
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain or 'your-domain.com'};
    
    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/{domain or 'your-domain.com'}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain or 'your-domain.com'}/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Koda Gateway
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    # Webhook API (if enabled)
    location /api/ {{
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""
    elif server == "caddy":
        config = f"""# Caddy reverse proxy configuration for Koda
# Save this as: /etc/caddy/Caddyfile

{domain or 'your-domain.com'} {{
    # Automatic HTTPS with Let's Encrypt
    
    # Koda Gateway
    reverse_proxy localhost:{port}
    
    # Webhook API (if enabled)
    handle_path /api/* {{
        reverse_proxy localhost:8080
    }}
    
    # Security headers
    header {{
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
    }}
}}
"""
    else:
        console.print(f"[red]Unknown server: {server}. Use nginx or caddy.[/red]")
        raise typer.Exit(1)
    
    # Save configuration
    config_file = Path(f"koda-{server}.conf")
    config_file.write_text(config)
    console.print(f"[green]✓[/green] Configuration saved to: {config_file}")
    
    console.print("\n[bold]Next steps:[/bold]")
    if server == "nginx":
        console.print("  1. Copy config: sudo cp koda-nginx.conf /etc/nginx/sites-available/koda")
        console.print("  2. Enable site: sudo ln -s /etc/nginx/sites-available/koda /etc/nginx/sites-enabled/")
        console.print("  3. Get SSL cert: sudo certbot --nginx -d " + (domain or 'your-domain.com'))
        console.print("  4. Reload nginx: sudo systemctl reload nginx")
    else:
        console.print("  1. Copy config: sudo cp koda-caddy.conf /etc/caddy/Caddyfile")
        console.print("  2. Reload caddy: sudo systemctl reload caddy")
    
    console.print("\n[dim]Caddy automatically handles SSL certificates.[/dim]")
    console.print("[dim]For nginx, use Let's Encrypt (certbot) for free SSL.[/dim]")


# ============================================================================
# Google Workspace Setup
# ============================================================================


@app.command("setup-google")
def setup_google(
    show_instructions: bool = typer.Option(False, "--instructions", "-i", help="Show setup instructions"),
    test_only: bool = typer.Option(False, "--test", "-t", help="Test existing connection"),
):
    """Setup Google Workspace integration (Gmail, Calendar, Meet).
    
    This command guides you through connecting your Google account
    for full Gmail, Calendar (including shared), and Meet integration.
    """
    from pathlib import Path
    
    if show_instructions:
        from koda.integrations.google_workspace import GoogleWorkspaceClient
        console.print(GoogleWorkspaceClient.SETUP_INSTRUCTIONS)
        return
    
    console.print("\n[bold cyan]🔧 Google Workspace Setup[/bold cyan]\n")
    
    # Check for credentials file
    creds_file = Path("~/.koda/google_credentials.json").expanduser()
    
    if not creds_file.exists():
        console.print("[yellow]⚠️  Credentials file not found![/yellow]\n")
        console.print("Je moet eerst een Google Cloud Project aanmaken en credentials downloaden.")
        console.print("Run [cyan]koda setup-google --instructions[/cyan] voor de volledige handleiding.\n")
        console.print("[bold]Korte versie:[/bold]")
        console.print("1. Ga naar https://console.cloud.google.com/")
        console.print("2. Maak een project en enable Gmail + Calendar APIs")
        console.print("3. Maak OAuth credentials (Desktop app)")
        console.print("4. Download JSON en sla op als ~/.koda/google_credentials.json")
        console.print("\nDaarna kun je dit command opnieuw runnen.")
        return
    
    # Check if already authorized
    try:
        from koda.integrations.google_workspace import GoogleWorkspaceClient
        client = GoogleWorkspaceClient()
        
        if test_only or client.is_authorized:
            console.print("Testing existing connection...\n")
            success, message = client.test_connection()
            
            if success:
                console.print(f"[green]✓[/green] {message}\n")
                
                # Show calendars
                calendars = client.list_calendars()
                console.print(f"[bold]Beschikbare Calendars ({len(calendars)}):[/bold]")
                for cal in calendars:
                    primary = " [primary]" if cal.is_primary else ""
                    role = f"({cal.access_role})"
                    console.print(f"  • {cal.name}{primary} {role}")
                
                console.print("\n[green]✓ Google Workspace is volledig geconfigureerd![/green]")
                return
            else:
                console.print(f"[red]✗[/red] {message}")
                if not test_only:
                    console.print("\nOpnieuw authoriseren...\n")
        
        # Run authorization flow
        console.print("Opening browser for Google authorization...")
        console.print("[dim]Log in met je Google account en geef Koda toegang.[/dim]\n")
        
        if client.authorize_interactive():
            console.print("\n[green]✓ Google Workspace succesvol verbonden![/green]")
            
            # Show what we have access to
            success, message = client.test_connection()
            console.print(f"  {message}")
            
            calendars = client.list_calendars()
            console.print(f"\n[bold]Beschikbare Calendars ({len(calendars)}):[/bold]")
            for cal in calendars:
                primary = " [primary]" if cal.is_primary else ""
                console.print(f"  • {cal.name}{primary}")
            
            console.print("\n[bold]Je kunt nu:[/bold]")
            console.print("  • Gmail lezen en versturen")
            console.print("  • Calendar events bekijken en maken")
            console.print("  • Google Meet links aanmaken")
            console.print("  • Shared calendars zien")
        else:
            console.print("\n[red]✗ Authorization failed. Probeer opnieuw.[/red]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("setup-linkedin")
def setup_linkedin(
    reset: bool = typer.Option(False, "--reset", "-r", help="Reset existing session before login"),
    status: bool = typer.Option(False, "--status", "-s", help="Check session status only"),
):
    """Setup LinkedIn integration via browser login.
    
    Opens a browser for manual LinkedIn login. The session is saved
    and reused for all future automation (posting, analytics, etc).
    """
    from pathlib import Path
    import shutil
    
    browser_path = Path.home() / ".koda" / "linkedin_browser"
    style_path = Path.home() / ".koda" / "linkedin_style.json"
    
    # Status check
    if status:
        console.print("\n[bold cyan]🔗 LinkedIn Status[/bold cyan]\n")
        
        if browser_path.exists():
            session_files = list(browser_path.glob("**/Cookies*")) + list(browser_path.glob("**/Local Storage*"))
            if session_files:
                console.print("[green]✓[/green] Browser sessie: Aanwezig")
            else:
                console.print("[yellow]⚠️[/yellow] Browser sessie: Leeg (login nodig)")
        else:
            console.print("[red]✗[/red] Browser sessie: Niet gevonden")
        
        if style_path.exists():
            try:
                import json
                with open(style_path) as f:
                    style_data = json.load(f)
                console.print(f"[green]✓[/green] Stijl profiel: {style_data.get('language', '?')}, {style_data.get('tone', '?')}")
            except:
                console.print("[yellow]⚠️[/yellow] Stijl profiel: Corrupt")
        else:
            console.print("[dim]ℹ️[/dim] Stijl profiel: Niet geleerd (vraag de bot om je stijl te leren)")
        
        return
    
    # Reset if requested
    if reset and browser_path.exists():
        console.print("[yellow]Resetting LinkedIn session...[/yellow]")
        try:
            shutil.rmtree(browser_path)
            console.print("[green]✓[/green] Browser sessie verwijderd")
        except Exception as e:
            console.print(f"[red]Error removing session: {e}[/red]")
    
    console.print("\n[bold cyan]🔗 LinkedIn Setup (Browser Login)[/bold cyan]\n")
    console.print("Dit opent een browser venster waar je kunt inloggen op LinkedIn.")
    console.print("Na het inloggen wordt je sessie opgeslagen voor toekomstig gebruik.\n")
    
    console.print("[bold]Voordelen van deze methode:[/bold]")
    console.print("  • Geen problemen met 2FA")
    console.print("  • Stabielere connectie")
    console.print("  • Ondersteuning voor posting en analytics")
    console.print("  • Sessie blijft bewaard\n")
    
    if not typer.confirm("Browser openen voor LinkedIn login?"):
        raise typer.Exit()
    
    try:
        import asyncio
        from koda.integrations.linkedin_playwright import LinkedInPlaywright
        
        console.print("\n[dim]Browser wordt gestart...[/dim]")
        
        async def do_login():
            client = LinkedInPlaywright(headless=False)
            
            console.print("\n[yellow]Log in bij LinkedIn in het browser venster.[/yellow]")
            console.print("[dim]Druk Enter hier als je klaar bent met inloggen...[/dim]\n")
            
            await client._ensure_browser()
            await client._page.goto("https://www.linkedin.com/login")
            
            input()  # Wait for user
            
            # Verify login
            valid, message = await client.check_session()
            await client.close()
            
            return valid, message
        
        valid, message = asyncio.run(do_login())
        
        if valid:
            console.print("\n[green]✓ LinkedIn succesvol verbonden![/green]")
            console.print(f"  {message}\n")
            
            console.print("[bold]Je kunt nu:[/bold]")
            console.print("  • LinkedIn berichten lezen en versturen")
            console.print("  • Posts maken (met afbeeldingen)")
            console.print("  • Feed en analytics bekijken")
            console.print("  • Schrijfstijl laten analyseren")
            console.print("\n[dim]Tip: Vraag de bot 'leer mijn LinkedIn stijl' voor gepersonaliseerde suggesties.[/dim]")
        else:
            console.print(f"\n[red]✗ Login verificatie mislukt: {message}[/red]")
            console.print("Probeer opnieuw met: [cyan]koda setup-linkedin --reset[/cyan]")
            
    except ImportError:
        console.print("[red]Error: Playwright niet geïnstalleerd[/red]")
        console.print("\nInstalleer met:")
        console.print("  [cyan]pip install playwright[/cyan]")
        console.print("  [cyan]playwright install chromium[/cyan]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# ============================================================================
# Dashboard
# ============================================================================


@app.command()
def dashboard(
    port: int = typer.Option(8081, "--port", "-p", help="Dashboard port"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
):
    """Start the web dashboard for configuration."""
    from koda.dashboard import run_dashboard
    
    console.print(f"[green]🐕 Koda Dashboard starting...[/green]")
    console.print(f"[dim]Open http://localhost:{port} in your browser[/dim]")
    run_dashboard(host=host, port=port)


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    no_bridge: bool = typer.Option(False, "--no-bridge", help="Don't auto-start WhatsApp bridge"),
    no_dashboard: bool = typer.Option(False, "--no-dashboard", help="Don't auto-start web dashboard"),
    dashboard_port: int = typer.Option(8081, "--dashboard-port", help="Dashboard port (localhost only)"),
):
    """Start the koda gateway."""
    import subprocess
    import signal
    import threading
    from pathlib import Path
    from koda.config.loader import load_config, get_data_dir
    from koda.messaging.queue import MessageBus
    from koda.providers.litellm_provider import LiteLLMProvider
    from koda.core.loop import AgentLoop
    from koda.services.manager import ChannelManager
    from koda.scheduler.service import CronService
    from koda.scheduler.types import CronJob
    from koda.monitor.service import HeartbeatService
    from koda.services.reminder import ReminderService, EmailSender
    from koda.services.webhook_api import WebhookServer
    
    import sys
    from loguru import logger
    
    # Configure logging - always show INFO, DEBUG with --verbose
    logger.remove()  # Remove default handler
    if verbose:
        logger.add(sys.stderr, level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")
        import logging
        logging.basicConfig(level=logging.DEBUG)
    else:
        logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    
    console.print(f"{__logo__} Starting koda gateway on port {port}...")
    
    # Track bridge process for cleanup
    bridge_process = None
    dashboard_thread = None
    
    config = load_config()
    
    # Auto-start dashboard on localhost (not exposed externally)
    if not no_dashboard:
        def run_dashboard():
            try:
                from koda.dashboard.app import create_app
                import uvicorn
                # IMPORTANT: Only bind to 127.0.0.1 (localhost) for security
                uvicorn.run(
                    create_app(),
                    host="127.0.0.1",  # localhost only - not accessible from outside
                    port=dashboard_port,
                    log_level="warning"  # Reduce dashboard log noise
                )
            except Exception as e:
                logger.warning(f"Dashboard failed to start: {e}")
        
        dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        dashboard_thread.start()
        console.print(f"[green]✓[/green] Dashboard: http://localhost:{dashboard_port} (localhost only)")
    
    # Auto-start WhatsApp bridge if enabled
    if config.channels.whatsapp.enabled and not no_bridge:
        # Find the bridge directory
        import sys
        bridge_dir = Path(__file__).parent.parent.parent / "bridge"
        
        if bridge_dir.exists() and (bridge_dir / "src" / "whatsapp.ts").exists():
            # Auto-rebuild bridge to ensure latest code
            console.print("[dim]Building WhatsApp bridge...[/dim]")
            try:
                build_result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=str(bridge_dir),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if build_result.returncode == 0:
                    console.print("[green]✓[/green] WhatsApp bridge built")
                else:
                    console.print(f"[yellow]⚠[/yellow] Bridge build warning: {build_result.stderr[:200] if build_result.stderr else 'unknown'}")
            except subprocess.TimeoutExpired:
                console.print("[yellow]⚠[/yellow] Bridge build timed out")
            except FileNotFoundError:
                console.print("[yellow]⚠[/yellow] npm not found - skipping bridge build")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not build bridge: {e}")
            
            # Start the bridge
            if (bridge_dir / "dist" / "index.js").exists():
                console.print("[dim]Starting WhatsApp bridge...[/dim]")
                try:
                    # Always show bridge output for debugging
                    bridge_process = subprocess.Popen(
                        ["node", "dist/index.js"],
                        cwd=str(bridge_dir),
                        stdout=None,  # Inherit stdout to show bridge logs
                        stderr=None,  # Inherit stderr to show bridge errors
                    )
                    # Give the bridge a moment to start
                    import time
                    time.sleep(2)
                    
                    if bridge_process.poll() is None:
                        console.print("[green]✓[/green] WhatsApp bridge started")
                    else:
                        console.print("[yellow]⚠[/yellow] WhatsApp bridge failed to start")
                        bridge_process = None
                except FileNotFoundError:
                    console.print("[yellow]⚠[/yellow] Node.js not found - WhatsApp bridge not started")
                    console.print("[dim]  Install Node.js or run the bridge manually: cd bridge && npm start[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Could not start WhatsApp bridge: {e}")
            else:
                console.print("[yellow]⚠[/yellow] WhatsApp bridge not built")
                console.print("[dim]  Run: cd bridge && npm install && npm run build[/dim]")
        else:
            console.print("[yellow]⚠[/yellow] WhatsApp bridge source not found")
            console.print("[dim]  Ensure bridge/src/whatsapp.ts exists[/dim]")
    
    # Create components
    bus = MessageBus()
    
    # Create provider (supports OpenRouter, Anthropic, OpenAI, Bedrock)
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.koda/config.json under providers.openrouter.apiKey")
        raise typer.Exit(1)
    
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )
    
    # Build calendar configuration with assistant personalization
    calendar_config = {
        "google_enabled": config.integrations.google.enabled,
        "google_credentials_file": config.integrations.google.credentials_file,
        "google_token_file": config.integrations.google.token_file,
        "exchange_enabled": config.integrations.exchange.enabled,
        "exchange_email": config.integrations.exchange.email,
        "exchange_password": config.integrations.exchange.password,
        "exchange_server": config.integrations.exchange.server,
        "caldav_enabled": config.integrations.caldav.enabled,
        "caldav_url": config.integrations.caldav.url,
        "caldav_username": config.integrations.caldav.username,
        "caldav_password": config.integrations.caldav.password,
        "default_reminder_phone": config.channels.whatsapp.owner_phone or "",
        # Assistant personalization for language detection
        "assistant_config": {
            "name": config.assistant.name,
            "user_name": config.assistant.user_name,
            "language": config.assistant.language,
            "personality": config.assistant.personality,
        },
        # LinkedIn integration
        "linkedin": {
            "enabled": config.integrations.linkedin.enabled,
            "email": config.integrations.linkedin.email,
            "password": config.integrations.linkedin.password,
        },
        # Pass full config for UnifiedEmailTool
        "config": config
    }
    
    # Create agent (reminder_service will be set after it's created)
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        calendar_config=calendar_config
    )
    
    # Create cron service
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}"
        )
        # Optionally deliver to channel
        if job.payload.deliver and job.payload.to:
            from koda.messaging.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "whatsapp",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path, on_job=on_cron_job)
    
    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")
    
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True
    )
    
    # Create channel manager
    channels = ChannelManager(config, bus)
    
    # Create reminder service
    reminder_config = config.integrations.reminder
    email_sender = None
    if reminder_config.email.enabled:
        email_sender = EmailSender(
            smtp_host=reminder_config.email.smtp_host,
            smtp_port=reminder_config.email.smtp_port,
            username=reminder_config.email.username,
            password=reminder_config.email.password,
            from_email=reminder_config.email.from_email,
            use_tls=reminder_config.email.use_tls
        )
    
    async def send_reminder_message(channel: str, recipient: str, message: str) -> None:
        """Send reminder via messaging channel."""
        from koda.messaging.events import OutboundMessage
        await bus.publish_outbound(OutboundMessage(
            channel=channel,
            chat_id=recipient,
            content=message
        ))
    
    reminder_store_path = get_data_dir() / "reminders" / "reminders.json"
    reminder_service = ReminderService(
        store_path=reminder_store_path,
        email_sender=email_sender,
        message_callback=send_reminder_message
    )
    
    # Register reminder tool with agent
    from koda.core.tools.reminder import ReminderTool
    agent.tools.register(ReminderTool(reminder_service=reminder_service))
    
    # Register schedule tool with cron service
    from koda.core.tools.schedule import ScheduleTool
    agent.tools.register(ScheduleTool(cron_service=cron))
    
    # Update unified calendar tool with reminder service
    agent.reminder_service = reminder_service
    for tool in agent.tools._tools.values():
        if hasattr(tool, 'reminder_service') and tool.name == 'calendar':
            tool.reminder_service = reminder_service
    
    # Create webhook server
    webhook_server = None
    if reminder_config.webhook.enabled:
        async def on_webhook_message(message: str, session_key: str | None) -> str:
            return await agent.process_direct(message, session_key or "webhook:default")
        
        webhook_server = WebhookServer(
            host=reminder_config.webhook.host,
            port=reminder_config.webhook.port,
            on_message=on_webhook_message,
            reminder_service=reminder_service,
            api_key=reminder_config.webhook.api_key or None
        )
    
    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")
    
    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")
    
    console.print(f"[green]✓[/green] Heartbeat: every 30m")
    console.print(f"[green]✓[/green] Reminder service: enabled")
    
    if webhook_server:
        console.print(f"[green]✓[/green] Webhook API: http://{reminder_config.webhook.host}:{reminder_config.webhook.port}")
    
    if email_sender:
        console.print(f"[green]✓[/green] Email reminders: {reminder_config.email.from_email}")
    
    # Start config file watcher for auto-reload
    from koda.config.watcher import start_config_watcher, stop_config_watcher
    
    def on_config_reload():
        """Handle config file changes."""
        try:
            new_config = load_config()
            # Update channel manager config
            channels.reload_config(new_config)
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Config reload failed: {e}")
    
    config_watcher = start_config_watcher(on_reload=on_config_reload)
    console.print(f"[green]✓[/green] Config watcher: auto-reload on changes")
    
    # Start email watcher for proactive email notifications
    email_watcher = None
    try:
        from koda.services.email_watcher import create_email_watcher_from_config
        
        async def send_email_notification(phone: str, message: str):
            """Send email notification via WhatsApp."""
            from koda.messaging.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id=phone + "@s.whatsapp.net",
                content=message
            ))
        
        email_watcher = create_email_watcher_from_config(config, send_email_notification)
        if email_watcher and email_watcher.watching_count > 0:
            email_watcher.start()
            console.print(f"[green]✓[/green] Email watcher: {email_watcher.watching_count} account(s) monitored")
    except Exception as e:
        logger.debug(f"Email watcher not started: {e}")
    
    # Start calendar watcher for proactive event reminders
    calendar_watcher = None
    try:
        from koda.services.calendar_watcher import create_calendar_watcher_from_config
        
        async def send_calendar_notification(phone: str, message: str):
            """Send calendar notification via WhatsApp."""
            from koda.messaging.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel="whatsapp",
                chat_id=phone + "@s.whatsapp.net",
                content=message
            ))
        
        calendar_watcher = create_calendar_watcher_from_config(config, send_calendar_notification)
        if calendar_watcher and calendar_watcher.source_count > 0:
            calendar_watcher.start()
            console.print(f"[green]✓[/green] Calendar watcher: {calendar_watcher.source_count} calendar(s) + morning briefing")
    except Exception as e:
        logger.debug(f"Calendar watcher not started: {e}")
    
    # Start proactive reminder service (new executive assistant features)
    proactive_service = None
    try:
        from koda.services.proactive_reminder import (
            ProactiveReminderService, ReminderConfig
        )
        
        # Create proactive reminder config
        proactive_config = ReminderConfig(
            calendar_reminders_enabled=True,
            calendar_default_minutes_before=15,
            calendar_morning_check_time="08:00",
            birthday_reminders_enabled=True,
            birthday_days_before=1,
            birthday_send_time="09:00",
            special_occasions_enabled=True,
            email_digest_enabled=True,
            email_digest_time="08:30",
            default_channel="whatsapp",
            default_recipient=config.channels.whatsapp.owner_phone or "",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            respect_quiet_hours=True
        )
        
        async def send_proactive_message(channel: str, recipient: str, message: str):
            """Send proactive reminder via messaging channel."""
            from koda.messaging.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=channel,
                chat_id=recipient if recipient else config.channels.whatsapp.owner_phone + "@s.whatsapp.net",
                content=message
            ))
        
        proactive_service = ProactiveReminderService(
            config=proactive_config,
            send_callback=send_proactive_message
        )
        
        console.print(f"[green]✓[/green] Proactive assistant: enabled (reminders, birthdays, briefings)")
    except Exception as e:
        logger.warning(f"Proactive reminder service not started: {e}")
        proactive_service = None
    
    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await reminder_service.start()
            if proactive_service:
                await proactive_service.start()
            
            tasks = [agent.run(), channels.start_all()]
            if webhook_server:
                tasks.append(webhook_server.start())
            
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            pass
        finally:
            console.print("\nShutting down...")
            stop_config_watcher()
            if email_watcher:
                email_watcher.stop()
            if calendar_watcher:
                calendar_watcher.stop()
            if proactive_service:
                await proactive_service.stop()
            heartbeat.stop()
            cron.stop()
            reminder_service.stop()
            if webhook_server:
                await webhook_server.stop()
            agent.stop()
            await channels.stop_all()
            
            # Stop WhatsApp bridge if we started it
            if bridge_process and bridge_process.poll() is None:
                console.print("[dim]Stopping WhatsApp bridge...[/dim]")
                bridge_process.terminate()
                try:
                    bridge_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    bridge_process.kill()
                console.print("[green]✓[/green] WhatsApp bridge stopped")
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        # Ensure bridge is stopped even if asyncio.run fails
        if bridge_process and bridge_process.poll() is None:
            bridge_process.terminate()
            bridge_process.wait(timeout=5)




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
):
    """Interact with the agent directly."""
    from koda.config.loader import load_config
    from koda.messaging.queue import MessageBus
    from koda.providers.litellm_provider import LiteLLMProvider
    from koda.core.loop import AgentLoop
    
    config = load_config()
    
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        console.print("[red]Error: No API key configured.[/red]")
        raise typer.Exit(1)

    bus = MessageBus()
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )
    
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        brave_api_key=config.tools.web.search.api_key or None
    )
    
    if message:
        # Single message mode
        async def run_once():
            response = await agent_loop.process_direct(message, session_id)
            console.print(f"\n{__logo__} {response}")
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        console.print(f"{__logo__} Interactive mode (Ctrl+C to exit)\n")
        
        async def run_interactive():
            while True:
                try:
                    user_input = console.input("[bold blue]You:[/bold blue] ")
                    if not user_input.strip():
                        continue
                    
                    response = await agent_loop.process_direct(user_input, session_id)
                    console.print(f"\n{__logo__} {response}\n")
                except KeyboardInterrupt:
                    console.print("\nGoodbye!")
                    break
        
        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from koda.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        "✓" if wa.enabled else "✗",
        wa.bridge_url
    )

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row(
        "Telegram",
        "✓" if tg.enabled else "✗",
        tg_config
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess
    
    # User's bridge location
    user_bridge = Path.home() / ".koda" / "bridge"
    
    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge
    
    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)
    
    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent / "bridge"  # koda/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)
    
    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge
    
    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall koda")
        raise typer.Exit(1)
    
    console.print(f"{__logo__} Setting up bridge...")
    
    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))
    
    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)
    
    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess
    
    bridge_dir = _get_bridge_dir()
    
    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")
    
    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from koda.config.loader import get_data_dir
    from koda.scheduler.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    jobs = service.list_jobs(include_disabled=all)
    
    if not jobs:
        console.print("No scheduled jobs.")
        return
    
    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")
    
    import time
    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"
        
        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000))
            next_run = next_time
        
        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"
        
        table.add_row(job.id, job.name, sched, status, next_run)
    
    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"),
):
    """Add a scheduled job."""
    from koda.config.loader import get_data_dir
    from koda.scheduler.service import CronService
    from koda.scheduler.types import CronSchedule
    
    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )
    
    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from koda.config.loader import get_data_dir
    from koda.scheduler.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from koda.config.loader import get_data_dir
    from koda.scheduler.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from koda.config.loader import get_data_dir
    from koda.scheduler.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    async def run():
        return await service.run_job(job_id, force=force)
    
    if asyncio.run(run()):
        console.print(f"[green]✓[/green] Job executed")
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show koda status."""
    from koda.config.loader import load_config, get_config_path
    from koda.utils.helpers import get_workspace_path
    
    config_path = get_config_path()
    workspace = get_workspace_path()
    
    console.print(f"{__logo__} koda Status\n")
    
    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")
    
    if config_path.exists():
        config = load_config()
        console.print(f"Model: {config.agents.defaults.model}")
        
        # Check API keys
        has_openrouter = bool(config.providers.openrouter.api_key)
        has_anthropic = bool(config.providers.anthropic.api_key)
        has_openai = bool(config.providers.openai.api_key)
        has_gemini = bool(config.providers.gemini.api_key)
        has_vllm = bool(config.providers.vllm.api_base)
        
        console.print(f"OpenRouter API: {'[green]✓[/green]' if has_openrouter else '[dim]not set[/dim]'}")
        console.print(f"Anthropic API: {'[green]✓[/green]' if has_anthropic else '[dim]not set[/dim]'}")
        console.print(f"OpenAI API: {'[green]✓[/green]' if has_openai else '[dim]not set[/dim]'}")
        console.print(f"Gemini API: {'[green]✓[/green]' if has_gemini else '[dim]not set[/dim]'}")
        vllm_status = f"[green]✓ {config.providers.vllm.api_base}[/green]" if has_vllm else "[dim]not set[/dim]"
        console.print(f"vLLM/Local: {vllm_status}")


# ============================================================================
# Daemon Commands
# ============================================================================

daemon_app = typer.Typer(help="Manage Koda as a system daemon")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("install")
def daemon_install():
    """Install Koda as a system daemon (auto-start on login)."""
    from koda.daemon import install_daemon
    install_daemon()


@daemon_app.command("uninstall")
def daemon_uninstall():
    """Uninstall the Koda daemon."""
    from koda.daemon import uninstall_daemon
    uninstall_daemon()


@daemon_app.command("start")
def daemon_start():
    """Start the Koda daemon."""
    from koda.daemon import DaemonManager
    manager = DaemonManager()
    success, message = manager.start()
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")


@daemon_app.command("stop")
def daemon_stop():
    """Stop the Koda daemon."""
    from koda.daemon import DaemonManager
    manager = DaemonManager()
    success, message = manager.stop()
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")


@daemon_app.command("restart")
def daemon_restart():
    """Restart the Koda daemon."""
    from koda.daemon import DaemonManager
    manager = DaemonManager()
    success, message = manager.restart()
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")


@daemon_app.command("status")
def daemon_status_cmd():
    """Show daemon status."""
    from koda.daemon import daemon_status
    daemon_status()


@daemon_app.command("logs")
def daemon_logs_cmd(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show")
):
    """Show daemon logs."""
    from koda.daemon import daemon_logs
    daemon_logs(lines)


if __name__ == "__main__":
    app()
