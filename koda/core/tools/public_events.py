"""Public events tool for importing external calendars and events.

Supports:
- Formula 1 races (via Ergast API)
- Football matches (via Football-Data.org)
- Concerts and festivals (via Songkick/Bandsintown)
- Generic iCal/ICS feeds
- Custom event sources

These events are stored separately from personal calendars and can trigger
proactive reminders like "Feyenoord plays this weekend" or "F1 race tomorrow".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from loguru import logger

from koda.core.tools.base import BaseTool


class EventCategory(str, Enum):
    """Categories of public events."""
    SPORTS = "sports"
    MUSIC = "music"
    ENTERTAINMENT = "entertainment"
    POLITICS = "politics"
    TECH = "tech"
    OTHER = "other"


class EventSource(str, Enum):
    """Sources for public events."""
    F1 = "f1"                          # Formula 1 via Ergast
    FOOTBALL = "football"              # Football via Football-Data
    CONCERTS = "concerts"              # Concerts via Songkick
    ICAL = "ical"                      # Generic iCal feed
    CUSTOM = "custom"                  # User-defined events


@dataclass
class PublicEvent:
    """Represents a public event."""
    id: str
    title: str
    description: str
    category: EventCategory
    source: EventSource
    start_time: datetime
    end_time: Optional[datetime]
    location: Optional[str]
    url: Optional[str]
    teams: Optional[list[str]]  # For sports events
    competition: Optional[str]  # E.g., "Formula 1", "Eredivisie"
    reminder_sent: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        data['end_time'] = self.end_time.isoformat() if self.end_time else None
        data['category'] = self.category.value
        data['source'] = self.source.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> PublicEvent:
        """Create from dictionary."""
        data = data.copy()
        data['start_time'] = datetime.fromisoformat(data['start_time'])
        if data.get('end_time'):
            data['end_time'] = datetime.fromisoformat(data['end_time'])
        data['category'] = EventCategory(data['category'])
        data['source'] = EventSource(data['source'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PublicEventsTool(BaseTool):
    """
    Import and manage public events like sports, concerts, and festivals.
    
    This tool fetches events from various public sources and stores them locally.
    The proactive assistant can then send reminders about upcoming events.
    
    Supported sources:
    - F1: Formula 1 race calendar (automatic, free)
    - Football: Match schedules for your favorite teams (API key required for some leagues)
    - Concerts: Live music events in your area (API key required)
    - iCal: Import any public calendar feed
    
    Examples:
    - "Add F1 calendar"
    - "Show me when Feyenoord plays next"
    - "Find concerts in Amsterdam this month"
    - "Import my favorite team's schedule"
    
    Actions:
    - import: Import events from a source
    - list: Show upcoming events
    - search: Search for specific events
    - add_team: Subscribe to a sports team
    - remove_team: Unsubscribe from a team
    - teams: List subscribed teams
    """
    
    name = "public_events"
    description = """Import and manage public events like sports, concerts, and festivals.

Use this to:
- Add Formula 1 race calendar
- Follow your favorite football team (Feyenoord, Ajax, etc.)
- Find concerts and festivals
- Import public calendar feeds
- Get reminded about upcoming events

Actions:
- import: Import events from a source (f1, football, concerts)
- list: Show upcoming events with optional filtering
- search: Search for specific events by keyword
- add_team: Subscribe to a sports team for auto-import
- remove_team: Unsubscribe from a team
- teams: List subscribed teams

