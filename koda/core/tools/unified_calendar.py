"""Unified calendar tool with multi-provider support, Google Meet, and proactive reminders.

This tool provides:
- Multi-calendar support (Google, Exchange, CalDAV)
- Automatic shared calendar discovery
- Proactive appointment reminders
- WhatsApp notification integration
- Smart conflict detection
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class UnifiedCalendarTool(BaseTool):
    """
    Unified calendar tool that supports multiple named calendar accounts with intelligent features.
    
    Features:
    - Multiple named calendar accounts (e.g., "Werk", "Privé", "Familie")
    - Automatic shared calendar discovery and access
    - Proactive WhatsApp reminders before appointments
    - Smart conflict detection when scheduling
    - Google Meet link generation
    - Cross-calendar event aggregation
    
    The tool automatically detects Google Workspace connections and includes all
    accessible calendars including shared ones.
    """
    
    name = "calendar"
    description = """Schedule and manage calendar events across multiple calendar accounts.

This tool provides intelligent calendar management with automatic shared calendar discovery,
proactive reminders, and conflict detection.

Calendar Selection:
- Use 'calendars' action first to see available calendars
- Calendar names are user-defined (e.g., "Werk Google", "Privé", "Team Kalender")
- Shared calendars are automatically discovered and accessible

Actions:
- list: List upcoming events from all calendars (includes shared)
- today: Get today's events from all calendars
- week: Get this week's events
- create: Create a new event with conflict checking
- update: Update an existing event
- delete: Delete an event
- calendars: List all available calendars with their names and types
- conflicts: Check for scheduling conflicts
- upcoming: Get events in the next N hours (default: 24)

Smart Features:
- Automatically includes shared calendars from Google Workspace
- Checks for conflicts before creating events
- Can send WhatsApp reminders before appointments
- Auto-discovers all accessible calendars

Parameters for 'create':
- summary: Event title (required)
- start: Start datetime ISO format (required)
- end: End datetime ISO format (required)
- calendar: Calendar NAME to use (e.g., "Werk", "Privé")
- description: Event description
- location: Event location
- attendees: List of attendee email addresses
- add_meet_link: Add Google Meet link (Google calendars only)
- whatsapp_reminder: Minutes before event to send reminder (e.g., 15, 30, 60)
- check_conflicts: Check for conflicts before creating (default: true)

Parameters for 'upcoming':
- hours: Number of hours to look ahead (default: 24)

