"""Unified calendar tool with multi-provider support, Google Meet, and WhatsApp reminders."""

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class UnifiedCalendarTool(BaseTool):
    """
    Unified calendar tool that supports multiple named calendar accounts.
    
    Features:
    - Multiple named calendar accounts (e.g., "Werk", "Privé", "Familie")
    - Automatic calendar selection prompt when ambiguous
    - Google Meet link generation for Google Calendar events
    - WhatsApp reminder scheduling before appointments
    - Lists available calendars across all providers
    - No limit on number of connected accounts
    """
    
    name = "calendar"
    description = """Schedule and manage calendar events across multiple named calendar accounts.

Calendars are identified by their user-defined NAME (e.g., "Werk", "Privé", "Familie").
Use the 'calendars' action to see all available calendar names.

IMPORTANT: When creating an event, ALWAYS:
1. Ask which calendar to use BY NAME if not specified and multiple calendars are available
2. Ask if the user wants a WhatsApp reminder before the event
3. For Google Calendar meetings, ask if they want a Google Meet link added

Actions:
- list: List upcoming events from all calendars
- today: Get today's events from all calendars  
- create: Create a new event (will prompt for calendar name, reminder, and meet link)
- update: Update an existing event (change time, location, description, add Meet link)
- delete: Delete an event
- calendars: List all available calendars with their names

Parameters for 'update':
- event_id: Event ID to update (required)
- calendar: Calendar NAME where the event is located
- summary: New event title
- start: New start datetime ISO format
- end: New end datetime ISO format
- location: New location
- description: New description
- add_meet_link: Add Google Meet link (Google only)

Parameters for 'delete':
- event_id: Event ID to delete (required)
- calendar: Calendar NAME where the event is located

Parameters for 'create':
- summary: Event title (required)
- start: Start datetime ISO format (required)
- end: End datetime ISO format (required)
- calendar: Calendar NAME to use (e.g., "Werk", "Privé", or the account name)
- description: Event description
- location: Event location
- attendees: List of attendee emails
- add_meet_link: Add Google Meet link (only for Google-type calendars)
- whatsapp_reminder: Minutes before event to send WhatsApp reminder
- reminder_phone: Phone number for WhatsApp reminder (defaults to owner)
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "today", "create", "update", "delete", "calendars"],
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
            "calendar": {
                "type": "string",
                "description": "Calendar to use: 'google', 'exchange', 'caldav', or specific calendar ID"
            },
            "summary": {
                "type": "string",
                "description": "Event title (for create action)"
            },
            "start": {
                "type": "string",
                "description": "Start datetime ISO format (for create action)"
            },
            "end": {
                "type": "string",
                "description": "End datetime ISO format (for create action)"
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
        
        # Check if Google Workspace is available (for Meet links)
        self._google_workspace_client = None
        self._google_workspace_available = self._check_google_workspace()
        
        # Auto-add Google Workspace as a calendar account if connected
        if self._google_workspace_available:
            # Check if we already have a google account
            has_google = any(acc.get("type") == "google" for acc in self.calendar_accounts)
            if not has_google:
                self.calendar_accounts.append({
                    "name": "Google",
                    "type": "google",
                    "auto_added": True
                })
                logger.info("Auto-added Google Workspace as calendar account")
    
    def _check_google_workspace(self) -> bool:
        """Check if Google Workspace is configured and authorized."""
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient()
            status = client.get_status()
            if status.get("authorized"):
                self._google_workspace_client = client
                return True
        except Exception:
            pass
        return False
    
    def _get_client_for_account(self, account: dict) -> Any:
        """Get or create a client for a named account."""
        name = account.get("name", "")
        if name in self._clients:
            return self._clients[name]
        
        account_type = account.get("type", "")
        
        if account_type == "google":
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
        """Find a calendar account by name (case-insensitive)."""
        name_lower = name.lower()
        for account in self.calendar_accounts:
            if account.get("name", "").lower() == name_lower:
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
            
            elif action == "calendars":
                return await self._list_calendars()
            
            elif action == "create":
                return await self._create_event(**kwargs)
            
            elif action == "update":
                return await self._update_event(**kwargs)
            
            elif action == "delete":
                return await self._delete_event(**kwargs)
            
            else:
                return f"Unknown action: {action}"
        
        except ConnectionError as e:
            # Connection errors - show friendly message to user, full error on server
            import traceback
            logger.error(f"Calendar connection error:")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"""❌ **Kan geen verbinding maken met calendar server**

