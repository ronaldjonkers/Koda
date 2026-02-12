"""Calendar Sync Service - Maintains a local cache of all calendar events.

Periodically syncs events from all configured calendar accounts (Google, Exchange,
CalDAV) to a local JSON file so the AI assistant always has instant access to
up-to-date calendar data for reminders, briefings, and queries.
"""

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass
class CachedEvent:
    """A locally cached calendar event."""
    id: str
    account_name: str
    account_type: str
    calendar_id: str = ""
    calendar_name: str = ""
    summary: str = ""
    description: str = ""
    location: str = ""
    start: str = ""  # ISO format
    end: str = ""    # ISO format
    all_day: bool = False
    is_recurring: bool = False
    is_shared: bool = False
    meet_link: str = ""
    attendees: list[str] = field(default_factory=list)
    organizer: str = ""
    status: str = ""  # confirmed, tentative, cancelled


@dataclass
class SyncState:
    """Tracks sync state per account."""
    account_name: str
    last_sync: str = ""  # ISO format
    event_count: int = 0
    error: str = ""
    sync_duration_ms: int = 0


class CalendarSyncService:
    """
    Service that maintains a local cache of all calendar events.
    
    Features:
    - Syncs all configured calendar accounts periodically
    - Stores events in ~/.koda/cache/calendars.json
    - Provides fast local reads for calendar queries
    - Tracks sync state per account
    - Thread-safe reads and writes
    """
    
    DEFAULT_SYNC_INTERVAL = 300  # 5 minutes
    DEFAULT_LOOKAHEAD_DAYS = 30
    DEFAULT_LOOKBEHIND_DAYS = 7
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        sync_interval: int = DEFAULT_SYNC_INTERVAL,
        lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
        lookbehind_days: int = DEFAULT_LOOKBEHIND_DAYS,
        tz: str = "Europe/Amsterdam",
    ):
        self.cache_dir = cache_dir or Path.home() / ".koda" / "cache"
        self.cache_file = self.cache_dir / "calendars.json"
        self.state_file = self.cache_dir / "calendar_sync_state.json"
        self.sync_interval = sync_interval
        self.lookahead_days = lookahead_days
        self.lookbehind_days = lookbehind_days
        self.tz = tz
        
        self._events: list[CachedEvent] = []
        self._sync_states: dict[str, SyncState] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._calendar_accounts: list[dict] = []
        
        # Ensure cache dir exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing cache
        self._load_cache()
    
    def set_accounts(self, accounts: list[dict]) -> None:
        """Set the calendar accounts to sync."""
        self._calendar_accounts = accounts
        logger.info(f"Calendar sync: {len(accounts)} account(s) configured")
    
    def start(self) -> None:
        """Start the periodic sync in a background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True, name="calendar-sync")
        self._thread.start()
        logger.info(f"📅 Calendar sync started (every {self.sync_interval}s, {self.lookahead_days}d ahead)")
    
    def stop(self) -> None:
        """Stop the sync service."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("📅 Calendar sync stopped")
    
    def sync_now(self) -> dict:
        """Trigger an immediate sync. Returns summary."""
        return self._do_sync()
    
    # =========================================================================
    # Read API - Used by other services and tools
    # =========================================================================
    
    def get_events(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        account_name: Optional[str] = None,
        calendar_name: Optional[str] = None,
    ) -> list[dict]:
        """Get cached events, optionally filtered by time range and account.
        
        Args:
            start: Filter events starting from this time (default: now)
            end: Filter events ending before this time (default: 30 days from now)
            account_name: Filter by account name (case-insensitive)
            calendar_name: Filter by calendar name (case-insensitive)
        
        Returns:
            List of event dicts sorted by start time.
        """
        with self._lock:
            events = list(self._events)
        
        # Default time range
        if start is None:
            start = datetime.now(timezone.utc)
        if end is None:
            end = start + timedelta(days=self.lookahead_days)
        
        start_iso = start.isoformat()
        end_iso = end.isoformat()
        
        result = []
        for ev in events:
            # Time filter
            if ev.end and ev.end < start_iso:
                continue
            if ev.start and ev.start > end_iso:
                continue
            
            # Account filter
            if account_name and ev.account_name.lower() != account_name.lower():
                continue
            
            # Calendar filter
            if calendar_name and ev.calendar_name.lower() != calendar_name.lower():
                continue
            
            result.append(asdict(ev))
        
        # Sort by start time
        result.sort(key=lambda e: e.get("start", ""))
        return result
    
    def get_today_events(self, account_name: Optional[str] = None) -> list[dict]:
        """Get events for today."""
        try:
            from zoneinfo import ZoneInfo
            local_tz = ZoneInfo(self.tz)
        except Exception:
            local_tz = timezone.utc
        
        now = datetime.now(local_tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.get_events(start=start, end=end, account_name=account_name)
    
    def get_upcoming_events(self, hours: int = 24, account_name: Optional[str] = None) -> list[dict]:
        """Get events in the next N hours."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours)
        return self.get_events(start=now, end=end, account_name=account_name)
    
    def get_week_events(self, account_name: Optional[str] = None) -> list[dict]:
        """Get events for the current week."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        return self.get_events(start=now, end=end, account_name=account_name)
    
    def get_sync_status(self) -> dict:
        """Get sync status summary."""
        with self._lock:
            states = {name: asdict(state) for name, state in self._sync_states.items()}
            total_events = len(self._events)
        
        return {
            "total_events": total_events,
            "accounts": states,
            "cache_file": str(self.cache_file),
            "sync_interval_seconds": self.sync_interval,
            "lookahead_days": self.lookahead_days,
        }
    
    def get_account_names(self) -> list[str]:
        """Get list of synced account names."""
        with self._lock:
            return list(set(ev.account_name for ev in self._events))
    
    # =========================================================================
    # Sync Logic
    # =========================================================================
    
    def _sync_loop(self) -> None:
        """Background sync loop."""
        # Initial sync immediately
        self._do_sync()
        
        while self._running:
            time.sleep(self.sync_interval)
            if self._running:
                self._do_sync()
    
    def _do_sync(self) -> dict:
        """Perform a full sync of all accounts."""
        summary = {"synced": 0, "errors": 0, "total_events": 0}
        all_events: list[CachedEvent] = []
        
        for account in self._calendar_accounts:
            account_name = account.get("name", "Unknown")
            account_type = account.get("type", "")
            
            start_time = time.time()
            state = SyncState(account_name=account_name)
            
            try:
                events = self._fetch_events_for_account(account)
                state.event_count = len(events)
                state.last_sync = datetime.now(timezone.utc).isoformat()
                state.sync_duration_ms = int((time.time() - start_time) * 1000)
                all_events.extend(events)
                summary["synced"] += 1
                logger.debug(f"Synced {len(events)} events from {account_name}")
            except Exception as e:
                state.error = str(e)
                state.last_sync = datetime.now(timezone.utc).isoformat()
                state.sync_duration_ms = int((time.time() - start_time) * 1000)
                summary["errors"] += 1
                logger.warning(f"Calendar sync failed for {account_name}: {e}")
            
            with self._lock:
                self._sync_states[account_name] = state
        
        # Update cache atomically
        with self._lock:
            self._events = all_events
        
        summary["total_events"] = len(all_events)
        
        # Persist to disk
        self._save_cache()
        self._save_state()
        
        logger.debug(f"Calendar sync complete: {summary['total_events']} events from {summary['synced']} accounts")
        return summary
    
    def _fetch_events_for_account(self, account: dict) -> list[CachedEvent]:
        """Fetch events from a single account."""
        account_name = account.get("name", "Unknown")
        account_type = account.get("type", "")
        
        now = datetime.now(timezone.utc)
        time_min = now - timedelta(days=self.lookbehind_days)
        time_max = now + timedelta(days=self.lookahead_days)
        
        events: list[CachedEvent] = []
        
        if account_type in ("google", "google_workspace"):
            events = self._fetch_google_events(account, time_min, time_max)
        elif account_type == "exchange":
            events = self._fetch_exchange_events(account, time_min, time_max)
        elif account_type in ("caldav", "google_caldav"):
            events = self._fetch_caldav_events(account, time_min, time_max)
        else:
            logger.debug(f"Unknown calendar type '{account_type}' for {account_name}")
        
        return events
    
    def _fetch_google_events(self, account: dict, time_min: datetime, time_max: datetime) -> list[CachedEvent]:
        """Fetch events from Google Calendar (Workspace or legacy)."""
        results = []
        account_name = account.get("name", "Google")
        
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient(timezone=self.tz)
            
            if not client.is_authorized:
                logger.debug(f"Google Workspace not authorized for {account_name}")
                return results
            
            calendar_id = account.get("calendar_id", "all")
            raw_events = client.list_events(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
            )
            
            for ev in raw_events:
                results.append(CachedEvent(
                    id=ev.id,
                    account_name=account_name,
                    account_type="google",
                    calendar_id=getattr(ev, 'calendar_id', '') or '',
                    calendar_name=getattr(ev, 'calendar_name', account_name) or account_name,
                    summary=ev.summary or "",
                    description=getattr(ev, 'description', '') or '',
                    location=ev.location or "",
                    start=ev.start.isoformat() if ev.start else "",
                    end=ev.end.isoformat() if ev.end else "",
                    all_day=getattr(ev, 'all_day', False),
                    is_recurring=getattr(ev, 'is_recurring', False),
                    is_shared=account.get("is_shared", False),
                    meet_link=ev.meet_link or "",
                    attendees=getattr(ev, 'attendees', []) or [],
                    organizer=getattr(ev, 'organizer', '') or '',
                    status=getattr(ev, 'status', 'confirmed') or 'confirmed',
                ))
        except Exception as e:
            logger.error(f"Error fetching Google events for {account_name}: {e}")
        
        return results
    
    def _fetch_exchange_events(self, account: dict, time_min: datetime, time_max: datetime) -> list[CachedEvent]:
        """Fetch events from Exchange."""
        results = []
        account_name = account.get("name", "Exchange")
        
        try:
            from koda.integrations.exchange_client import ExchangeClient
            client = ExchangeClient(
                email=account.get("email", ""),
                password=account.get("password", ""),
                server=account.get("server", ""),
                username=account.get("username", "") or account.get("email", ""),
                use_autodiscover=account.get("use_autodiscover", False),
            )
            
            raw_events = client.list_calendar_events(
                start=time_min,
                end=time_max,
                max_results=200,
            )
            
            for ev in raw_events:
                results.append(CachedEvent(
                    id=str(ev.get("id", "")),
                    account_name=account_name,
                    account_type="exchange",
                    summary=ev.get("subject", ev.get("summary", "")),
                    description=ev.get("body", ""),
                    location=ev.get("location", ""),
                    start=ev.get("start", ""),
                    end=ev.get("end", ""),
                    all_day=ev.get("all_day", False),
                    is_recurring=ev.get("is_recurring", False),
                    attendees=ev.get("attendees", []),
                    organizer=ev.get("organizer", ""),
                    status=ev.get("status", "confirmed"),
                ))
        except Exception as e:
            logger.error(f"Error fetching Exchange events for {account_name}: {e}")
        
        return results
    
    def _fetch_caldav_events(self, account: dict, time_min: datetime, time_max: datetime) -> list[CachedEvent]:
        """Fetch events from CalDAV."""
        results = []
        account_name = account.get("name", "CalDAV")
        
        try:
            from koda.integrations.google_caldav import GoogleCalDAVClient
            client = GoogleCalDAVClient(
                email=account.get("email", ""),
                app_password=account.get("password", ""),
            )
            
            days_ahead = (time_max - time_min).days
            raw_events = client.get_events(days_ahead=days_ahead)
            
            for ev in raw_events:
                start = getattr(ev, 'start', None)
                end = getattr(ev, 'end', None)
                results.append(CachedEvent(
                    id=getattr(ev, 'uid', '') or str(id(ev)),
                    account_name=account_name,
                    account_type="caldav",
                    summary=getattr(ev, 'summary', '') or '',
                    description=getattr(ev, 'description', '') or '',
                    location=getattr(ev, 'location', '') or '',
                    start=start.isoformat() if hasattr(start, 'isoformat') else str(start or ''),
                    end=end.isoformat() if hasattr(end, 'isoformat') else str(end or ''),
                    all_day=getattr(ev, 'all_day', False),
                ))
        except Exception as e:
            logger.error(f"Error fetching CalDAV events for {account_name}: {e}")
        
        return results
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def _save_cache(self) -> None:
        """Save events to disk."""
        try:
            with self._lock:
                data = [asdict(ev) for ev in self._events]
            
            self.cache_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save calendar cache: {e}")
    
    def _load_cache(self) -> None:
        """Load events from disk."""
        if not self.cache_file.exists():
            return
        
        try:
            raw = json.loads(self.cache_file.read_text())
            with self._lock:
                self._events = [CachedEvent(**ev) for ev in raw]
            logger.debug(f"Loaded {len(self._events)} cached calendar events")
        except Exception as e:
            logger.warning(f"Failed to load calendar cache: {e}")
    
    def _save_state(self) -> None:
        """Save sync state to disk."""
        try:
            with self._lock:
                data = {name: asdict(state) for name, state in self._sync_states.items()}
            self.state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save sync state: {e}")
    
    def _load_state(self) -> None:
        """Load sync state from disk."""
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text())
            with self._lock:
                self._sync_states = {
                    name: SyncState(**state) for name, state in raw.items()
                }
        except Exception as e:
            logger.warning(f"Failed to load sync state: {e}")