Parameters for 'conflicts':
- start: Start datetime to check
- end: End datetime to check
- calendar: Specific calendar to check (optional, checks all if not specified)
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "today", "week", "create", "update", "delete", "calendars", "conflicts", "upcoming"],
                "description": "Action to perform"
            },
            "event_id": {
                "type": "string",
                "description": "Event ID for update/delete actions"
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead (for list action)"
            },
            "hours": {
                "type": "integer",
                "description": "Number of hours to look ahead (for upcoming action)"
            },
            "calendar": {
                "type": "string",
                "description": "Calendar to use: specific name like 'Werk Google', 'Privé', etc."
            },
            "summary": {
                "type": "string",
                "description": "Event title (for create action)"
            },
            "start": {
                "type": "string",
                "description": "Start datetime ISO format (for create/conflicts action)"
            },
            "end": {
                "type": "string",
                "description": "End datetime ISO format (for create/conflicts action)"
            },
            "description": {
                "type": "string",
                "description": "Event description"
            },
            "location": {
                "type": "string",
                "description": "Event location"
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses"
            },
            "add_meet_link": {
                "type": "boolean",
                "description": "Add Google Meet link (only for Google Calendar events)"
            },
            "whatsapp_reminder": {
                "type": "integer",
                "description": "Minutes before event to send WhatsApp reminder (e.g., 15, 30, 60)"
            },
            "reminder_phone": {
                "type": "string",
                "description": "Phone number for WhatsApp reminder"
            },
            "check_conflicts": {
                "type": "boolean",
                "description": "Check for conflicts before creating event"
            }
        },
        "required": ["action"]
    }
    
    def __init__(
        self,
        calendar_accounts: list[dict] | None = None,
        # Legacy parameters for backward compatibility
        google_enabled: bool = False,
        google_credentials_file: str = "",
        google_token_file: str = "",
        exchange_enabled: bool = False,
        exchange_email: str = "",
        exchange_password: str = "",
        exchange_server: str = "",
        caldav_enabled: bool = False,
        caldav_url: str = "",
        caldav_username: str = "",
        caldav_password: str = "",
        reminder_service: Any = None,
        default_reminder_phone: str = ""
    ):
        # Named accounts (new system)
        self.calendar_accounts = calendar_accounts or []
        
        # Legacy single-account support (convert to named accounts if no named accounts)
        if not self.calendar_accounts:
            if google_enabled:
                self.calendar_accounts.append({
                    "name": "Google",
                    "type": "google",
                    "credentials_file": google_credentials_file,
                    "token_file": google_token_file,
                })
            if exchange_enabled:
                self.calendar_accounts.append({
                    "name": "Exchange",
                    "type": "exchange",
                    "email": exchange_email,
                    "password": exchange_password,
                    "server": exchange_server,
                })
            if caldav_enabled:
                self.calendar_accounts.append({
                    "name": "CalDAV",
                    "type": "caldav",
                    "url": caldav_url,
                    "username": caldav_username,
                    "password": caldav_password,
                })
        
        self.reminder_service = reminder_service
        self.default_reminder_phone = default_reminder_phone
        
        # Clients cache by account name
        self._clients: dict[str, Any] = {}
        
        # Check if Google Workspace is available (for Meet links and shared calendars)
        self._google_workspace_client = None
        self._google_workspace_available = self._check_google_workspace()
        
        # Auto-add Google Workspace with all calendars if connected
        if self._google_workspace_available:
            self._add_google_workspace_calendars()
    
    def _check_google_workspace(self) -> bool:
        """Check if Google Workspace is configured and authorized."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            logger.debug(f"Google Workspace status: {status}")
            if status.get("authorized"):
                self._google_workspace_client = client
                logger.info("✅ Google Workspace is authorized and available")
                return True
            else:
                logger.debug(f"Google Workspace not authorized: {status}")
        except Exception as e:
            logger.debug(f"Google Workspace check failed: {e}")
        return False
    
    def _add_google_workspace_calendars(self) -> None:
        """Add Google Workspace with all discovered calendars including shared ones."""
        try:
            if not self._google_workspace_client:
                return
            
            # Get all calendars including shared ones
            all_calendars = self._google_workspace_client.list_calendars(use_cache=False)
            
            # Check if we already have Google accounts
            existing_google = [acc for acc in self.calendar_accounts if acc.get("type") == "google"]
            
            if not existing_google:
                # Add each calendar as a separate account for easy selection
                for cal in all_calendars:
                    account_name = cal.name
                    if cal.is_shared:
                        account_name = f"{cal.name} (Shared)"
                    
                    # Check if this calendar is already added
                    existing = [acc for acc in self.calendar_accounts if acc.get("name") == account_name]
                    if not existing:
                        self.calendar_accounts.append({
                            "name": account_name,
                            "type": "google_workspace",
                            "calendar_id": cal.id,
                            "is_shared": cal.is_shared,
                            "access_role": cal.access_role,
                            "auto_added": True
                        })
                        logger.info(f"Added calendar: {account_name}")
                
                logger.info(f"Auto-added {len(all_calendars)} Google calendars ({sum(1 for c in all_calendars if c.is_shared)} shared)")
        except Exception as e:
            logger.warning(f"Failed to add Google Workspace calendars: {e}")
    
    def _get_client_for_account(self, account: dict) -> Any:
        """Get or create a client for a named account."""
        name = account.get("name", "")
        if name in self._clients:
            return self._clients[name]
        
        account_type = account.get("type", "")
        
        if account_type == "google_workspace":
            # Use the shared Google Workspace client
            if self._google_workspace_client:
                return self._google_workspace_client
            else:
                # Try to re-initialize
                if self._check_google_workspace():
                    return self._google_workspace_client
        elif account_type == "google":
            # Prefer GoogleWorkspaceClient if available (supports Meet links)
            if self._google_workspace_client:
                client = self._google_workspace_client
            else:
                from koda.integrations.google_calendar import GoogleCalendarClient
                client = GoogleCalendarClient(
                    credentials_file=account.get("credentials_file", ""),
                    token_file=account.get("token_file", "")
                )
        elif account_type == "exchange":
            from koda.integrations.exchange_client import ExchangeClient
            client = ExchangeClient(
                email=account.get("email", ""),
                password=account.get("password", ""),
                server=account.get("server", ""),
                username=account.get("username", "") or account.get("email", ""),
                version=account.get("version", "auto"),
                auth_type=account.get("auth_type", "basic"),
                use_autodiscover=account.get("use_autodiscover", False)
            )
        elif account_type == "caldav":
            from koda.integrations.caldav_client import CalDAVClient
            client = CalDAVClient(
                url=account.get("url", ""),
                username=account.get("username", ""),
                password=account.get("password", ""),
                calendar_path=account.get("calendar_path", "")
            )
        else:
            return None
        
        self._clients[name] = client
        return client
    
    def _get_account_by_name(self, name: str) -> dict | None:
        """Find a calendar account by name (case-insensitive, partial match)."""
        name_lower = name.lower()
        
        # First try exact match
        for account in self.calendar_accounts:
            if account.get("name", "").lower() == name_lower:
                return account
        
        # Then try partial match
        for account in self.calendar_accounts:
            if name_lower in account.get("name", "").lower():
                return account
        
        return None
    
    def _get_account_names(self) -> list[str]:
        """Get list of all calendar account names."""
        return [acc.get("name", "") for acc in self.calendar_accounts if acc.get("name")]
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list")
        
        try:
            if action == "list":
                return await self._list_events(kwargs.get("days", 7))
            
            elif action == "today":
                return await self._list_events(days=1, today_only=True)
            
            elif action == "week":
                return await self._list_events(days=7, week_view=True)
            
            elif action == "calendars":
                return await self._list_calendars()
            
            elif action == "create":
                return await self._create_event(**kwargs)
            
            elif action == "update":
                return await self._update_event(**kwargs)
            
            elif action == "delete":
                return await self._delete_event(**kwargs)
            
            elif action == "conflicts":
                return await self._check_conflicts(**kwargs)
            
            elif action == "upcoming":
                return await self._get_upcoming(kwargs.get("hours", 24))
            
            else:
                return f"Unknown action: {action}"
        
        except ConnectionError as e:
            import traceback
            logger.error(f"Calendar connection error:")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"""❌ **Cannot connect to calendar server**

