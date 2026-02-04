"""Web Dashboard for Koda configuration and monitoring."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


def create_app() -> FastAPI:
    """Create the FastAPI dashboard application."""
    app = FastAPI(
        title="Koda Dashboard",
        description="Web interface for Koda configuration and monitoring",
        version="1.0.0"
    )
    
    # ============== API Routes ==============
    
    @app.get("/api/config")
    async def get_config():
        """Get current configuration."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            # Convert to dict, hiding sensitive fields
            return _sanitize_config(config.model_dump())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/config")
    async def update_config(request: Request):
        """Update configuration."""
        try:
            from koda.config.loader import load_config, save_config
            data = await request.json()
            config = load_config()
            
            # Update specific sections
            if "assistant" in data:
                for k, v in data["assistant"].items():
                    if hasattr(config.assistant, k):
                        setattr(config.assistant, k, v)
            
            if "channels" in data:
                if "whatsapp" in data["channels"]:
                    for k, v in data["channels"]["whatsapp"].items():
                        if hasattr(config.channels.whatsapp, k):
                            setattr(config.channels.whatsapp, k, v)
            
            if "integrations" in data:
                for k, v in data["integrations"].items():
                    if hasattr(config.integrations, k):
                        section = getattr(config.integrations, k)
                        if isinstance(v, dict):
                            for sk, sv in v.items():
                                if hasattr(section, sk):
                                    setattr(section, sk, sv)
            
            if "tools" in data:
                if "web" in data["tools"]:
                    if "search" in data["tools"]["web"]:
                        for k, v in data["tools"]["web"]["search"].items():
                            if hasattr(config.tools.web.search, k):
                                setattr(config.tools.web.search, k, v)
            
            save_config(config)
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/status")
    async def get_status():
        """Get system status."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            
            status = {
                "assistant": {
                    "name": config.assistant.name,
                    "model": config.assistant.model
                },
                "whatsapp": {
                    "enabled": config.channels.whatsapp.enabled,
                    "bot_mode": config.channels.whatsapp.bot_mode
                },
                "integrations": {
                    "linkedin": config.integrations.linkedin.enabled,
                    "accounts": len(config.integrations.accounts) if config.integrations.accounts else 0
                }
            }
            return status
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
                accounts.append({
                    "name": acc.name,
                    "type": acc.type,
                    "enabled": acc.enabled,
                    "capabilities": acc.capabilities
                })
            
            return {"accounts": accounts}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/schedules")
    async def get_schedules():
        """Get scheduled tasks."""
        try:
            schedule_file = Path.home() / ".koda" / "schedules.json"
            if schedule_file.exists():
                with open(schedule_file) as f:
                    return json.load(f)
            return {"schedules": []}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/schedules/{job_id}")
    async def delete_schedule(job_id: str):
        """Delete a scheduled task."""
        try:
            schedule_file = Path.home() / ".koda" / "schedules.json"
            if schedule_file.exists():
                with open(schedule_file) as f:
                    data = json.load(f)
                
                data["schedules"] = [s for s in data.get("schedules", []) if s.get("id") != job_id]
                
                with open(schedule_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                return {"status": "deleted", "id": job_id}
            raise HTTPException(status_code=404, detail="Schedule not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
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


def get_dashboard_html() -> str:
    """Return the dashboard HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Koda Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        .card { @apply bg-white rounded-lg shadow-md p-6 mb-4; }
        .btn { @apply px-4 py-2 rounded-md font-medium transition-colors; }
        .btn-primary { @apply bg-blue-600 text-white hover:bg-blue-700; }
        .btn-secondary { @apply bg-gray-200 text-gray-800 hover:bg-gray-300; }
        .input { @apply w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-white shadow-sm">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <span class="text-2xl">🐕</span>
                    <span class="ml-2 text-xl font-bold text-gray-800">Koda Dashboard</span>
                </div>
                <div class="flex items-center space-x-4">
                    <span id="status-indicator" class="flex items-center">
                        <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                        <span class="text-sm text-gray-600">Connected</span>
                    </span>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <!-- Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div class="card">
                <div class="flex items-center">
                    <div class="p-3 bg-blue-100 rounded-full">
                        <i data-lucide="bot" class="w-6 h-6 text-blue-600"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm text-gray-500">Assistant</p>
                        <p id="assistant-name" class="text-lg font-semibold">Loading...</p>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="flex items-center">
                    <div class="p-3 bg-green-100 rounded-full">
                        <i data-lucide="message-circle" class="w-6 h-6 text-green-600"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm text-gray-500">WhatsApp</p>
                        <p id="whatsapp-status" class="text-lg font-semibold">Loading...</p>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="flex items-center">
                    <div class="p-3 bg-purple-100 rounded-full">
                        <i data-lucide="link" class="w-6 h-6 text-purple-600"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm text-gray-500">Integrations</p>
                        <p id="integrations-count" class="text-lg font-semibold">Loading...</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="mb-6">
            <nav class="flex space-x-4">
                <button onclick="showTab('config')" class="tab-btn px-4 py-2 font-medium text-blue-600 border-b-2 border-blue-600">Configuration</button>
                <button onclick="showTab('accounts')" class="tab-btn px-4 py-2 font-medium text-gray-500 hover:text-gray-700">Accounts</button>
                <button onclick="showTab('schedules')" class="tab-btn px-4 py-2 font-medium text-gray-500 hover:text-gray-700">Schedules</button>
            </nav>
        </div>

        <!-- Config Tab -->
        <div id="tab-config" class="tab-content">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">Assistant Settings</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
                        <input id="cfg-name" type="text" class="input" placeholder="Koda">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Language</label>
                        <select id="cfg-language" class="input">
                            <option value="en">English</option>
                            <option value="nl">Nederlands</option>
                            <option value="de">Deutsch</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2 class="text-lg font-semibold mb-4">WhatsApp Settings</h2>
                <div class="space-y-4">
                    <div class="flex items-center">
                        <input id="cfg-wa-enabled" type="checkbox" class="w-4 h-4 text-blue-600">
                        <label class="ml-2 text-sm text-gray-700">Enable WhatsApp</label>
                    </div>
                    <div class="flex items-center">
                        <input id="cfg-wa-botmode" type="checkbox" class="w-4 h-4 text-blue-600">
                        <label class="ml-2 text-sm text-gray-700">Bot Mode (respond to everyone)</label>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Owner Phone</label>
                        <input id="cfg-wa-owner" type="text" class="input" placeholder="+31612345678">
                    </div>
                </div>
            </div>

            <div class="card">
                <h2 class="text-lg font-semibold mb-4">API Keys</h2>
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Brave Search API Key</label>
                        <input id="cfg-brave-key" type="password" class="input" placeholder="Enter API key">
                    </div>
                </div>
            </div>

            <button onclick="saveConfig()" class="btn btn-primary">Save Configuration</button>
        </div>

        <!-- Accounts Tab -->
        <div id="tab-accounts" class="tab-content hidden">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">Configured Accounts</h2>
                <div id="accounts-list" class="space-y-2">
                    <p class="text-gray-500">Loading...</p>
                </div>
            </div>
        </div>

        <!-- Schedules Tab -->
        <div id="tab-schedules" class="tab-content hidden">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">Scheduled Tasks</h2>
                <div id="schedules-list" class="space-y-2">
                    <p class="text-gray-500">Loading...</p>
                </div>
            </div>
        </div>
    </main>

    <script>
        // Initialize Lucide icons
        lucide.createIcons();

        // Load initial data
        async function loadStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('assistant-name').textContent = data.assistant?.name || 'Koda';
                document.getElementById('whatsapp-status').textContent = data.whatsapp?.enabled ? 'Active' : 'Disabled';
                document.getElementById('integrations-count').textContent = data.integrations?.accounts + ' accounts';
            } catch (e) {
                console.error('Failed to load status:', e);
            }
        }

        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                
                document.getElementById('cfg-name').value = data.assistant?.name || '';
                document.getElementById('cfg-language').value = data.assistant?.language || 'en';
                document.getElementById('cfg-wa-enabled').checked = data.channels?.whatsapp?.enabled || false;
                document.getElementById('cfg-wa-botmode').checked = data.channels?.whatsapp?.bot_mode || false;
                document.getElementById('cfg-wa-owner').value = data.channels?.whatsapp?.owner_phone || '';
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
                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded-md">
                            <div>
                                <span class="font-medium">${acc.name}</span>
                                <span class="ml-2 text-sm text-gray-500">${acc.type}</span>
                            </div>
                            <span class="text-sm ${acc.enabled ? 'text-green-600' : 'text-gray-400'}">
                                ${acc.enabled ? 'Active' : 'Disabled'}
                            </span>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<p class="text-gray-500">No accounts configured. Use WhatsApp commands to add accounts.</p>';
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
                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded-md">
                            <div>
                                <span class="font-medium">${s.name}</span>
                                <span class="ml-2 text-sm text-gray-500">${s.schedule}</span>
                            </div>
                            <button onclick="deleteSchedule('${s.id}')" class="text-red-600 hover:text-red-800">
                                Delete
                            </button>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<p class="text-gray-500">No scheduled tasks.</p>';
                }
            } catch (e) {
                console.error('Failed to load schedules:', e);
            }
        }

        async function saveConfig() {
            try {
                const config = {
                    assistant: {
                        name: document.getElementById('cfg-name').value,
                        language: document.getElementById('cfg-language').value
                    },
                    channels: {
                        whatsapp: {
                            enabled: document.getElementById('cfg-wa-enabled').checked,
                            bot_mode: document.getElementById('cfg-wa-botmode').checked,
                            owner_phone: document.getElementById('cfg-wa-owner').value
                        }
                    }
                };
                
                const braveKey = document.getElementById('cfg-brave-key').value;
                if (braveKey && braveKey !== '[HIDDEN]') {
                    config.tools = { web: { search: { api_key: braveKey } } };
                }
                
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                if (res.ok) {
                    alert('Configuration saved!');
                    loadStatus();
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
                await fetch('/api/schedules/' + id, { method: 'DELETE' });
                loadSchedules();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('text-blue-600', 'border-b-2', 'border-blue-600');
                b.classList.add('text-gray-500');
            });
            
            document.getElementById('tab-' + name).classList.remove('hidden');
            event.target.classList.add('text-blue-600', 'border-b-2', 'border-blue-600');
            event.target.classList.remove('text-gray-500');
            
            if (name === 'accounts') loadAccounts();
            if (name === 'schedules') loadSchedules();
        }

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