Mogelijke oorzaken:
• Onjuiste inloggegevens (email/wachtwoord)
• Server is niet bereikbaar
• Autodiscover werkt niet voor dit account

Probeer:
1. Controleer of je wachtwoord correct is
2. Gebruik /removecalendar en /addcalendar om opnieuw in te stellen
3. Probeer handmatig een server op te geven

_Technische fout is gelogd op de server._"""
        
        except Exception as e:
            # Other errors - log full details on server
            import traceback
            logger.error(f"Calendar operation failed for action '{action}':")
            logger.error(f"Full error: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return f"❌ **Calendar fout:** {str(e)}\n\n_Details zijn gelogd op de server._"
    
    async def _list_calendars(self) -> str:
        """List all available calendar accounts with their names."""
        if not self.calendar_accounts:
            return "No calendar accounts configured. Run 'koda config calendar' to add an account."
        
        output = ["**Available Calendar Accounts:**\n"]
        
        for account in self.calendar_accounts:
            name = account.get("name", "Unnamed")
            account_type = account.get("type", "unknown")
            type_label = {"google": "Google Calendar", "exchange": "Exchange", "caldav": "CalDAV"}.get(account_type, account_type)
            
            output.append(f"• **{name}** ({type_label})")
            
            # Show additional details based on type
            if account_type == "google":
                try:
                    client = self._get_client_for_account(account)
                    calendars = client.list_calendars()
                    for cal in calendars[:5]:  # Show first 5
                        # Handle both dict and dataclass
                        if hasattr(cal, 'name'):
                            cal_name = cal.name
                            is_primary = cal.is_primary
                        else:
                            cal_name = cal.get('summary', cal.get('name', 'Unknown'))
                            is_primary = cal.get('primary', False)
                        primary = " ⭐" if is_primary else ""
                        output.append(f"  - {cal_name}{primary}")
                except Exception as e:
                    output.append(f"  ⚠️ Error: {e}")
            elif account_type == "exchange":
                output.append(f"  📧 {account.get('email', '')}")
            elif account_type == "caldav":
                output.append(f"  🔗 {account.get('url', '')[:50]}...")
            
            output.append("")
        
        output.append("_Use the calendar NAME when creating events._")
        return "\n".join(output)
    
    async def _list_events(self, days: int = 7, today_only: bool = False) -> str:
        """List events from all calendar accounts."""
        all_events = []
        
        title = "Today's events" if today_only else f"Events (next {days} days)"
        
        for account in self.calendar_accounts:
            account_name = account.get("name", "Unknown")
            account_type = account.get("type", "")
            
            try:
                client = self._get_client_for_account(account)
                if not client:
                    continue
                
                if account_type == "google":
                    # GoogleWorkspaceClient uses list_events()
                    now = datetime.now()
                    if today_only:
                        time_max = now.replace(hour=23, minute=59, second=59)
                    else:
                        time_max = now + timedelta(days=days)
                    
                    # Use calendar_id="all" to get events from all calendars
                    events = client.list_events(
                        calendar_id="all",
                        time_min=now,
                        time_max=time_max
                    )
                    for e in events:
                        # Convert GoogleCalendarEvent dataclass to dict
                        event_dict = {
                            "_account": account_name,
                            "id": e.id,
                            "summary": e.summary,
                            "start": e.start.isoformat() if e.start else "",
                            "end": e.end.isoformat() if e.end else "",
                            "location": e.location,
                            "meet_link": e.meet_link,
                            "calendar_name": e.calendar_name,
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
                            "id": e.uid,  # Include UID for update/delete
                            "summary": e.summary,
                            "start": e.start.isoformat() if e.start else "",
                            "end": e.end.isoformat() if e.end else "",
                            "location": e.location,
                        })
            
            except Exception as e:
                logger.warning(f"{account_name} calendar error: {e}")
        
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
        
        output = [f"**{title}** ({len(all_events)} events):\n"]
        
        for e in all_events:
            start = e.get("start", "")
            if isinstance(start, str) and start:
                try:
                    start = datetime.fromisoformat(start.replace("Z", "")).strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            account = e.get("_account", "")
            event_id = e.get("id") or e.get("event_id") or e.get("uid", "")
            
            output.append(f"• **{e.get('summary', '(No title)')}** [{account}]")
            output.append(f"  📅 {start}")
            if e.get("location"):
                output.append(f"  📍 {e['location']}")
            if event_id:
                # Show short ID for readability
                short_id = event_id[:20] + "..." if len(str(event_id)) > 20 else event_id
                output.append(f"  🆔 `{short_id}`")
            output.append("")
        
        return "\n".join(output)
    
    async def _create_event(self, **kwargs) -> str:
        """Create a calendar event with optional Meet link and WhatsApp reminder."""
        summary = kwargs.get("summary")
        start_str = kwargs.get("start")
        end_str = kwargs.get("end")
        calendar_name = kwargs.get("calendar")
        # Default to adding Meet link if Google Workspace is available
        add_meet_link = kwargs.get("add_meet_link", self._google_workspace_available)
        whatsapp_reminder = kwargs.get("whatsapp_reminder")
        reminder_phone = kwargs.get("reminder_phone", self.default_reminder_phone)
        
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
            return "Error: No calendar accounts configured. Run 'koda config calendar' to add one."
        
        # Determine which calendar to use
        if not calendar_name:
            if len(account_names) == 1:
                calendar_name = account_names[0]
            else:
                # Multiple calendars - ask user to specify by name
                names_list = ", ".join(f'"{n}"' for n in account_names)
                return (
                    f"**Which calendar should I use?**\n\n"
                    f"Available calendars: {names_list}\n\n"
                    f"Please specify with: `calendar: \"Werk\"` (or the name of your calendar)\n\n"
                    f"Also, would you like:\n"
                    f"- A **Google Meet link** added? (only for Google-type calendars)\n"
                    f"- A **WhatsApp reminder** before the event? (e.g., 15 minutes before)"
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
            
            if account_type == "google":
                result = client.create_event(
                    summary=summary,
                    start=start,
                    end=end,
                    calendar_id="primary",
                    description=kwargs.get("description"),
                    location=kwargs.get("location"),
                    attendees=kwargs.get("attendees"),
                    add_meet_link=add_meet_link
                )
                # Handle both dict (old client) and dataclass (GoogleWorkspaceClient)
                if hasattr(result, 'meet_link'):
                    meet_link = result.meet_link
                elif isinstance(result, dict):
                    meet_link = result.get("meet_link")
            
            elif account_type == "exchange":
                # For Exchange, fetch a Meet link if requested and Google Workspace is available
                location = kwargs.get("location", "")
                description = kwargs.get("description", "")
                
                if add_meet_link and self._google_workspace_available:
                    try:
                        from koda.core.tools.google_meet import GoogleMeetTool
                        meet_tool = GoogleMeetTool()
                        fetched_meet_link = meet_tool.get_quick_meet_link()
                        if fetched_meet_link:
                            meet_link = fetched_meet_link
                            # Add to location
                            if location:
                                location = f"{location} | {meet_link}"
                            else:
                                location = meet_link
                            # Add to description/body
                            if description:
                                description = f"{description}\n\n🔗 Google Meet: {meet_link}"
                            else:
                                description = f"🔗 Google Meet: {meet_link}"
                    except Exception as e:
                        logger.warning(f"Could not fetch Meet link for Exchange event: {e}")
                
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
                    f"📅 *Herinnering*\n\n"
                    f"Je hebt over {whatsapp_reminder} minuten een afspraak:\n\n"
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
        
        if result and result.get("htmlLink"):
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
        
        # Get calendar account
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
            
            # Parse optional datetime updates
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
            
            if account_type == "google":
                result = client.update_event(
                    event_id=event_id,
                    calendar_id="primary",
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
        
        # Get calendar account
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
            
            if account_type == "google":
                result = client.delete_event(event_id=event_id, calendar_id="primary")
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