Possible causes:
• Incorrect credentials (email/password)
• Google Workspace token expired - try '/resetgoogle' or 'koda setup-google'
• Server is unreachable
• Autodiscover does not work for this account

Try:
1. Check if your password is correct
2. Use /removecalendar and /addcalendar to reconfigure
3. For Google: reset the connection with 'koda setup-google --reset'
4. Try specifying a server manually

_Technical error has been logged on the server._"""
        
        except Exception as e:
            import traceback
            logger.error(f"Calendar operation failed for action '{action}':")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"❌ **Calendar error:** {str(e)}\n\n_Details have been logged on the server._"
    
    async def _list_calendars(self) -> str:
        """List all available calendar accounts with their names."""
        # Refresh Google Workspace calendars to catch any new shared calendars
        if self._google_workspace_available:
            self._add_google_workspace_calendars()
        
        if not self.calendar_accounts:
            return "No calendars configured. Use 'koda config calendar' or /addcalendar to add an account."
        
        output = ["**Available Calendars:**\n"]
        
        for account in self.calendar_accounts:
            name = account.get("name", "Unnamed")
            account_type = account.get("type", "unknown")
            is_shared = account.get("is_shared", False)
            access_role = account.get("access_role", "")
            
            type_label = {
                "google_workspace": "📅 Google",
                "google": "📅 Google",
                "exchange": "🏢 Exchange",
                "caldav": "🔗 CalDAV"
            }.get(account_type, account_type)
            
            shared_label = " (Shared)" if is_shared else ""
            access_label = f" [{access_role}]" if access_role and access_role != "owner" else ""
            
            output.append(f"• **{name}**{shared_label}{access_label}")
            output.append(f"  Type: {type_label}")
            
            # Show additional details based on type
            if account_type in ["google", "google_workspace"]:
                try:
                    client = self._get_client_for_account(account)
                    if client and hasattr(client, 'list_calendars'):
                        calendars = client.list_calendars()
                        output.append(f"  Access to {len(calendars)} calendar(s)")
                except Exception as e:
                    output.append(f"  ⚠️ Error: {e}")
            elif account_type == "exchange":
                output.append(f"  📧 {account.get('email', '')}")
            elif account_type == "caldav":
                output.append(f"  🔗 {account.get('url', '')[:50]}...")
            
            output.append("")
        
        output.append("_Use the calendar NAME when creating events._")
        return "\n".join(output)
    
    async def _list_events(self, days: int = 7, today_only: bool = False, week_view: bool = False) -> str:
        """List events from all calendar accounts."""
        all_events = []
        
        if today_only:
            title = "📅 Today's agenda"
        elif week_view:
            title = "📅 This week's agenda"
        else:
            title = f"📅 Agenda for the next {days} days"
        
        logger.debug(f"Fetching events from {len(self.calendar_accounts)} calendar accounts")
        
        for account in self.calendar_accounts:
            account_name = account.get("name", "Unknown")
            account_type = account.get("type", "")
            
            try:
                client = self._get_client_for_account(account)
                if not client:
                    logger.warning(f"No client available for {account_name}")
                    continue
                
                logger.debug(f"Fetching events from {account_name}")
                
                if account_type in ["google", "google_workspace"]:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    
                    if today_only:
                        time_max = now.replace(hour=23, minute=59, second=59)
                    else:
                        time_max = now + timedelta(days=days)
                    
                    # Get specific calendar ID if specified
                    calendar_id = account.get("calendar_id", "all")
                    
                    events = client.list_events(
                        calendar_id=calendar_id,
                        time_min=now,
                        time_max=time_max
                    )
                    
                    for e in events:
                        event_dict = {
                            "_account": account_name,
                            "_is_shared": account.get("is_shared", False),
                            "id": e.id,
                            "summary": e.summary,
                            "start": e.start.isoformat() if e.start else "",
                            "end": e.end.isoformat() if e.end else "",
                            "location": e.location,
                            "meet_link": e.meet_link,
                            "calendar_name": e.calendar_name if hasattr(e, 'calendar_name') else account_name,
                            "is_recurring": getattr(e, 'is_recurring', False),
                        }
                        all_events.append(event_dict)
                
                elif account_type == "exchange":
                    if today_only:
                        events = client.get_today_events()
                    else:
                        now = datetime.now()
                        events = client.list_calendar_events(
                            start=now,
                            end=now + timedelta(days=days)
                        )
                    for e in events:
                        e["_account"] = account_name
                        e["summary"] = e.get("subject", e.get("summary", "(No title)"))
                        all_events.append(e)
                
                elif account_type == "caldav":
                    events = client.get_events(days_ahead=days if not today_only else 1)
                    for e in events:
                        all_events.append({
                            "_account": account_name,
                            "id": e.uid,
                            "summary": e.summary,
                            "start": e.start.isoformat() if e.start else "",
                            "end": e.end.isoformat() if e.end else "",
                            "location": e.location,
                        })
            
            except Exception as e:
                import traceback
                logger.warning(f"{account_name} calendar error: {e}")
                logger.debug(f"Calendar error traceback:\n{traceback.format_exc()}")
        
        if not all_events:
            return f"{title}: No events found."
        
        # Sort by start time
        def get_start(e):
            start = e.get("start", "")
            if isinstance(start, str):
                try:
                    return datetime.fromisoformat(start.replace("Z", ""))
                except:
                    return datetime.max
            return start if isinstance(start, datetime) else datetime.max
        
        all_events.sort(key=get_start)
        
        # Group by day for better readability
        output = [f"**{title}** ({len(all_events)} events):\n"]
        
        current_day = None
        for e in all_events:
            start = e.get("start", "")
            if isinstance(start, str) and start:
                try:
                    start_dt = datetime.fromisoformat(start.replace("Z", ""))
                    day_str = start_dt.strftime("%A %d %B").capitalize()
                    time_str = start_dt.strftime("%H:%M")
                    
                    # Add day header if new day
                    if day_str != current_day:
                        current_day = day_str
                        output.append(f"\n**{day_str}**")
                    
                    start_display = time_str
                except:
                    start_display = start
            else:
                start_display = str(start)
            
            account = e.get("_account", "")
            is_shared = e.get("_is_shared", False)
            shared_label = " [shared]" if is_shared else ""
            
            output.append(f"  • **{e.get('summary', '(No title)')}** [{account}]{shared_label}")
            output.append(f"    🕐 {start_display}")
            
            if e.get("location"):
                output.append(f"    📍 {e['location']}")
            if e.get("meet_link"):
                output.append(f"    🔗 {e['meet_link']}")
            if e.get("is_recurring"):
                output.append(f"    🔄 Recurring")
        
        return "\n".join(output)
    
    async def _get_upcoming(self, hours: int = 24) -> str:
        """Get upcoming events in the next N hours."""
        all_events = []
        from datetime import timezone
        
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(hours=hours)
        
        for account in self.calendar_accounts:
            account_name = account.get("name", "Unknown")
            account_type = account.get("type", "")
            
            try:
                client = self._get_client_for_account(account)
                if not client:
                    continue
                
                if account_type in ["google", "google_workspace"]:
                    calendar_id = account.get("calendar_id", "all")
                    events = client.list_events(
                        calendar_id=calendar_id,
                        time_min=now,
                        time_max=time_max
                    )
                    for e in events:
                        all_events.append({
                            "_account": account_name,
                            "summary": e.summary,
                            "start": e.start,
                            "location": e.location,
                            "meet_link": e.meet_link,
                        })
            except Exception as e:
                logger.debug(f"Error fetching from {account_name}: {e}")
        
        if not all_events:
            return f"No events in the next {hours} hours."
        
        # Sort by start time
        all_events.sort(key=lambda e: e.get("start", datetime.max))
        
        output = [f"**Next {hours} hours** ({len(all_events)} events):\n"]
        
        for e in all_events:
            start = e.get("start")
            if isinstance(start, datetime):
                time_str = start.strftime("%H:%M")
                date_str = start.strftime("%d %b")
                display_time = f"{date_str} {time_str}"
            else:
                display_time = str(start)
            
            output.append(f"• **{e.get('summary')}** [{e.get('_account')}]")
            output.append(f"  🕐 {display_time}")
            if e.get("location"):
                output.append(f"  📍 {e['location']}")
            output.append("")
        
        return "\n".join(output)
    
    async def _check_conflicts(self, **kwargs) -> str:
        """Check for scheduling conflicts."""
        start_str = kwargs.get("start")
        end_str = kwargs.get("end")
        calendar_name = kwargs.get("calendar")
        
        if not start_str or not end_str:
            return "Error: start and end times are required for conflict check."
        
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
        except ValueError as e:
            return f"Error parsing datetime: {e}"
        
        conflicts = []
        
        # Check specific calendar or all calendars
        accounts_to_check = []
        if calendar_name:
            account = self._get_account_by_name(calendar_name)
            if account:
                accounts_to_check = [account]
            else:
                return f"Calendar '{calendar_name}' not found."
        else:
            accounts_to_check = self.calendar_accounts
        
        for account in accounts_to_check:
            account_name = account.get("name", "Unknown")
            account_type = account.get("type", "")
            
            try:
                client = self._get_client_for_account(account)
                if not client:
                    continue
                
                if account_type in ["google", "google_workspace"]:
                    from datetime import timezone
                    calendar_id = account.get("calendar_id", "primary")
                    
                    events = client.list_events(
                        calendar_id=calendar_id,
                        time_min=start.replace(tzinfo=timezone.utc) if not start.tzinfo else start,
                        time_max=end.replace(tzinfo=timezone.utc) if not end.tzinfo else end
                    )
                    
                    for e in events:
                        conflicts.append({
                            "account": account_name,
                            "summary": e.summary,
                            "start": e.start,
                            "end": e.end,
                        })
            except Exception as e:
                logger.debug(f"Error checking {account_name}: {e}")
        
        if conflicts:
            output = [f"**⚠️ {len(conflicts)} conflict(s) found:**\n"]
            for c in conflicts:
                output.append(f"• **{c['summary']}** [{c['account']}]")
                if isinstance(c['start'], datetime):
                    output.append(f"  🕐 {c['start'].strftime('%H:%M')} - {c['end'].strftime('%H:%M')}")
            return "\n".join(output)
        else:
            return f"✅ No conflicts found for this time slot."
    
    async def _create_event(self, **kwargs) -> str:
        """Create a calendar event with optional Meet link and WhatsApp reminder."""
        summary = kwargs.get("summary")
        start_str = kwargs.get("start")
        end_str = kwargs.get("end")
        calendar_name = kwargs.get("calendar")
        add_meet_link = kwargs.get("add_meet_link", self._google_workspace_available)
        whatsapp_reminder = kwargs.get("whatsapp_reminder")
        reminder_phone = kwargs.get("reminder_phone", self.default_reminder_phone)
        check_conflicts = kwargs.get("check_conflicts", True)
        
        # Validate required fields
        if not summary:
            return "Error: Event summary/title is required."
        if not start_str:
            return "Error: Event start time is required."
        if not end_str:
            return "Error: Event end time is required."
        
        # Parse times
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
        except ValueError as e:
            return f"Error parsing datetime: {e}"
        
        # Check available calendars
        account_names = self._get_account_names()
        if not account_names:
            return "Error: No calendar accounts configured. Use /addcalendar to add one."
        
        # Check for conflicts if requested
        if check_conflicts:
            conflict_result = await self._check_conflicts(
                start=start_str,
                end=end_str,
                calendar=calendar_name
            )
            if "conflict(s) found" in conflict_result.lower():
                return f"{conflict_result}\n\nWant to proceed anyway? Use check_conflicts: false"
        
        # Determine which calendar to use
        if not calendar_name:
            if len(account_names) == 1:
                calendar_name = account_names[0]
            else:
                names_list = ", ".join(f'"{n}"' for n in account_names)
                return (
                    f"**Which calendar do you want to use?**\n\n"
                    f"Available: {names_list}\n\n"
                    f"Specify with: `calendar: \"Work\"` (or your calendar name)\n\n"
                    f"Would you also like:\n"
                    f"- A **Google Meet link** added?\n"
                    f"- A **WhatsApp reminder** before the event? (e.g. 15 minutes before)"
                )
        
        # Find the account by name
        account = self._get_account_by_name(calendar_name)
        if not account:
            return f"Error: Calendar '{calendar_name}' not found. Available: {', '.join(account_names)}"
        
        account_type = account.get("type", "")
        
        # Create the event on the selected calendar
        result = None
        meet_link = None
        
        try:
            client = self._get_client_for_account(account)
            if not client:
                return f"Error: Could not connect to calendar '{calendar_name}'"
            
            if account_type in ["google", "google_workspace"]:
                calendar_id = account.get("calendar_id", "primary")
                result = client.create_event(
                    summary=summary,
                    start=start,
                    end=end,
                    calendar_id=calendar_id,
                    description=kwargs.get("description"),
                    location=kwargs.get("location"),
                    attendees=kwargs.get("attendees"),
                    add_meet_link=add_meet_link
                )
                if hasattr(result, 'meet_link'):
                    meet_link = result.meet_link
                elif isinstance(result, dict):
                    meet_link = result.get("meet_link")
            
            elif account_type == "exchange":
                location = kwargs.get("location", "")
                description = kwargs.get("description", "")
                
                if add_meet_link and self._google_workspace_available:
                    try:
                        from koda.core.tools.google_meet import GoogleMeetTool
                        meet_tool = GoogleMeetTool()
                        fetched_meet_link = meet_tool.get_quick_meet_link()
                        if fetched_meet_link:
                            meet_link = fetched_meet_link
                            if location:
                                location = f"{location} | {meet_link}"
                            else:
                                location = meet_link
                            if description:
                                description = f"{description}\n\n🔗 Google Meet: {meet_link}"
                            else:
                                description = f"🔗 Google Meet: {meet_link}"
                    except Exception as e:
                        logger.warning(f"Could not fetch Meet link: {e}")
                
                result = client.create_calendar_event(
                    subject=summary,
                    start=start,
                    end=end,
                    body=description or None,
                    location=location or None,
                    attendees=kwargs.get("attendees")
                )
            
            elif account_type == "caldav":
                uid = client.create_event(
                    summary=summary,
                    start=start,
                    end=end,
                    location=kwargs.get("location"),
                    description=kwargs.get("description")
                )
                result = {"id": uid, "summary": summary}
            
            else:
                return f"Error: Unknown calendar type '{account_type}'"
        
        except Exception as e:
            return f"Error creating event on '{calendar_name}': {e}"
        
        # Schedule WhatsApp reminder if requested
        reminder_scheduled = False
        if whatsapp_reminder and self.reminder_service and reminder_phone:
            reminder_time = start - timedelta(minutes=whatsapp_reminder)
            
            if reminder_time > datetime.now():
                reminder_message = (
                    f"📅 *Reminder*\n\n"
                    f"You have an appointment in {whatsapp_reminder} minutes:\n\n"
                    f"**{summary}**\n"
                    f"🕐 {start.strftime('%H:%M')}"
                )
                
                if kwargs.get("location"):
                    reminder_message += f"\n📍 {kwargs['location']}"
                
                if meet_link:
                    reminder_message += f"\n\n🔗 Google Meet: {meet_link}"
                
                try:
                    await self.reminder_service.schedule_reminder(
                        title=f"Reminder: {summary}",
                        message=reminder_message,
                        trigger_at=reminder_time,
                        channel="whatsapp",
                        recipient=reminder_phone
                    )
                    reminder_scheduled = True
                except Exception as e:
                    logger.error(f"Failed to schedule WhatsApp reminder: {e}")
        
        # Build response
        output = [f"✅ **Event created:** {summary}"]
        output.append(f"📅 {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')}")
        output.append(f"📆 Calendar: {calendar_name}")
        
        if kwargs.get("location"):
            output.append(f"📍 {kwargs['location']}")
        
        if meet_link:
            output.append(f"\n🔗 **Google Meet:** {meet_link}")
        
        if result and isinstance(result, dict) and result.get("htmlLink"):
            output.append(f"\n🔗 Event link: {result['htmlLink']}")
        
        if reminder_scheduled:
            output.append(f"\n⏰ WhatsApp reminder set for {whatsapp_reminder} minutes before")
        
        return "\n".join(output)
    
    async def _update_event(self, **kwargs) -> str:
        """Update an existing calendar event."""
        event_id = kwargs.get("event_id")
        calendar_name = kwargs.get("calendar")
        
        if not event_id:
            return "Error: event_id is required. Use 'list' action to find event IDs."
        
        account_names = self._get_account_names()
        if not account_names:
            return "Error: No calendar accounts configured."
        
        if not calendar_name:
            if len(account_names) == 1:
                calendar_name = account_names[0]
            else:
                return f"Error: Multiple calendars available. Specify which one: {', '.join(account_names)}"
        
        account = self._get_account_by_name(calendar_name)
        if not account:
            return f"Error: Calendar '{calendar_name}' not found."
        
        account_type = account.get("type", "")
        
        try:
            client = self._get_client_for_account(account)
            if not client:
                return f"Error: Could not connect to calendar '{calendar_name}'"
            
            start = None
            end = None
            if kwargs.get("start"):
                try:
                    start = datetime.fromisoformat(kwargs["start"])
                except ValueError:
                    return "Error: Invalid start datetime format"
            if kwargs.get("end"):
                try:
                    end = datetime.fromisoformat(kwargs["end"])
                except ValueError:
                    return "Error: Invalid end datetime format"
            
            if account_type in ["google", "google_workspace"]:
                calendar_id = account.get("calendar_id", "primary")
                result = client.update_event(
                    event_id=event_id,
                    calendar_id=calendar_id,
                    summary=kwargs.get("summary"),
                    start=start,
                    end=end,
                    description=kwargs.get("description"),
                    location=kwargs.get("location"),
                    add_meet_link=kwargs.get("add_meet_link", False)
                )
                if result:
                    meet_info = f"\n🔗 Meet: {result.meet_link}" if result.meet_link else ""
                    return f"✅ **Event updated:** {result.summary}{meet_info}"
                return "❌ Failed to update event"
            
            elif account_type == "exchange":
                result = client.update_calendar_event(
                    event_id=event_id,
                    subject=kwargs.get("summary"),
                    start=start,
                    end=end,
                    body=kwargs.get("description"),
                    location=kwargs.get("location")
                )
                if result:
                    return f"✅ **Event updated**"
                return "❌ Failed to update event"
            
            elif account_type == "caldav":
                result = client.update_event(
                    event_uid=event_id,
                    summary=kwargs.get("summary"),
                    start=start,
                    end=end,
                    description=kwargs.get("description"),
                    location=kwargs.get("location")
                )
                if result:
                    return f"✅ **Event updated**"
                return "❌ Failed to update event"
            
            else:
                return f"Error: Update not supported for calendar type '{account_type}'"
        
        except Exception as e:
            logger.error(f"Failed to update event: {e}")
            return f"❌ Error updating event: {e}"
    
    async def _delete_event(self, **kwargs) -> str:
        """Delete a calendar event."""
        event_id = kwargs.get("event_id")
        calendar_name = kwargs.get("calendar")
        
        if not event_id:
            return "Error: event_id is required. Use 'list' action to find event IDs."
        
        account_names = self._get_account_names()
        if not account_names:
            return "Error: No calendar accounts configured."
        
        if not calendar_name:
            if len(account_names) == 1:
                calendar_name = account_names[0]
            else:
                return f"Error: Multiple calendars available. Specify which one: {', '.join(account_names)}"
        
        account = self._get_account_by_name(calendar_name)
        if not account:
            return f"Error: Calendar '{calendar_name}' not found."
        
        account_type = account.get("type", "")
        
        try:
            client = self._get_client_for_account(account)
            if not client:
                return f"Error: Could not connect to calendar '{calendar_name}'"
            
            if account_type in ["google", "google_workspace"]:
                calendar_id = account.get("calendar_id", "primary")
                result = client.delete_event(event_id=event_id, calendar_id=calendar_id)
                if result:
                    return "✅ **Event deleted**"
                return "❌ Failed to delete event"
            
            elif account_type == "exchange":
                result = client.delete_calendar_event(event_id=event_id)
                if result:
                    return "✅ **Event deleted**"
                return "❌ Failed to delete event"
            
            elif account_type == "caldav":
                result = client.delete_event(event_uid=event_id)
                if result:
                    return "✅ **Event deleted**"
                return "❌ Failed to delete event"
            
            else:
                return f"Error: Delete not supported for calendar type '{account_type}'"
        
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return f"❌ Error deleting event: {e}"
