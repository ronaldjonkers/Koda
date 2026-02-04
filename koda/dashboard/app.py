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


def _check_linkedin_session() -> bool:
    """Check if LinkedIn browser session exists."""
    browser_path = Path.home() / ".koda" / "linkedin_browser"
    if browser_path.exists():
        session_files = list(browser_path.glob("**/Cookies*")) + list(browser_path.glob("**/Local Storage*"))
        return len(session_files) > 0
    return False


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
                    "linkedin": _check_linkedin_session(),
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
    
    @app.get("/api/linkedin/status")
    async def get_linkedin_status():
        """Get LinkedIn session status."""
        browser_path = Path.home() / ".koda" / "linkedin_browser"
        style_path = Path.home() / ".koda" / "linkedin_style.json"
        
        session_active = False
        style_learned = False
        style_info = None
        
        if browser_path.exists():
            session_files = list(browser_path.glob("**/Cookies*")) + list(browser_path.glob("**/Local Storage*"))
            session_active = len(session_files) > 0
        
        if style_path.exists():
            try:
                with open(style_path) as f:
                    style_data = json.load(f)
                style_learned = True
                style_info = {
                    "language": style_data.get("language", "Unknown"),
                    "tone": style_data.get("tone", "Unknown")
                }
            except:
                pass
        
        return {
            "session_active": session_active,
            "style_learned": style_learned,
            "style_info": style_info,
            "setup_command": "koda setup-linkedin"
        }
    
    @app.get("/api/accounts")
    async def get_accounts():
        """Get configured accounts."""
        try:
            from koda.config.loader import load_config
            config = load_config()
            accounts = []
            
            # Get accounts from integrations.accounts list
            for acc in (config.integrations.accounts or []):
                if hasattr(acc, 'model_dump'):
                    acc_dict = acc.model_dump()
                elif isinstance(acc, dict):
                    acc_dict = acc
                else:
                    acc_dict = {}
                
                acc_data = {
                    "name": acc_dict.get('name', 'Unknown'),
                    "type": acc_dict.get('type', 'unknown'),
                    "enabled": acc_dict.get('enabled', True),
                    "capabilities": acc_dict.get('capabilities', []),
                    "email": acc_dict.get('email', ''),
                    "server": acc_dict.get('server', '')
                }
                accounts.append(acc_data)
            
            # Also check legacy exchange config
            if config.integrations.exchange.enabled:
                accounts.append({
                    "name": "Exchange (legacy)",
                    "type": "exchange",
                    "enabled": True,
                    "capabilities": ["email", "calendar", "contacts"],
                    "email": config.integrations.exchange.email,
                    "server": config.integrations.exchange.server
                })
            
            return {"accounts": accounts, "count": len(accounts)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/accounts")
    async def add_account(request: Request):
        """Add a new account."""
        try:
            from koda.config.loader import load_config, save_config
            data = await request.json()
            
            account = {
                "name": data.get("name", ""),
                "type": data.get("type", ""),
                "enabled": True,
                "email": data.get("email", ""),
                "password": data.get("password", ""),
                "server": data.get("server", ""),
                "capabilities": data.get("capabilities", [])
            }
            
            # Validate required fields
            if not account["name"] or not account["type"] or not account["email"]:
                raise HTTPException(status_code=400, detail="name, type, and email are required")
            
            config = load_config()
            if not config.integrations.accounts:
                config.integrations.accounts = []
            
            # Check if account already exists
            for i, acc in enumerate(config.integrations.accounts):
                acc_email = getattr(acc, 'email', acc.get('email', '')) if hasattr(acc, 'email') or isinstance(acc, dict) else ''
                if acc_email == account["email"]:
                    config.integrations.accounts[i] = account
                    save_config(config)
                    return {"status": "updated", "account": account["name"]}
            
            config.integrations.accounts.append(account)
            save_config(config)
            return {"status": "created", "account": account["name"]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/accounts/{email}")
    async def delete_account(email: str):
        """Delete an account by email."""
        try:
            from koda.config.loader import load_config, save_config
            from urllib.parse import unquote
            
            email = unquote(email)
            config = load_config()
            
            if not config.integrations.accounts:
                raise HTTPException(status_code=404, detail="No accounts found")
            
            original_count = len(config.integrations.accounts)
            config.integrations.accounts = [
                acc for acc in config.integrations.accounts
                if (getattr(acc, 'email', acc.get('email', '')) if hasattr(acc, 'email') or isinstance(acc, dict) else '') != email
            ]
            
            if len(config.integrations.accounts) < original_count:
                save_config(config)
                return {"status": "deleted", "email": email}
            
            raise HTTPException(status_code=404, detail="Account not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/system-metrics")
    async def get_system_metrics():
        """Get system metrics (CPU, memory, load)."""
        try:
            import os
            metrics = {
                "cpu_percent": 0,
                "memory_percent": 0,
                "memory_used_mb": 0,
                "memory_total_mb": 0,
                "load_1m": 0,
                "load_5m": 0,
                "load_15m": 0,
                "process_memory_mb": 0
            }
            
            # Try to get system metrics with psutil if available
            try:
                import psutil
                metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                mem = psutil.virtual_memory()
                metrics["memory_percent"] = mem.percent
                metrics["memory_used_mb"] = round(mem.used / 1024 / 1024)
                metrics["memory_total_mb"] = round(mem.total / 1024 / 1024)
                
                # Process memory
                process = psutil.Process(os.getpid())
                metrics["process_memory_mb"] = round(process.memory_info().rss / 1024 / 1024)
            except ImportError:
                pass
            
            # Load average (Unix only)
            try:
                load = os.getloadavg()
                metrics["load_1m"] = round(load[0], 2)
                metrics["load_5m"] = round(load[1], 2)
                metrics["load_15m"] = round(load[2], 2)
            except (OSError, AttributeError):
                pass
            
            return metrics
        except Exception as e:
            return {"error": str(e)}
    
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
    
    @app.get("/api/google-workspace/status")
    async def google_workspace_status():
        """Get Google Workspace connection status."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            
            if status["authorized"]:
                try:
                    calendars = client.list_calendars()
                    status["calendars"] = [{"id": c.id, "name": c.name, "primary": c.is_primary} for c in calendars]
                except:
                    status["calendars"] = []
            
            return status
        except ImportError:
            return {"configured": False, "authorized": False, "error": "Google API libraries not installed"}
        except Exception as e:
            return {"configured": False, "authorized": False, "error": str(e)}
    
    @app.get("/api/google-workspace/auth-url")
    async def google_workspace_auth_url(request: Request):
        """Get Google OAuth authorization URL."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            
            # Get the base URL for redirect
            host = request.headers.get("host", "localhost:8081")
            scheme = request.headers.get("x-forwarded-proto", "http")
            redirect_uri = f"{scheme}://{host}/api/google-workspace/callback"
            
            client = GoogleWorkspaceClient()
            
            if not client.is_configured:
                raise HTTPException(
                    status_code=400, 
                    detail="Google credentials not configured. Download google_credentials.json to ~/.koda/"
                )
            
            auth_url = client.get_authorization_url(redirect_uri)
            return {"auth_url": auth_url, "redirect_uri": redirect_uri}
        except HTTPException:
            raise
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/google-workspace/callback")
    async def google_workspace_callback(code: str = None, error: str = None):
        """Handle OAuth callback from Google."""
        from fastapi.responses import RedirectResponse
        
        if error:
            return RedirectResponse(url=f"/?google_error={error}")
        
        if not code:
            return RedirectResponse(url="/?google_error=no_code")
        
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            
            # Use same redirect URI as auth-url
            client = GoogleWorkspaceClient()
            # Note: redirect_uri must match exactly what was used in get_authorization_url
            # This is tricky in a callback, so we use a fixed localhost URL
            redirect_uri = "http://localhost:8081/api/google-workspace/callback"
            
            if client.authorize_with_code(code, redirect_uri):
                return RedirectResponse(url="/?google_success=true")
            else:
                return RedirectResponse(url="/?google_error=auth_failed")
        except Exception as e:
            logger.error(f"Google OAuth callback error: {e}")
            return RedirectResponse(url=f"/?google_error={str(e)}")
    
    @app.post("/api/google-workspace/test")
    async def google_workspace_test():
        """Test Google Workspace connection."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            success, message = client.test_connection()
            
            if success:
                calendars = client.list_calendars()
                return {
                    "status": "ok",
                    "message": message,
                    "calendars": [{"id": c.id, "name": c.name, "primary": c.is_primary, "role": c.access_role} for c in calendars]
                }
            else:
                raise HTTPException(status_code=400, detail=message)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
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
        <!-- System Metrics Row -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div class="card stat-card">
                <div class="stat-value text-blue-600" id="sys-cpu">0%</div>
                <div class="stat-label">CPU</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-green-600" id="sys-memory">0%</div>
                <div class="stat-label">Memory</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-purple-600" id="sys-load">0.0</div>
                <div class="stat-label">Load (1m)</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value text-orange-600" id="sys-process">0 MB</div>
                <div class="stat-label">Koda Memory</div>
            </div>
        </div>

        <!-- App Metrics Row -->
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
                        <div id="linkedin-status-box" class="p-3 bg-gray-50 rounded-lg">
                            <p class="text-sm text-gray-600">Status: <span id="cfg-li-status" class="font-medium">Checking...</span></p>
                        </div>
                        <div class="bg-blue-50 p-4 rounded-lg">
                            <p class="text-sm text-blue-800 font-medium mb-2">🔗 Browser-based Login</p>
                            <p class="text-sm text-blue-700 mb-3">LinkedIn uses browser session for stable automation. Run this command in terminal:</p>
                            <code class="block bg-blue-100 p-2 rounded text-sm font-mono">koda setup-linkedin</code>
                        </div>
                        <div class="text-sm text-gray-500">
                            <p class="font-medium mb-1">Features:</p>
                            <ul class="list-disc list-inside space-y-1">
                                <li>No 2FA issues</li>
                                <li>Posting with images</li>
                                <li>Analytics access</li>
                                <li>Style learning</li>
                            </ul>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="checkLinkedInStatus()" class="btn btn-secondary text-sm">🔄 Refresh Status</button>
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
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">📧 Configured Accounts</h2>
                    <div id="accounts-list" class="space-y-3">
                        <p class="text-gray-500">Loading...</p>
                    </div>
                </div>
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">➕ Add Account</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Account Name</label>
                            <input id="acc-name" type="text" class="input" placeholder="Work Email">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Type</label>
                            <select id="acc-type" class="input" onchange="updateAccountFields()">
                                <option value="exchange">Exchange / Office 365</option>
                                <option value="google_caldav">Google (CalDAV)</option>
                                <option value="imap">IMAP (Email only)</option>
                                <option value="caldav">CalDAV (Calendar only)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                            <input id="acc-email" type="email" class="input" placeholder="you@company.com">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Password / App Password</label>
                            <input id="acc-password" type="password" class="input" placeholder="••••••••">
                        </div>
                        <div id="acc-server-field">
                            <label class="block text-sm font-medium text-gray-700 mb-1">Server (Exchange only)</label>
                            <input id="acc-server" type="text" class="input" placeholder="outlook.office365.com">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Capabilities</label>
                            <div class="flex space-x-4">
                                <label class="flex items-center">
                                    <input type="checkbox" id="acc-cap-email" class="w-4 h-4 text-blue-600 rounded" checked>
                                    <span class="ml-2 text-sm">Email</span>
                                </label>
                                <label class="flex items-center">
                                    <input type="checkbox" id="acc-cap-calendar" class="w-4 h-4 text-blue-600 rounded" checked>
                                    <span class="ml-2 text-sm">Calendar</span>
                                </label>
                                <label class="flex items-center">
                                    <input type="checkbox" id="acc-cap-contacts" class="w-4 h-4 text-blue-600 rounded">
                                    <span class="ml-2 text-sm">Contacts</span>
                                </label>
                            </div>
                        </div>
                        <button onclick="addAccount()" class="btn btn-primary">➕ Add Account</button>
                        <p id="acc-status" class="text-sm"></p>
                    </div>
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

        <!-- Google Workspace Tab -->
        <div id="tab-google" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Google Workspace Status -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">� Google Workspace Status</h2>
                    <div id="google-ws-status" class="space-y-3">
                        <p class="text-gray-500">Loading...</p>
                    </div>
                </div>
                
                <!-- Google Workspace Setup (OAuth) -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">🔐 Google Workspace Setup (Recommended)</h2>
                    <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                        <p class="text-sm text-green-800"><strong>✨ Volledige toegang:</strong> Gmail, Calendar (incl. shared), Meet links</p>
                    </div>
                    <div class="space-y-4">
                        <p class="text-sm text-gray-600">Verbind je Google account via OAuth voor volledige toegang tot Gmail, Calendar en Meet.</p>
                        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm">
                            <strong>Vereist:</strong> google_credentials.json in ~/.koda/<br>
                            <a href="https://console.cloud.google.com/" target="_blank" class="text-blue-600 underline">Google Cloud Console</a> → APIs & Services → Credentials
                        </div>
                        <button onclick="connectGoogleWorkspace()" class="btn btn-primary w-full">🔗 Connect Google Workspace</button>
                        <button onclick="testGoogleWorkspace()" class="btn btn-secondary w-full">🧪 Test Connection</button>
                        <p id="google-ws-connect-status" class="text-sm"></p>
                    </div>
                </div>
                
                <!-- Google CalDAV (Simple) -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">📅 Google Calendar (Simple Mode)</h2>
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                        <p class="text-sm text-blue-800"><strong>📖 Alleen Calendar:</strong> Gebruikt App Password, geen OAuth nodig</p>
                    </div>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Gmail Address</label>
                            <input id="google-email" type="email" class="input" placeholder="your.email@gmail.com">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">App Password (16 letters)</label>
                            <input id="google-password" type="password" class="input" placeholder="abcd efgh ijkl mnop">
                            <p class="text-xs text-gray-500 mt-1"><a href="https://myaccount.google.com/apppasswords" target="_blank" class="text-blue-600 underline">Get App Password</a></p>
                        </div>
                        <button onclick="addGoogleCalendar()" class="btn btn-secondary w-full">Connect Calendar Only</button>
                        <p id="google-status" class="text-sm"></p>
                    </div>
                </div>
                
                <!-- Calendars List -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">📆 Connected Calendars</h2>
                    <div id="google-calendars-list" class="space-y-2">
                        <p class="text-gray-500">Connect Google Workspace to see calendars</p>
                    </div>
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
                
                // Load LinkedIn status separately
                checkLinkedInStatus();
                
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
                // LinkedIn status is set by checkLinkedInStatus()
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
                            <div class="flex-1">
                                <span class="font-medium">${acc.name}</span>
                                <span class="ml-2 badge badge-blue">${acc.type}</span>
                                ${acc.email ? '<div class="text-sm text-gray-500 mt-1">' + acc.email + (acc.server ? ' (' + acc.server + ')' : '') + '</div>' : ''}
                                ${acc.capabilities?.length ? '<div class="text-xs text-gray-400 mt-1">' + acc.capabilities.join(', ') + '</div>' : ''}
                            </div>
                            <div class="flex items-center space-x-2">
                                <span class="badge ${acc.enabled ? 'badge-green' : 'badge-red'}">${acc.enabled ? 'Active' : 'Disabled'}</span>
                                <button onclick="deleteAccount('${acc.email}')" class="text-red-600 hover:text-red-800 text-sm">🗑️</button>
                            </div>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<div class="text-center py-8 text-gray-500"><p>No accounts configured yet.</p><p class="text-sm mt-2">Add an account using the form on the right.</p></div>';
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

        async function checkLinkedInStatus() {
            try {
                const res = await fetch('/api/linkedin/status');
                const data = await res.json();
                
                const statusEl = document.getElementById('cfg-li-status');
                const intEl = document.getElementById('int-linkedin');
                
                if (data.session_active) {
                    statusEl.innerHTML = '<span class="text-green-600">✓ Sessie actief</span>';
                    if (data.style_learned && data.style_info) {
                        statusEl.innerHTML += ` <span class="text-gray-500">(${data.style_info.language}, ${data.style_info.tone})</span>`;
                    }
                    intEl.innerHTML = '<span class="badge badge-green">Active</span> Browser sessie';
                } else {
                    statusEl.innerHTML = '<span class="text-red-600">✗ Niet ingelogd</span>';
                    intEl.innerHTML = '<span class="badge badge-red">Not configured</span>';
                }
            } catch (e) {
                console.error('Failed to check LinkedIn status:', e);
                document.getElementById('cfg-li-status').textContent = 'Error checking status';
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
                        // LinkedIn is configured via CLI, not dashboard
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
            if (name === 'google') loadGoogleWorkspaceStatus();
        }

        async function loadSystemMetrics() {
            try {
                const res = await fetch('/api/system-metrics');
                const data = await res.json();
                
                document.getElementById('sys-cpu').textContent = data.cpu_percent + '%';
                document.getElementById('sys-memory').textContent = data.memory_percent + '%';
                document.getElementById('sys-load').textContent = data.load_1m;
                document.getElementById('sys-process').textContent = data.process_memory_mb + ' MB';
            } catch (e) {
                console.error('Failed to load system metrics:', e);
            }
        }

        async function addAccount() {
            const status = document.getElementById('acc-status');
            const capabilities = [];
            if (document.getElementById('acc-cap-email').checked) capabilities.push('email');
            if (document.getElementById('acc-cap-calendar').checked) capabilities.push('calendar');
            if (document.getElementById('acc-cap-contacts').checked) capabilities.push('contacts');
            
            const account = {
                name: document.getElementById('acc-name').value,
                type: document.getElementById('acc-type').value,
                email: document.getElementById('acc-email').value,
                password: document.getElementById('acc-password').value,
                server: document.getElementById('acc-server').value,
                capabilities: capabilities
            };
            
            if (!account.name || !account.email) {
                status.textContent = '❌ Name and email are required';
                status.className = 'text-sm text-red-600';
                return;
            }
            
            status.textContent = '⏳ Adding account...';
            status.className = 'text-sm text-blue-600';
            
            try {
                const res = await fetch('/api/accounts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(account)
                });
                const data = await res.json();
                
                if (res.ok) {
                    status.textContent = '✅ Account ' + data.status + ': ' + account.name;
                    status.className = 'text-sm text-green-600';
                    loadAccounts();
                    // Clear form
                    document.getElementById('acc-name').value = '';
                    document.getElementById('acc-email').value = '';
                    document.getElementById('acc-password').value = '';
                } else {
                    status.textContent = '❌ ' + data.detail;
                    status.className = 'text-sm text-red-600';
                }
            } catch (e) {
                status.textContent = '❌ Error: ' + e.message;
                status.className = 'text-sm text-red-600';
            }
        }

        async function deleteAccount(email) {
            if (!confirm('Delete account ' + email + '?')) return;
            try {
                const res = await fetch('/api/accounts/' + encodeURIComponent(email), { method: 'DELETE' });
                if (res.ok) loadAccounts();
                else alert('Failed to delete account');
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function updateAccountFields() {
            const type = document.getElementById('acc-type').value;
            const serverField = document.getElementById('acc-server-field');
            serverField.style.display = type === 'exchange' ? 'block' : 'none';
        }

        // Google Workspace functions
        async function loadGoogleWorkspaceStatus() {
            try {
                const res = await fetch('/api/google-workspace/status');
                const data = await res.json();
                const statusDiv = document.getElementById('google-ws-status');
                const calendarsList = document.getElementById('google-calendars-list');
                
                if (data.authorized) {
                    statusDiv.innerHTML = `
                        <div class="flex items-center space-x-2">
                            <span class="badge badge-green">Connected</span>
                            <span class="text-sm text-gray-600">${data.email || ''}</span>
                        </div>
                        <p class="text-sm text-gray-500">${data.calendars?.length || 0} calendars available</p>
                    `;
                    
                    if (data.calendars?.length) {
                        calendarsList.innerHTML = data.calendars.map(c => `
                            <div class="flex items-center justify-between p-2 bg-gray-50 rounded">
                                <span>${c.name}</span>
                                ${c.primary ? '<span class="badge badge-blue text-xs">Primary</span>' : ''}
                            </div>
                        `).join('');
                    }
                } else if (data.configured) {
                    statusDiv.innerHTML = `
                        <div class="flex items-center space-x-2">
                            <span class="badge badge-yellow">Not Authorized</span>
                        </div>
                        <p class="text-sm text-gray-500">Credentials file found. Click "Connect" to authorize.</p>
                    `;
                } else {
                    statusDiv.innerHTML = `
                        <div class="flex items-center space-x-2">
                            <span class="badge badge-red">Not Configured</span>
                        </div>
                        <p class="text-sm text-gray-500">Download google_credentials.json to ~/.koda/</p>
                        ${data.error ? '<p class="text-xs text-red-500">' + data.error + '</p>' : ''}
                    `;
                }
            } catch (e) {
                console.error('Failed to load Google status:', e);
            }
        }

        async function connectGoogleWorkspace() {
            const status = document.getElementById('google-ws-connect-status');
            status.textContent = '⏳ Getting authorization URL...';
            status.className = 'text-sm text-blue-600';
            
            try {
                const res = await fetch('/api/google-workspace/auth-url');
                const data = await res.json();
                
                if (res.ok && data.auth_url) {
                    status.textContent = '🔗 Opening Google login...';
                    window.open(data.auth_url, '_blank');
                    status.innerHTML = '⏳ Waiting for authorization... <a href="' + data.auth_url + '" target="_blank" class="text-blue-600 underline">Click here if popup blocked</a>';
                } else {
                    status.textContent = '❌ ' + (data.detail || 'Failed to get auth URL');
                    status.className = 'text-sm text-red-600';
                }
            } catch (e) {
                status.textContent = '❌ Error: ' + e.message;
                status.className = 'text-sm text-red-600';
            }
        }

        async function testGoogleWorkspace() {
            const status = document.getElementById('google-ws-connect-status');
            status.textContent = '⏳ Testing connection...';
            status.className = 'text-sm text-blue-600';
            
            try {
                const res = await fetch('/api/google-workspace/test', { method: 'POST' });
                const data = await res.json();
                
                if (res.ok) {
                    status.textContent = '✅ ' + data.message;
                    status.className = 'text-sm text-green-600';
                    loadGoogleWorkspaceStatus();
                } else {
                    status.textContent = '❌ ' + (data.detail || 'Test failed');
                    status.className = 'text-sm text-red-600';
                }
            } catch (e) {
                status.textContent = '❌ Error: ' + e.message;
                status.className = 'text-sm text-red-600';
            }
        }

        // Check for OAuth callback result
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('google_success')) {
            alert('✅ Google Workspace connected successfully!');
            window.history.replaceState({}, document.title, '/');
            loadGoogleWorkspaceStatus();
        } else if (urlParams.get('google_error')) {
            alert('❌ Google connection failed: ' + urlParams.get('google_error'));
            window.history.replaceState({}, document.title, '/');
        }

        // Auto-refresh status every 30 seconds
        setInterval(loadStatus, 30000);
        setInterval(loadSystemMetrics, 10000);
        
        // Initial load
        loadStatus();
        loadConfig();
        loadSystemMetrics();
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