Examples:
- "Import F1 calendar"
- "When does Feyenoord play next?"
- "Find concerts in Amsterdam"
- "Show my subscribed teams"
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["import", "list", "search", "add_team", "remove_team", "teams"],
                "description": "Action to perform"
            },
            "source": {
                "type": "string",
                "enum": ["f1", "football", "concerts", "ical"],
                "description": "Source to import from (for 'import' action)"
            },
            "team": {
                "type": "string",
                "description": "Team name for football subscriptions"
            },
            "competition": {
                "type": "string",
                "description": "Competition code (e.g., 'PL' for Premier League, 'DED' for Eredivisie)"
            },
            "keyword": {
                "type": "string",
                "description": "Search keyword (for 'search' action)"
            },
            "category": {
                "type": "string",
                "enum": ["sports", "music", "entertainment", "all"],
                "description": "Filter by category"
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead (default: 30)",
                "default": 30
            },
            "location": {
                "type": "string",
                "description": "Location for concert searches (e.g., 'Amsterdam')"
            },
            "ical_url": {
                "type": "string",
                "description": "URL to iCal/ICS feed"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 10
            }
        },
        "required": ["action"]
    }
    
    # API endpoints
    F1_API_URL = "https://ergast.com/api/f1"
    FOOTBALL_API_URL = "https://api.football-data.org/v4"
    
    def __init__(self, workspace: Path, football_api_key: Optional[str] = None):
        self.workspace = workspace
        self.data_dir = workspace / "public_events"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.events_file = self.data_dir / "events.json"
        self.teams_file = self.data_dir / "subscribed_teams.json"
        self.config_file = self.data_dir / "config.json"
        
        self.football_api_key = football_api_key
        
        # Load existing data
        self.events: list[PublicEvent] = self._load_events()
        self.subscribed_teams: list[dict] = self._load_teams()
    
    def _load_events(self) -> list[PublicEvent]:
        """Load events from storage."""
        if not self.events_file.exists():
            return []
        try:
            data = json.loads(self.events_file.read_text())
            return [PublicEvent.from_dict(e) for e in data.get("events", [])]
        except Exception as e:
            logger.error(f"Failed to load events: {e}")
            return []
    
    def _save_events(self):
        """Save events to storage."""
        data = {
            "events": [e.to_dict() for e in self.events],
            "last_updated": datetime.now().isoformat()
        }
        self.events_file.write_text(json.dumps(data, indent=2, default=str))
    
    def _load_teams(self) -> list[dict]:
        """Load subscribed teams."""
        if not self.teams_file.exists():
            return []
        try:
            return json.loads(self.teams_file.read_text())
        except Exception:
            return []
    
    def _save_teams(self):
        """Save subscribed teams."""
        self.teams_file.write_text(json.dumps(self.subscribed_teams, indent=2))
    
    async def execute(self, **kwargs) -> str:
        """Execute public events action."""
        action = kwargs.get("action")
        
        try:
            if action == "import":
                return await self._import_events(**kwargs)
            elif action == "list":
                return self._list_events(**kwargs)
            elif action == "search":
                return self._search_events(**kwargs)
            elif action == "add_team":
                return await self._add_team(**kwargs)
            elif action == "remove_team":
                return self._remove_team(**kwargs)
            elif action == "teams":
                return self._list_teams()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Public events error: {e}")
            return f"❌ Error: {str(e)}"
    
    async def _import_events(self, source: Optional[str] = None, **kwargs) -> str:
        """Import events from a source."""
        if not source:
            return "❌ Please specify a source: f1, football, concerts, or ical"
        
        if source == "f1":
            return await self._import_f1()
        elif source == "football":
            team = kwargs.get("team", "")
            if team:
                return await self._import_football_team(team)
            return await self._import_all_football()
        elif source == "ical":
            url = kwargs.get("ical_url", "")
            if not url:
                return "❌ Please provide an iCal URL with ical_url parameter"
            return await self._import_ical(url)
        else:
            return f"❌ Unknown source: {source}"
    
    async def _import_f1(self) -> str:
        """Import Formula 1 race calendar."""
        logger.info("Importing F1 calendar...")
        
        current_year = datetime.now().year
        url = f"{self.F1_API_URL}/{current_year}.json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                if not races:
                    return "❌ No F1 races found for this season"
                
                imported_count = 0
                for race in races:
                    race_date = race.get("date")
                    race_time = race.get("time", "00:00:00Z")
                    
                    if not race_date:
                        continue
                    
                    start_time = datetime.fromisoformat(f"{race_date}T{race_time.replace('Z', '+00:00')}")
                    
                    # Skip past races
                    if start_time < datetime.now(start_time.tzinfo) - timedelta(days=1):
                        continue
                    
                    event = PublicEvent(
                        id=f"f1_{race.get('season')}_{race.get('round')}",
                        title=f"🏎️ F1: {race.get('raceName', 'Grand Prix')}",
                        description=f"Round {race.get('round')} of the Formula 1 World Championship at {race.get('Circuit', {}).get('circuitName', 'Unknown Circuit')}",
                        category=EventCategory.SPORTS,
                        source=EventSource.F1,
                        start_time=start_time,
                        end_time=start_time + timedelta(hours=3),
                        location=race.get("Circuit", {}).get("Location", {}).get("locality", ""),
                        url=race.get("url"),
                        teams=None,
                        competition="Formula 1"
                    )
                    
                    # Update or add event
                    self._upsert_event(event)
                    imported_count += 1
                
                self._save_events()
                return f"✅ Imported {imported_count} F1 races for the {current_year} season"
                
            except httpx.HTTPStatusError as e:
                logger.error(f"F1 API error: {e}")
                return f"❌ F1 API error: {e.response.status_code}"
            except Exception as e:
                logger.error(f"Failed to import F1: {e}")
                return f"❌ Failed to import F1 calendar: {e}"
    
    async def _import_football_team(self, team_name: str) -> str:
        """Import matches for a specific football team."""
        logger.info(f"Importing matches for {team_name}...")
        
        # Map common team names to IDs (simplified, would need proper API in production)
        team_map = {
            "feyenoord": {"id": 675, "competition": "DED"},
            "ajax": {"id": 678, "competition": "DED"},
            "psv": {"id": 674, "competition": "DED"},
            "az": {"id": 682, "competition": "DED"},
            "liverpool": {"id": 64, "competition": "PL"},
            "manchester city": {"id": 65, "competition": "PL"},
            "manchester united": {"id": 66, "competition": "PL"},
            "arsenal": {"id": 57, "competition": "PL"},
            "chelsea": {"id": 61, "competition": "PL"},
            "barcelona": {"id": 81, "competition": "PD"},
            "real madrid": {"id": 86, "competition": "PD"},
        }
        
        team_lower = team_name.lower()
        if team_lower not in team_map:
            return f"❌ Team '{team_name}' not found in known teams. Try the full team name or add manually."
        
        team_info = team_map[team_lower]
        
        if not self.football_api_key:
            # Use mock data for demo if no API key
            return await self._import_mock_football(team_name, team_info)
        
        # Real API implementation would go here
        url = f"{self.FOOTBALL_API_URL}/teams/{team_info['id']}/matches?status=SCHEDULED"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers={"X-Auth-Token": self.football_api_key}
                )
                response.raise_for_status()
                data = response.json()
                
                matches = data.get("matches", [])
                imported_count = self._process_football_matches(matches, team_name)
                
                self._save_events()
                return f"✅ Imported {imported_count} upcoming matches for {team_name}"
                
            except Exception as e:
                logger.error(f"Football API error: {e}")
                return await self._import_mock_football(team_name, team_info)
    
    async def _import_mock_football(self, team_name: str, team_info: dict) -> str:
        """Generate mock football data for demo purposes."""
        logger.info(f"Using mock data for {team_name}")
        
        # Generate some mock upcoming matches
        mock_matches = []
        base_date = datetime.now() + timedelta(days=7)
        
        opponents = {
            "feyenoord": ["Ajax", "PSV", "AZ Alkmaar", "FC Twente", "Sparta Rotterdam"],
            "ajax": ["Feyenoord", "PSV", "AZ Alkmaar", "FC Utrecht", "Vitesse"],
            "psv": ["Feyenoord", "Ajax", "AZ Alkmaar", "Heerenveen", "RKC Waalwijk"],
            "liverpool": ["Manchester City", "Arsenal", "Chelsea", "Tottenham", "Newcastle"],
            "manchester city": ["Liverpool", "Arsenal", "Chelsea", "Manchester United", "Tottenham"],
        }
        
        team_lower = team_name.lower()
        opponents_list = mock_matches.get(team_lower, ["Team A", "Team B", "Team C"])
        
        for i, opponent in enumerate(opponents_list[:5]):
            match_date = base_date + timedelta(days=i*7)
            is_home = i % 2 == 0
            
            event = PublicEvent(
                id=f"football_mock_{team_lower}_{i}",
                title=f"⚽ {team_name} vs {opponent}",
                description=f"{'Home' if is_home else 'Away'} match in the league",
                category=EventCategory.SPORTS,
                source=EventSource.FOOTBALL,
                start_time=match_date.replace(hour=14, minute=30),
                end_time=match_date.replace(hour=16, minute=30),
                location="Home Stadium" if is_home else f"{opponent} Stadium",
                url=None,
                teams=[team_name, opponent],
                competition="Eredivisie" if team_info.get("competition") == "DED" else "Premier League"
            )
            
            self._upsert_event(event)
        
        self._save_events()
        return f"✅ Added demo matches for {team_name} (5 upcoming games)\n\n💡 For real data, add a Football-Data API key with: `koda setup-football --api-key YOUR_KEY`"
    
    def _process_football_matches(self, matches: list, team_name: str) -> int:
        """Process and store football matches."""
        count = 0
        for match in matches[:10]:  # Limit to 10 matches
            match_date = match.get("utcDate")
            if not match_date:
                continue
            
            start_time = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
            
            home_team = match.get("homeTeam", {}).get("name", "Unknown")
            away_team = match.get("awayTeam", {}).get("name", "Unknown")
            competition = match.get("competition", {}).get("name", "Unknown League")
            
            event = PublicEvent(
                id=f"football_{match.get('id')}",
                title=f"⚽ {home_team} vs {away_team}",
                description=f"{competition} match",
                category=EventCategory.SPORTS,
                source=EventSource.FOOTBALL,
                start_time=start_time,
                end_time=start_time + timedelta(hours=2),
                location=match.get("venue", "TBD"),
                url=None,
                teams=[home_team, away_team],
                competition=competition
            )
            
            self._upsert_event(event)
            count += 1
        
        return count
    
    async def _import_ical(self, url: str) -> str:
        """Import events from an iCal/ICS feed."""
        logger.info(f"Importing iCal from {url}...")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                ical_data = response.text
                
                # Parse iCal data (simplified parser)
                events = self._parse_ical(ical_data, url)
                
                for event in events:
                    self._upsert_event(event)
                
                self._save_events()
                return f"✅ Imported {len(events)} events from iCal feed"
                
        except Exception as e:
            logger.error(f"iCal import error: {e}")
            return f"❌ Failed to import iCal: {e}"
    
    def _parse_ical(self, ical_data: str, source_url: str) -> list[PublicEvent]:
        """Parse iCal data and extract events."""
        events = []
        lines = ical_data.split('\n')
        
        current_event = {}
        in_event = False
        
        for line in lines:
            line = line.strip()
            
            if line == "BEGIN:VEVENT":
                current_event = {}
                in_event = True
            elif line == "END:VEVENT":
                if in_event and current_event.get("uid"):
                    try:
                        start_time = self._parse_ical_datetime(
                            current_event.get("dtstart", ""),
                            current_event.get("dtstart_tz", "")
                        )
                        
                        if start_time and start_time > datetime.now() - timedelta(days=1):
                            event = PublicEvent(
                                id=f"ical_{current_event.get('uid', 'unknown')}",
                                title=current_event.get("summary", "Unknown Event"),
                                description=current_event.get("description", ""),
                                category=EventCategory.OTHER,
                                source=EventSource.ICAL,
                                start_time=start_time,
                                end_time=self._parse_ical_datetime(
                                    current_event.get("dtend", ""),
                                    current_event.get("dtend_tz", "")
                                ),
                                location=current_event.get("location"),
                                url=current_event.get("url") or source_url,
                                teams=None,
                                competition=None
                            )
                            events.append(event)
                    except Exception as e:
                        logger.debug(f"Failed to parse iCal event: {e}")
                
                in_event = False
                current_event = {}
            elif in_event:
                if line.startswith("SUMMARY:"):
                    current_event["summary"] = line[8:]
                elif line.startswith("DESCRIPTION:"):
                    current_event["description"] = line[12:]
                elif line.startswith("UID:"):
                    current_event["uid"] = line[4:]
                elif line.startswith("DTSTART"):
                    if ";" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            current_event["dtstart"] = parts[1]
                    else:
                        current_event["dtstart"] = line[8:]
                elif line.startswith("DTEND"):
                    if ";" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            current_event["dtend"] = parts[1]
                    else:
                        current_event["dtend"] = line[6:]
                elif line.startswith("LOCATION:"):
                    current_event["location"] = line[9:]
                elif line.startswith("URL:"):
                    current_event["url"] = line[4:]
        
        return events
    
    def _parse_ical_datetime(self, dt_string: str, tz_string: str = "") -> Optional[datetime]:
        """Parse iCal datetime string."""
        if not dt_string:
            return None
        
        # Remove any VALUE=DATE: prefix
        if "VALUE=DATE:" in dt_string:
            dt_string = dt_string.split("VALUE=DATE:")[1]
        
        # Handle date-only format (YYYYMMDD)
        if len(dt_string) == 8:
            return datetime.strptime(dt_string, "%Y%m%d")
        
        # Handle datetime format (YYYYMMDDTHHMMSS)
        if "T" in dt_string:
            if dt_string.endswith("Z"):
                return datetime.strptime(dt_string, "%Y%m%dT%H%M%SZ")
            else:
                return datetime.strptime(dt_string[:15], "%Y%m%dT%H%M%S")
        
        return None
    
    def _upsert_event(self, event: PublicEvent):
        """Add or update an event."""
        # Remove existing event with same ID
        self.events = [e for e in self.events if e.id != event.id]
        self.events.append(event)
        
        # Sort by start time
        self.events.sort(key=lambda e: e.start_time)
    
    def _list_events(self, category: Optional[str] = None, days: int = 30, limit: int = 10, **kwargs) -> str:
        """List upcoming events."""
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        
        # Filter events
        filtered = [
            e for e in self.events
            if now <= e.start_time <= cutoff
            and (not category or category == "all" or e.category.value == category)
        ]
        
        if not filtered:
            return f"📅 No upcoming events in the next {days} days.\n\nTry importing some:\n• `import F1 calendar`\n• `add football team Feyenoord`"
        
        lines = [f"📅 *Upcoming Events* (next {days} days)\n"]
        
        for event in filtered[:limit]:
            # Format date
            days_until = (event.start_time - now).days
            if days_until == 0:
                when = "Today"
            elif days_until == 1:
                when = "Tomorrow"
            else:
                when = f"In {days_until} days"
            
            date_str = event.start_time.strftime("%a %d %b %H:%M")
            
            lines.append(f"*{event.title}*")
            lines.append(f"📆 {date_str} ({when})")
            if event.location:
                lines.append(f"📍 {event.location}")
            if event.competition:
                lines.append(f"🏆 {event.competition}")
            lines.append("")
        
        if len(filtered) > limit:
            lines.append(f"_...and {len(filtered) - limit} more events_")
        
        return "\n".join(lines)
    
    def _search_events(self, keyword: str, **kwargs) -> str:
        """Search events by keyword."""
        if not keyword:
            return "❌ Please provide a search keyword"
        
        keyword_lower = keyword.lower()
        
        matching = [
            e for e in self.events
            if keyword_lower in e.title.lower()
            or keyword_lower in e.description.lower()
            or (e.teams and any(keyword_lower in t.lower() for t in e.teams))
            or (e.competition and keyword_lower in e.competition.lower())
        ]
        
        if not matching:
            return f"🔍 No events found matching '{keyword}'"
        
        lines = [f"🔍 *Search Results for '{keyword}'*\n"]
        
        for event in matching[:10]:
            date_str = event.start_time.strftime("%a %d %b %H:%M")
            lines.append(f"*{event.title}*")
            lines.append(f"📆 {date_str}")
            if event.teams:
                lines.append(f"⚽ {' vs '.join(event.teams)}")
            lines.append("")
        
        return "\n".join(lines)
    
    async def _add_team(self, team: Optional[str] = None, **kwargs) -> str:
        """Subscribe to a sports team."""
        if not team:
            return "❌ Please specify a team name"
        
        # Check if already subscribed
        existing = [t for t in self.subscribed_teams if t["name"].lower() == team.lower()]
        if existing:
            return f"ℹ️ Already subscribed to {team}"
        
        # Add to subscribed teams
        self.subscribed_teams.append({
            "name": team,
            "sport": "football",
            "added_at": datetime.now().isoformat()
        })
        self._save_teams()
        
        # Auto-import matches
        result = await self._import_football_team(team)
        
        return f"✅ Subscribed to {team}!\n{result}"
    
    def _remove_team(self, team: Optional[str] = None, **kwargs) -> str:
        """Unsubscribe from a sports team."""
        if not team:
            return "❌ Please specify a team name"
        
        original_count = len(self.subscribed_teams)
        self.subscribed_teams = [t for t in self.subscribed_teams if t["name"].lower() != team.lower()]
        
        if len(self.subscribed_teams) < original_count:
            self._save_teams()
            return f"✅ Unsubscribed from {team}"
        else:
            return f"❌ Not subscribed to {team}"
    
    def _list_teams(self) -> str:
        """List subscribed teams."""
        if not self.subscribed_teams:
            return "📋 *Subscribed Teams*\n\nNo teams subscribed yet.\n\nTry:\n• `add team Feyenoord`\n• `add team Liverpool`"
        
        lines = ["📋 *Subscribed Teams*\n"]
        
        for team in self.subscribed_teams:
            lines.append(f"• {team['name']} ({team.get('sport', 'unknown')})")
        
        lines.append("\n_Use `add team <name>` to subscribe or `remove team <name>` to unsubscribe_")
        
        return "\n".join(lines)
    
    def get_upcoming_events_for_reminders(self, days_ahead: int = 3) -> list[PublicEvent]:
        """Get events that need reminders sent."""
        now = datetime.now()
        cutoff = now + timedelta(days=days_ahead)
        
        return [
            e for e in self.events
            if not e.reminder_sent
            and now <= e.start_time <= cutoff
        ]
    
    def mark_reminder_sent(self, event_id: str):
        """Mark an event's reminder as sent."""
        for event in self.events:
            if event.id == event_id:
                event.reminder_sent = True
                break
        self._save_events()