def create_calendar_sync_from_config(config) -> Optional[CalendarSyncService]:
    """Create a CalendarSyncService from the Koda config.
    
    Collects all accounts with calendar capability and sets up sync.
    """
    try:
        tz = config.assistant.timezone if hasattr(config.assistant, 'timezone') else "Europe/Amsterdam"
        
        service = CalendarSyncService(tz=tz)
        
        # Build calendar accounts list
        calendar_accounts = []
        
        # 1. Auto-detect Google Workspace
        try:
            from koda.integrations.google_workspace import GoogleWorkspaceClient
            client = GoogleWorkspaceClient(timezone=tz)
            if client.is_authorized:
                # Get all calendars including shared ones
                all_calendars = client.list_calendars(use_cache=False)
                for cal in all_calendars:
                    calendar_accounts.append({
                        "name": cal.name + (" (Shared)" if cal.is_shared else ""),
                        "type": "google_workspace",
                        "calendar_id": cal.id,
                        "is_shared": cal.is_shared,
                    })
                logger.info(f"Calendar sync: found {len(all_calendars)} Google calendars")
        except Exception as e:
            logger.debug(f"Google Workspace not available for calendar sync: {e}")
        
        # 2. Unified accounts with calendar capability
        for acc in getattr(config.integrations, 'accounts', []) or []:
            caps = getattr(acc, 'capabilities', []) or []
            acc_type = getattr(acc, 'type', '')
            
            if 'calendar' in caps or acc_type in ('exchange', 'caldav', 'google_caldav'):
                acc_dict = acc.model_dump() if hasattr(acc, 'model_dump') else (
                    acc if isinstance(acc, dict) else {}
                )
                calendar_accounts.append(acc_dict)
        
        # 3. Legacy calendar_accounts
        for acc in getattr(config.integrations, 'calendar_accounts', []) or []:
            acc_dict = acc.model_dump() if hasattr(acc, 'model_dump') else (
                acc if isinstance(acc, dict) else {}
            )
            calendar_accounts.append(acc_dict)
        
        if not calendar_accounts:
            logger.debug("No calendar accounts configured for sync")
            return None
        
        service.set_accounts(calendar_accounts)
        return service
    
    except Exception as e:
        logger.error(f"Failed to create calendar sync service: {e}")
        return None
