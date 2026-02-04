"""Web Dashboard for Koda configuration and monitoring."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Global metrics tracking
_metrics = {
    "messages_received": 0,
    "messages_processed": 0,
    "errors": 0,
    "start_time": time.time(),
    "active_tasks": [],
    "recent_messages": []
}


def increment_metric(name: str, value: int = 1):
    """Increment a metric counter."""
    if name in _metrics:
        _metrics[name] += value


def add_active_task(task_id: str, description: str):
    """Add an active task."""
    _metrics["active_tasks"].append({
        "id": task_id,
        "description": description,
        "started": datetime.now().isoformat()
    })


def remove_active_task(task_id: str):
    """Remove a completed task."""
    _metrics["active_tasks"] = [t for t in _metrics["active_tasks"] if t["id"] != task_id]


def add_recent_message(sender: str, preview: str):
    """Add a recent message to tracking."""
    _metrics["recent_messages"].insert(0, {
        "sender": sender,
        "preview": preview[:50],
        "time": datetime.now().isoformat()
    })
    _metrics["recent_messages"] = _metrics["recent_messages"][:20]  # Keep last 20


def create_app() -> FastAPI:
    """Create the FastAPI dashboard application."""
    app = FastAPI(
        title="Koda Dashboard",
        description="Web interface for Koda configuration and monitoring",
        version="2.0.0"
    )
    
    # ============== API Routes ==============
    
    @app.get("/api/config")
    async def get_config():
        """Get current configuration with all details."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            
            # Build comprehensive config response
            return {
                "assistant": {
                    "name": config.assistant.name,
                    "user_name": config.assistant.user_name,
                    "language": config.assistant.language,
                    "personality": config.assistant.personality,
                    "model": getattr(config.assistant, 'model', None) or config.agents.defaults.model
                },
                "channels": {
                    "whatsapp": {
                        "enabled": config.channels.whatsapp.enabled,
                        "bot_mode": config.channels.whatsapp.bot_mode,
                        "owner_phone": config.channels.whatsapp.owner_phone,
                        "allow_from": config.channels.whatsapp.allow_from or [],
                        "escalate_to_owner": config.channels.whatsapp.escalate_to_owner
                    },
                    "telegram": {
                        "enabled": config.channels.telegram.enabled if hasattr(config.channels, 'telegram') else False
                    }
                },
                "integrations": {
                    "linkedin": {
                        "enabled": config.integrations.linkedin.enabled,
                        "email": config.integrations.linkedin.email or ""
                    },
                    "google": {
                        "enabled": config.integrations.google.enabled
                    },
                    "exchange": {
                        "enabled": config.integrations.exchange.enabled,
                        "email": config.integrations.exchange.email or ""
                    },
                    "caldav": {
                        "enabled": config.integrations.caldav.enabled,
                        "url": config.integrations.caldav.url or ""
                    }
                },
                "tools": {
                    "brave_api_key": bool(config.tools.web.search.api_key),
                    "brave_api_key_preview": (config.tools.web.search.api_key[:8] + "..." if config.tools.web.search.api_key else "")
                },
                "model": config.agents.defaults.model,
                "max_iterations": config.agents.defaults.max_tool_iterations
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/config/raw")
    async def get_raw_config():
        """Get raw config for editing (sensitive fields shown as indicators)."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            raw = config.model_dump()
            return _prepare_config_for_display(raw)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/config")
    async def update_config(request: Request):
        """Update configuration."""
        try:
            from koda.config.loader import load_config, save_config
            data = await request.json()
            config = load_config()
            
            # Update assistant
            if "assistant" in data:
                for k, v in data["assistant"].items():
                    if hasattr(config.assistant, k) and v is not None:
                        setattr(config.assistant, k, v)
            
            # Update channels
            if "channels" in data:
                if "whatsapp" in data["channels"]:
                    wa = data["channels"]["whatsapp"]
                    for k, v in wa.items():
                        if hasattr(config.channels.whatsapp, k) and v is not None:
                            setattr(config.channels.whatsapp, k, v)
            
            # Update integrations
            if "integrations" in data:
                if "linkedin" in data["integrations"]:
                    li = data["integrations"]["linkedin"]
                    for k, v in li.items():
                        if hasattr(config.integrations.linkedin, k) and v is not None:
                            setattr(config.integrations.linkedin, k, v)
            
            # Update tools/API keys
            if "tools" in data:
                if "brave_api_key" in data["tools"] and data["tools"]["brave_api_key"]:
                    config.tools.web.search.api_key = data["tools"]["brave_api_key"]
            
            # Update model
            if "model" in data and data["model"]:
                config.agents.defaults.model = data["model"]
            
            save_config(config)
            return {"status": "ok", "message": "Configuration saved"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/status")
    async def get_status():
        """Get comprehensive system status."""
        try:
            from koda.config.loader import load_config, get_data_dir
            config = load_config()
            
            # Calculate uptime
            uptime_seconds = int(time.time() - _metrics["start_time"])
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s"
            
            # Count schedules
            schedule_count = 0
            cron_file = get_data_dir() / "cron" / "jobs.json"
            if cron_file.exists():
                try:
                    with open(cron_file) as f:
                        jobs = json.load(f)
                        schedule_count = len(jobs.get("jobs", []))
                except:
                    pass
            
            return {
                "assistant": {
                    "name": config.assistant.name,
                    "model": config.agents.defaults.model
                },
                "whatsapp": {
                    "enabled": config.channels.whatsapp.enabled,
                    "bot_mode": config.channels.whatsapp.bot_mode
                },
                "integrations": {
                    "linkedin": config.integrations.linkedin.enabled,
                    "accounts": len(config.integrations.accounts) if config.integrations.accounts else 0
                },
                "metrics": {
                    "uptime": uptime_str,
                    "messages_received": _metrics["messages_received"],
                    "messages_processed": _metrics["messages_processed"],
                    "errors": _metrics["errors"],
                    "active_tasks": len(_metrics["active_tasks"]),
                    "scheduled_jobs": schedule_count
                },
                "api_keys": {
                    "brave": bool(config.tools.web.search.api_key)
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/accounts")
    async def get_accounts():
        """Get configured accounts."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            accounts = []
            
            for acc in (config.integrations.accounts or []):
                acc_data = {
                    "name": getattr(acc, 'name', acc.get('name', 'Unknown')) if hasattr(acc, 'name') or isinstance(acc, dict) else 'Unknown',
                    "type": getattr(acc, 'type', acc.get('type', 'unknown')) if hasattr(acc, 'type') or isinstance(acc, dict) else 'unknown',
                    "enabled": getattr(acc, 'enabled', acc.get('enabled', True)) if hasattr(acc, 'enabled') or isinstance(acc, dict) else True,
                    "capabilities": getattr(acc, 'capabilities', acc.get('capabilities', [])) if hasattr(acc, 'capabilities') or isinstance(acc, dict) else [],
                    "email": getattr(acc, 'email', acc.get('email', '')) if hasattr(acc, 'email') or isinstance(acc, dict) else ''
                }
                accounts.append(acc_data)
            
            return {"accounts": accounts}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/schedules")
    async def get_schedules():
        """Get scheduled tasks from cron jobs."""
        try:
            from koda.config.loader import get_data_dir
            
            # Try multiple possible locations for schedules
            schedules = []
            
            # Check cron jobs
            cron_file = get_data_dir() / "cron" / "jobs.json"
            if cron_file.exists():
                with open(cron_file) as f:
                    data = json.load(f)
                    for job in data.get("jobs", []):
                        schedules.append({
                            "id": job.get("id", ""),
                            "name": job.get("name", job.get("payload", {}).get("message", "")[:50]),
                            "schedule": job.get("cron_expr", ""),
                            "enabled": job.get("enabled", True),
                            "next_run": job.get("next_run", ""),
                            "last_run": job.get("last_run", ""),
                            "type": "cron"
                        })
            
            # Also check reminders
            reminder_file = get_data_dir() / "reminders" / "reminders.json"
            if reminder_file.exists():
                with open(reminder_file) as f:
                    data = json.load(f)
                    for reminder in data.get("reminders", []):
                        schedules.append({
                            "id": reminder.get("id", ""),
                            "name": reminder.get("message", "")[:50],
                            "schedule": reminder.get("time", ""),
                            "enabled": True,
                            "type": "reminder"
                        })
            
            return {"schedules": schedules, "count": len(schedules)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/schedules/{job_id}")
    async def delete_schedule(job_id: str):
        """Delete a scheduled task."""
        try:
            from koda.config.loader import get_data_dir
            
            # Try cron jobs first
            cron_file = get_data_dir() / "cron" / "jobs.json"
            if cron_file.exists():
                with open(cron_file) as f:
                    data = json.load(f)
                
                original_count = len(data.get("jobs", []))
                data["jobs"] = [j for j in data.get("jobs", []) if j.get("id") != job_id]
                
                if len(data["jobs"]) < original_count:
                    with open(cron_file, "w") as f:
                        json.dump(data, f, indent=2)
                    return {"status": "deleted", "id": job_id}
            
            # Try reminders
            reminder_file = get_data_dir() / "reminders" / "reminders.json"
            if reminder_file.exists():
                with open(reminder_file) as f:
                    data = json.load(f)
                
                original_count = len(data.get("reminders", []))
                data["reminders"] = [r for r in data.get("reminders", []) if r.get("id") != job_id]
                
                if len(data["reminders"]) < original_count:
                    with open(reminder_file, "w") as f:
                        json.dump(data, f, indent=2)
                    return {"status": "deleted", "id": job_id}
            
            raise HTTPException(status_code=404, detail="Schedule not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/metrics")
    async def get_metrics():
        """Get real-time metrics."""
        return {
            "messages_received": _metrics["messages_received"],
            "messages_processed": _metrics["messages_processed"],
            "errors": _metrics["errors"],
            "active_tasks": _metrics["active_tasks"],
            "recent_messages": _metrics["recent_messages"][:10]
        }
    
    @app.get("/api/tasks")
    async def get_active_tasks():
        """Get currently active tasks."""
        return {"tasks": _metrics["active_tasks"]}
    
    @app.post("/api/google-calendar")
    async def add_google_calendar(request: Request):
        """Add Google Calendar via CalDAV."""
        try:
            data = await request.json()
            email = data.get("email", "").strip()
            app_password = data.get("app_password", "").replace(" ", "")
            
            if not email or not app_password:
                raise HTTPException(status_code=400, detail="Email and app_password required")
            
            from koda.integrations.google_caldav import GoogleCalDAVClient
            from koda.config.loader import load_config, save_config
            
            client = GoogleCalDAVClient(email, app_password)
            success, message = client.test_connection()
            
            if not success:
                raise HTTPException(status_code=400, detail=message)
            
            # Save to config
            config = load_config()
            account = {
                "name": f"Google ({email.split('@')[0]})",
                "type": "google_caldav",
                "email": email,
                "password": app_password,
                "enabled": True,
                "capabilities": ["calendar"]
            }
            
            if not config.integrations.accounts:
                config.integrations.accounts = []
            
            # Update or add
            found = False
            for i, acc in enumerate(config.integrations.accounts):
                if (hasattr(acc, 'email') and acc.email == email) or (isinstance(acc, dict) and acc.get('email') == email):
                    config.integrations.accounts[i] = account
                    found = True
                    break
            
            if not found:
                config.integrations.accounts.append(account)
            
            save_config(config)
            
            calendars = client.list_calendars()
            return {"status": "ok", "calendars": [c['name'] for c in calendars]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/google-help")
    async def google_help():
        """Get Google Calendar setup instructions."""
        return {
            "instructions": """
## Google Calendar Setup (CalDAV met App Wachtwoord)

### Stap 1: 2-Stapsverificatie Inschakelen
Ga naar https://myaccount.google.com/security en zorg dat 2-Stapsverificatie AAN staat.

### Stap 2: App Wachtwoord Aanmaken

📖 **Uitgebreide handleiding:** https://support.google.com/mail/answer/185833

Kort:
1. Ga naar https://myaccount.google.com/apppasswords
2. Klik "App selecteren" → "Overige (aangepaste naam)"
3. Type: "Koda"
4. Klik "Genereren"
5. Je krijgt een 16-letter wachtwoord (bijv: abcd efgh ijkl mnop)

### Stap 3: Invullen
Vul je Gmail adres en het 16-letter App Wachtwoord in het formulier hieronder in.

### Voordelen
- Geen Google Cloud Console nodig
- Geen OAuth tokens die verlopen
- Werkt net als een mailclient
"""
        }
    
    # ============== Web UI ==============
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Main dashboard page."""
        return get_dashboard_html()
    
    return app


def _sanitize_config(config: dict) -> dict:
    """Remove sensitive fields from config."""
    sensitive_keys = ["password", "api_key", "secret", "token", "credentials"]
    
    def sanitize(obj):
        if isinstance(obj, dict):
            return {
                k: "[HIDDEN]" if any(s in k.lower() for s in sensitive_keys) else sanitize(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [sanitize(i) for i in obj]
        return obj
    
    return sanitize(config)


def _prepare_config_for_display(config: dict) -> dict:
    """Prepare config for display, showing indicators for sensitive fields."""
    sensitive_keys = ["password", "api_key", "secret", "token", "credentials"]
    
    def prepare(obj, path=""):
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if any(s in k.lower() for s in sensitive_keys) and v:
                    result[k] = {"_has_value": True, "_preview": str(v)[:4] + "..." if v else ""}
                else:
                    result[k] = prepare(v, f"{path}.{k}")
            return result
        elif isinstance(obj, list):
            return [prepare(i, path) for i in obj]
        return obj
    
    return prepare(config)


def get_dashboard_html() -> str:
    """Return the comprehensive dashboard HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Koda Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        .card { background: white; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 1.5rem; margin-bottom: 1rem; }
        .btn { padding: 0.5rem 1rem; border-radius: 0.375rem; font-weight: 500; transition: all 0.2s; cursor: pointer; }
        .btn-primary { background: #2563eb; color: white; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-danger:hover { background: #b91c1c; }
        .input { width: 100%; padding: 0.5rem 0.75rem; border: 1px solid #d1d5db; border-radius: 0.375rem; }
        .input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,0.2); }
        .badge { display: inline-block; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; }
        .badge-green { background: #dcfce7; color: #166534; }
        .badge-red { background: #fee2e2; color: #991b1b; }
        .badge-blue { background: #dbeafe; color: #1e40af; }
        .badge-yellow { background: #fef3c7; color: #92400e; }
        .stat-card { text-align: center; padding: 1rem; }
        .stat-value { font-size: 1.5rem; font-weight: 700; }
        .stat-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-white shadow-sm sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <span class="text-2xl">🐕</span>
                    <span class="ml-2 text-xl font-bold text-gray-800">Koda Dashboard</span>
                    <span class="ml-2 text-xs text-gray-400">v2.0</span>
                </div>
                <div class="flex items-center space-x-4">
                    <span id="uptime" class="text-sm text-gray-500"></span>
                    <span class="flex items-center">
                        <span class="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
                        <span class="text-sm text-gray-600">Running</span>
                    </span>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <!-- Metrics Row -->
        <div class="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
            <div class="card stat-card">
                <div class="stat-value text-blue-600" id="stat-messages">0</div>
                <div class="stat-label">Messages</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-green-600" id="stat-processed">0</div>
                <div class="stat-label">Processed</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-red-600" id="stat-errors">0</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-purple-600" id="stat-tasks">0</div>
                <div class="stat-label">Active Tasks</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-orange-600" id="stat-schedules">0</div>
                <div class="stat-label">Schedules</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-gray-600" id="stat-accounts">0</div>
                <div class="stat-label">Accounts</div>
            </div>
        </div>

        <!-- Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div class="card">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-gray-500">Assistant</p>
                        <p id="assistant-name" class="text-lg font-semibold">Loading...</p>
                        <p id="assistant-model" class="text-xs text-gray-400"></p>
                    </div>
                    <div class="text-3xl">🤖</div>
                </div>
            </div>
            <div class="card">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-gray-500">WhatsApp</p>
                        <p id="whatsapp-status" class="text-lg font-semibold">Loading...</p>
                        <p id="whatsapp-mode" class="text-xs text-gray-400"></p>
                    </div>
                    <div class="text-3xl">💬</div>
                </div>
            </div>
            <div class="card">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-gray-500">Brave Search</p>
                        <p id="brave-status" class="text-lg font-semibold">Loading...</p>
                        <p id="brave-preview" class="text-xs text-gray-400"></p>
                    </div>
                    <div class="text-3xl">🔍</div>
                </div>
            </div>
            <div class="card">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-gray-500">LinkedIn</p>
                        <p id="linkedin-status" class="text-lg font-semibold">Loading...</p>
                    </div>
                    <div class="text-3xl">💼</div>
                </div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="mb-6 border-b border-gray-200">
            <nav class="flex space-x-8">
                <button onclick="showTab('config')" class="tab-btn py-4 px-1 border-b-2 border-blue-500 font-medium text-blue-600">Configuration</button>
                <button onclick="showTab('accounts')" class="tab-btn py-4 px-1 border-b-2 border-transparent font-medium text-gray-500 hover:text-gray-700">Accounts</button>
                <button onclick="showTab('schedules')" class="tab-btn py-4 px-1 border-b-2 border-transparent font-medium text-gray-500 hover:text-gray-700">Schedules</button>
                <button onclick="showTab('integrations')" class="tab-btn py-4 px-1 border-b-2 border-transparent font-medium text-gray-500 hover:text-gray-700">Integrations</button>
                <button onclick="showTab('google')" class="tab-btn py-4 px-1 border-b-2 border-transparent font-medium text-gray-500 hover:text-gray-700">Google Calendar</button>
            </nav>
        </div>

        <!-- Config Tab -->
        <div id="tab-config" class="tab-content">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4 flex items-center"><span class="mr-2">👤</span> Assistant Settings</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Bot Name</label>
                            <input id="cfg-name" type="text" class="input" placeholder="Koda">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Your Name</label>
                            <input id="cfg-user-name" type="text" class="input" placeholder="Your name">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Language</label>
                            <select id="cfg-language" class="input">
                                <option value="en">English</option>
                                <option value="nl">Nederlands</option>
                                <option value="de">Deutsch</option>
                                <option value="fr">Français</option>
                                <option value="es">Español</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Personality</label>
                            <select id="cfg-personality" class="input">
                                <option value="professional">Professional</option>
                                <option value="friendly">Friendly</option>
                                <option value="concise">Concise</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">AI Model</label>
                            <input id="cfg-model" type="text" class="input" placeholder="anthropic/claude-sonnet-4-20250514">
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2 class="text-lg font-semibold mb-4 flex items-center"><span class="mr-2">💬</span> WhatsApp Settings</h2>
                    <div class="space-y-4">
                        <div class="flex items-center">
                            <input id="cfg-wa-enabled" type="checkbox" class="w-4 h-4 text-blue-600 rounded">
                            <label class="ml-2 text-sm text-gray-700">Enable WhatsApp</label>
                        </div>
                        <div class="flex items-center">
                            <input id="cfg-wa-botmode" type="checkbox" class="w-4 h-4 text-blue-600 rounded">
                            <label class="ml-2 text-sm text-gray-700">Bot Mode (respond to everyone)</label>
                        </div>
                        <div class="flex items-center">
                            <input id="cfg-wa-escalate" type="checkbox" class="w-4 h-4 text-blue-600 rounded">
                            <label class="ml-2 text-sm text-gray-700">Escalate to owner</label>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Owner Phone</label>
                            <input id="cfg-wa-owner" type="text" class="input" placeholder="+31612345678">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Allow From (comma-separated)</label>
                            <input id="cfg-wa-allowfrom" type="text" class="input" placeholder="+31612345678, +31687654321">
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2 class="text-lg font-semibold mb-4 flex items-center"><span class="mr-2">🔑</span> API Keys</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Brave Search API Key</label>
                            <div class="flex space-x-2">
                                <input id="cfg-brave-key" type="password" class="input flex-1" placeholder="Enter API key">
                                <button onclick="togglePassword('cfg-brave-key')" class="btn btn-primary">👁</button>
                            </div>
                            <p id="brave-key-status" class="text-xs text-gray-500 mt-1"></p>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2 class="text-lg font-semibold mb-4 flex items-center"><span class="mr-2">💼</span> LinkedIn Settings</h2>
                    <div class="space-y-4">
                        <div class="flex items-center">
                            <input id="cfg-li-enabled" type="checkbox" class="w-4 h-4 text-blue-600 rounded">
                            <label class="ml-2 text-sm text-gray-700">Enable LinkedIn</label>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">LinkedIn Email</label>
                            <input id="cfg-li-email" type="email" class="input" placeholder="your@email.com">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">LinkedIn Password</label>
                            <input id="cfg-li-password" type="password" class="input" placeholder="••••••••">
                        </div>
                    </div>
                </div>
            </div>
            <div class="mt-6">
                <button onclick="saveConfig()" class="btn btn-primary">💾 Save Configuration</button>
                <span id="save-status" class="ml-4 text-sm text-green-600 hidden">✓ Saved!</span>
            </div>
        </div>

        <!-- Accounts Tab -->
        <div id="tab-accounts" class="tab-content hidden">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">📧 Configured Accounts</h2>
                <div id="accounts-list" class="space-y-3">
                    <p class="text-gray-500">Loading...</p>
                </div>
            </div>
        </div>

        <!-- Schedules Tab -->
        <div id="tab-schedules" class="tab-content hidden">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">📅 Scheduled Tasks & Reminders</h2>
                <div id="schedules-list" class="space-y-3">
                    <p class="text-gray-500">Loading...</p>
                </div>
            </div>
        </div>

        <!-- Integrations Tab -->
        <div id="tab-integrations" class="tab-content hidden">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div class="card">
                    <h3 class="font-semibold mb-2">🔍 Brave Search</h3>
                    <p id="int-brave" class="text-sm text-gray-600">Loading...</p>
                </div>
                <div class="card">
                    <h3 class="font-semibold mb-2">💼 LinkedIn</h3>
                    <p id="int-linkedin" class="text-sm text-gray-600">Loading...</p>
                </div>
                <div class="card">
                    <h3 class="font-semibold mb-2">📅 Google Calendar</h3>
                    <p id="int-google" class="text-sm text-gray-600">Loading...</p>
                </div>
                <div class="card">
                    <h3 class="font-semibold mb-2">📧 Exchange</h3>
                    <p id="int-exchange" class="text-sm text-gray-600">Loading...</p>
                </div>
                <div class="card">
                    <h3 class="font-semibold mb-2">📆 CalDAV</h3>
                    <p id="int-caldav" class="text-sm text-gray-600">Loading...</p>
                </div>
            </div>
        </div>

        <!-- Google Calendar Tab -->
        <div id="tab-google" class="tab-content hidden">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">📅 Google Calendar Setup (Easy Mode)</h2>
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                    <p class="text-sm text-blue-800"><strong>📖 Help:</strong> <a href="https://support.google.com/mail/answer/185833" target="_blank" class="underline">How to create App Passwords</a></p>
                </div>
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Gmail Address</label>
                        <input id="google-email" type="email" class="input" placeholder="your.email@gmail.com">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">App Password (16 letters)</label>
                        <input id="google-password" type="password" class="input" placeholder="abcd efgh ijkl mnop">
                    </div>
                    <button onclick="addGoogleCalendar()" class="btn btn-primary">Connect Google Calendar</button>
                    <p id="google-status" class="text-sm"></p>
                </div>
            </div>
        </div>
    </main>

    <script>
        lucide.createIcons();
        let configData = {};

        async function loadStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                document.getElementById('assistant-name').textContent = data.assistant?.name || 'Koda';
                document.getElementById('assistant-model').textContent = data.assistant?.model || '';
                document.getElementById('whatsapp-status').textContent = data.whatsapp?.enabled ? 'Active' : 'Disabled';
                document.getElementById('whatsapp-mode').textContent = data.whatsapp?.bot_mode ? 'Bot Mode' : 'Restricted';
                document.getElementById('brave-status').textContent = data.api_keys?.brave ? 'Configured' : 'Not Set';
                document.getElementById('linkedin-status').textContent = data.integrations?.linkedin ? 'Active' : 'Disabled';
                document.getElementById('uptime').textContent = 'Uptime: ' + (data.metrics?.uptime || '0s');
                
                // Update stats
                document.getElementById('stat-messages').textContent = data.metrics?.messages_received || 0;
                document.getElementById('stat-processed').textContent = data.metrics?.messages_processed || 0;
                document.getElementById('stat-errors').textContent = data.metrics?.errors || 0;
                document.getElementById('stat-tasks').textContent = data.metrics?.active_tasks || 0;
                document.getElementById('stat-schedules').textContent = data.metrics?.scheduled_jobs || 0;
                document.getElementById('stat-accounts').textContent = data.integrations?.accounts || 0;
            } catch (e) {
                console.error('Failed to load status:', e);
            }
        }

        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                configData = await res.json();
                
                document.getElementById('cfg-name').value = configData.assistant?.name || '';
                document.getElementById('cfg-user-name').value = configData.assistant?.user_name || '';
                document.getElementById('cfg-language').value = configData.assistant?.language || 'en';
                document.getElementById('cfg-personality').value = configData.assistant?.personality || 'professional';
                document.getElementById('cfg-model').value = configData.model || '';
                
                document.getElementById('cfg-wa-enabled').checked = configData.channels?.whatsapp?.enabled || false;
                document.getElementById('cfg-wa-botmode').checked = configData.channels?.whatsapp?.bot_mode || false;
                document.getElementById('cfg-wa-escalate').checked = configData.channels?.whatsapp?.escalate_to_owner || false;
                document.getElementById('cfg-wa-owner').value = configData.channels?.whatsapp?.owner_phone || '';
                document.getElementById('cfg-wa-allowfrom').value = (configData.channels?.whatsapp?.allow_from || []).join(', ');
                
                document.getElementById('cfg-li-enabled').checked = configData.integrations?.linkedin?.enabled || false;
                document.getElementById('cfg-li-email').value = configData.integrations?.linkedin?.email || '';
                
                // Show Brave key status
                if (configData.tools?.brave_api_key) {
                    document.getElementById('brave-key-status').textContent = '✓ Key configured: ' + configData.tools.brave_api_key_preview;
                    document.getElementById('brave-key-status').className = 'text-xs text-green-600 mt-1';
                    document.getElementById('brave-preview').textContent = configData.tools.brave_api_key_preview;
                } else {
                    document.getElementById('brave-key-status').textContent = '✗ No key configured';
                    document.getElementById('brave-key-status').className = 'text-xs text-red-600 mt-1';
                }
                
                // Update integrations tab
                document.getElementById('int-brave').innerHTML = configData.tools?.brave_api_key ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-red">Not configured</span>';
                document.getElementById('int-linkedin').innerHTML = configData.integrations?.linkedin?.enabled ? '<span class="badge badge-green">Active</span> ' + configData.integrations.linkedin.email : '<span class="badge badge-red">Disabled</span>';
                document.getElementById('int-google').innerHTML = configData.integrations?.google?.enabled ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-yellow">Not configured</span>';
                document.getElementById('int-exchange').innerHTML = configData.integrations?.exchange?.enabled ? '<span class="badge badge-green">Active</span> ' + configData.integrations.exchange.email : '<span class="badge badge-red">Disabled</span>';
                document.getElementById('int-caldav').innerHTML = configData.integrations?.caldav?.enabled ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-red">Disabled</span>';
            } catch (e) {
                console.error('Failed to load config:', e);
            }
        }

        async function loadAccounts() {
            try {
                const res = await fetch('/api/accounts');
                const data = await res.json();
                const list = document.getElementById('accounts-list');
                
                if (data.accounts?.length) {
                    list.innerHTML = data.accounts.map(acc => `
                        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                            <div>
                                <span class="font-medium">${acc.name}</span>
                                <span class="ml-2 badge badge-blue">${acc.type}</span>
                                ${acc.email ? '<span class="ml-2 text-sm text-gray-500">' + acc.email + '</span>' : ''}
                            </div>
                            <div class="flex items-center space-x-2">
                                <span class="badge ${acc.enabled ? 'badge-green' : 'badge-red'}">${acc.enabled ? 'Active' : 'Disabled'}</span>
                                ${acc.capabilities?.length ? '<span class="text-xs text-gray-400">' + acc.capabilities.join(', ') + '</span>' : ''}
                            </div>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<div class="text-center py-8 text-gray-500"><p>No accounts configured yet.</p><p class="text-sm mt-2">Use WhatsApp commands like /addmail or /addgoogle to add accounts.</p></div>';
                }
            } catch (e) {
                console.error('Failed to load accounts:', e);
            }
        }

        async function loadSchedules() {
            try {
                const res = await fetch('/api/schedules');
                const data = await res.json();
                const list = document.getElementById('schedules-list');
                
                if (data.schedules?.length) {
                    list.innerHTML = data.schedules.map(s => `
                        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                            <div class="flex-1">
                                <span class="font-medium">${s.name || 'Unnamed'}</span>
                                <span class="ml-2 badge badge-blue">${s.type}</span>
                                <div class="text-sm text-gray-500 mt-1">
                                    <span>⏰ ${s.schedule}</span>
                                    ${s.next_run ? '<span class="ml-4">Next: ' + new Date(s.next_run).toLocaleString() + '</span>' : ''}
                                </div>
                            </div>
                            <button onclick="deleteSchedule('${s.id}')" class="btn btn-danger text-sm">Delete</button>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<div class="text-center py-8 text-gray-500"><p>No scheduled tasks.</p><p class="text-sm mt-2">Use natural language like "Remind me every Monday at 9am to check emails"</p></div>';
                }
            } catch (e) {
                console.error('Failed to load schedules:', e);
            }
        }

        async function saveConfig() {
            try {
                const allowFrom = document.getElementById('cfg-wa-allowfrom').value
                    .split(',').map(s => s.trim()).filter(s => s);
                
                const config = {
                    assistant: {
                        name: document.getElementById('cfg-name').value,
                        user_name: document.getElementById('cfg-user-name').value,
                        language: document.getElementById('cfg-language').value,
                        personality: document.getElementById('cfg-personality').value
                    },
                    model: document.getElementById('cfg-model').value,
                    channels: {
                        whatsapp: {
                            enabled: document.getElementById('cfg-wa-enabled').checked,
                            bot_mode: document.getElementById('cfg-wa-botmode').checked,
                            escalate_to_owner: document.getElementById('cfg-wa-escalate').checked,
                            owner_phone: document.getElementById('cfg-wa-owner').value,
                            allow_from: allowFrom
                        }
                    },
                    integrations: {
                        linkedin: {
                            enabled: document.getElementById('cfg-li-enabled').checked,
                            email: document.getElementById('cfg-li-email').value,
                            password: document.getElementById('cfg-li-password').value || undefined
                        }
                    },
                    tools: {}
                };
                
                const braveKey = document.getElementById('cfg-brave-key').value;
                if (braveKey) config.tools.brave_api_key = braveKey;
                
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                if (res.ok) {
                    document.getElementById('save-status').classList.remove('hidden');
                    setTimeout(() => document.getElementById('save-status').classList.add('hidden'), 3000);
                    loadStatus();
                    loadConfig();
                } else {
                    alert('Failed to save configuration');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function deleteSchedule(id) {
            if (!confirm('Delete this schedule?')) return;
            try {
                const res = await fetch('/api/schedules/' + id, { method: 'DELETE' });
                if (res.ok) loadSchedules();
                else alert('Failed to delete schedule');
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function addGoogleCalendar() {
            const email = document.getElementById('google-email').value;
            const password = document.getElementById('google-password').value.replace(/\\s/g, '');
            const status = document.getElementById('google-status');
            
            if (!email || !password) {
                status.textContent = '❌ Please fill in both fields';
                status.className = 'text-sm text-red-600';
                return;
            }
            
            status.textContent = '⏳ Connecting...';
            status.className = 'text-sm text-blue-600';
            
            try {
                const res = await fetch('/api/google-calendar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, app_password: password })
                });
                const data = await res.json();
                
                if (res.ok) {
                    status.textContent = '✅ Connected! Calendars: ' + data.calendars.join(', ');
                    status.className = 'text-sm text-green-600';
                    loadAccounts();
                } else {
                    status.textContent = '❌ ' + data.detail;
                    status.className = 'text-sm text-red-600';
                }
            } catch (e) {
                status.textContent = '❌ Error: ' + e.message;
                status.className = 'text-sm text-red-600';
            }
        }

        function togglePassword(id) {
            const input = document.getElementById(id);
            input.type = input.type === 'password' ? 'text' : 'password';
        }

        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('border-blue-500', 'text-blue-600');
                b.classList.add('border-transparent', 'text-gray-500');
            });
            
            document.getElementById('tab-' + name).classList.remove('hidden');
            event.target.classList.add('border-blue-500', 'text-blue-600');
            event.target.classList.remove('border-transparent', 'text-gray-500');
            
            if (name === 'accounts') loadAccounts();
            if (name === 'schedules') loadSchedules();
            if (name === 'integrations') loadConfig();
        }

        // Auto-refresh status every 30 seconds
        setInterval(loadStatus, 30000);
        
        // Initial load
        loadStatus();
        loadConfig();
    </script>
</body>
</html>'''


def run_dashboard(host: str = "0.0.0.0", port: int = 8081):
    """Run the dashboard server."""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_dashboard()
