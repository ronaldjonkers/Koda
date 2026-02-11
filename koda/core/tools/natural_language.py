"""Natural Language Command Processor - Understand user intent, not just commands.

This module enables the AI to understand natural, conversational requests
and translate them into the appropriate actions. Instead of requiring
specific command syntax, users can speak naturally.

Examples:
- "What does my day look like?" → calendar today
- "Remind me to call mom tomorrow" → add_reminder
- "Do I have any meetings this week?" → calendar list days=7
- "Wish John happy birthday" → message + check birthday
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Any, Optional

from loguru import logger

from koda.core.tools.base import BaseTool


@dataclass
class ParsedIntent:
    """Represents a parsed user intent."""
    intent: str
    action: str
    parameters: dict[str, Any]
    confidence: float
    original_query: str


class NaturalLanguageProcessor:
    """
    Process natural language into structured commands.
    
    This class handles the translation from natural, conversational
    language to specific tool invocations.
    """
    
    def __init__(self):
        self.patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> dict[str, list[tuple[re.Pattern, callable]]]:
        """Compile regex patterns for intent matching."""
        patterns = {}
        
        # Calendar intents
        patterns["calendar"] = [
            # Today's agenda
            (re.compile(r"(?:what's|what is|wat is|wat staat|hoe ziet).*?(?:my day|mijn dag|vandaag|today).*?(?:look like|staat|er op)?", re.I), 
             self._parse_today_intent),
            
            # This week
            (re.compile(r"(?:what|wat).*?(?:this week|deze week|komende week).*?(?:have|heb|staat|agenda)?", re.I),
             self._parse_week_intent),
            
            # Upcoming events
            (re.compile(r"(?:what's|what is|wat).*?(?:coming up|aanstaande|binnenkort|upcoming)", re.I),
             self._parse_upcoming_intent),
            
            # Check availability
            (re.compile(r"(?:am i|ben ik).*?(?:free|beschikbaar|vrij).*?(?:at|om)?\s*(.+?)(?:\?|$)", re.I),
             self._parse_availability_intent),
            
            # Create event
            (re.compile(r"(?:schedule|plan|maak|create).*?(?:meeting|afspraak|event|call|appointment).*?(?:with|met)?\s*(.+?)(?:\s+(?:at|op|om)\s+(.+))?$", re.I),
             self._parse_create_event_intent),
        ]
        
        # Reminder intents
        patterns["reminder"] = [
            # Remind me to...
            (re.compile(r"(?:remind|herinner).*?(?:me|mij)?\s+(?:to|om)?\s+(.+?)(?:\s+(?:at|op|om|in)\s+(.+))?$", re.I),
             self._parse_reminder_intent),
            
            # Don't let me forget
            (re.compile(r"(?:don't let|laat).*?(?:me|mij).*?(?:forget|vergeten).*?(.+?)(?:$|\?)", re.I),
             self._parse_reminder_intent),
        ]
        
        # Email intents
        patterns["email"] = [
            # Check emails
            (re.compile(r"(?:check|any|do i have|heb ik).*?(?:emails?|mails?|berichten)", re.I),
             self._parse_check_email_intent),
            
            # Important emails
            (re.compile(r"(?:important|urgent|belangrijk|dringend).*?(?:emails?|mails?)", re.I),
             self._parse_important_email_intent),
            
            # Send email
            (re.compile(r"(?:send|stuur|email|mail).*?(?:to|aan)?\s*(.+?)(?:\s+(?:about|over|regarding)\s+(.+))?$", re.I),
             self._parse_send_email_intent),
        ]
        
        # Birthday intents
        patterns["birthday"] = [
            # Upcoming birthdays
            (re.compile(r"(?:any|upcoming|binnenkort|aankomend).*?(?:birthdays?|verjaardagen?)", re.I),
             self._parse_upcoming_birthdays_intent),
            
            # Someone's birthday
            (re.compile(r"(?:when is|wanneer is).*?(?:(.+?)'?s?|van)\s+(?:birthday|verjaardag)", re.I),
             self._parse_specific_birthday_intent),
            
            # Wish happy birthday
            (re.compile(r"(?:wish|feliciteer).*?(?:happy birthday|gefeliciteerd|van harte)?\s*(?:to|met)?\s*(.+?)$", re.I),
             self._parse_wish_birthday_intent),
        ]
        
        # Contact intents
        patterns["contact"] = [
            # Find contact
            (re.compile(r"(?:find|zoek|lookup|look up).*?(?:contact|number|phone|email).*?(?:for|van)?\s*(.+?)$", re.I),
             self._parse_find_contact_intent),
        ]
        
        # Morning briefing
        patterns["briefing"] = [
            (re.compile(r"(?:morning|briefing|dagoverzicht|overzicht|good morning|goedemorgen)", re.I),
             self._parse_morning_briefing_intent),
        ]
        
        return patterns
    
    def parse(self, query: str) -> Optional[ParsedIntent]:
        """
        Parse a natural language query into a structured intent.
        
        Args:
            query: The natural language query
            
        Returns:
            ParsedIntent or None if no match
        """
        for intent_type, patterns in self.patterns.items():
            for pattern, parser in patterns:
                match = pattern.search(query)
                if match:
                    try:
                        action, params, confidence = parser(match, query)
                        return ParsedIntent(
                            intent=intent_type,
                            action=action,
                            parameters=params,
                            confidence=confidence,
                            original_query=query
                        )
                    except Exception as e:
                        logger.debug(f"Parser failed for '{query}': {e}")
                        continue
        
        return None
    
    # ============== Calendar Parsers ==============
    
    def _parse_today_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "calendar_today", {"action": "today"}, 0.9
    
    def _parse_week_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "calendar_week", {"action": "week"}, 0.85
    
    def _parse_upcoming_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "calendar_upcoming", {"action": "upcoming", "hours": 48}, 0.8
    
    def _parse_availability_intent(self, match, query: str) -> tuple[str, dict, float]:
        time_str = match.group(1) if match.groups() else ""
        return "calendar_check", {
            "action": "conflicts",
            "start": self._parse_time_to_iso(time_str),
            "end": self._parse_time_to_iso(time_str, add_hours=1)
        }, 0.75
    
    def _parse_create_event_intent(self, match, query: str) -> tuple[str, dict, float]:
        groups = match.groups()
        subject = groups[0] if groups else "New Event"
        time_str = groups[1] if len(groups) > 1 else None
        
        start_time = self._parse_time_to_iso(time_str) if time_str else self._get_default_event_time()
        end_time = self._parse_time_to_iso(time_str, add_hours=1) if time_str else self._get_default_event_time(add_hours=1)
        
        return "calendar_create", {
            "action": "create",
            "summary": subject.strip(),
            "start": start_time,
            "end": end_time
        }, 0.8
    
    # ============== Reminder Parsers ==============
    
    def _parse_reminder_intent(self, match, query: str) -> tuple[str, dict, float]:
        groups = match.groups()
        task = groups[0] if groups else "Reminder"
        time_str = groups[1] if len(groups) > 1 else None
        
        when = time_str if time_str else "+30 minutes"
        
        return "proactive_reminder", {
            "action": "add_reminder",
            "title": task.strip(),
            "message": f"Herinnering: {task.strip()}",
            "when": when,
            "priority": "normal"
        }, 0.85
    
    # ============== Email Parsers ==============
    
    def _parse_check_email_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "email_check", {"action": "list", "unread_only": True}, 0.8
    
    def _parse_important_email_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "email_important", {"action": "list", "priority": "high"}, 0.85
    
    def _parse_send_email_intent(self, match, query: str) -> tuple[str, dict, float]:
        groups = match.groups()
        recipient = groups[0] if groups else ""
        subject = groups[1] if len(groups) > 1 else ""
        
        return "email_send", {
            "action": "send",
            "to": recipient.strip(),
            "subject": subject.strip() if subject else "No subject"
        }, 0.75
    
    # ============== Birthday Parsers ==============
    
    def _parse_upcoming_birthdays_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "birthday_upcoming", {"action": "birthdays", "days": 30}, 0.9
    
    def _parse_specific_birthday_intent(self, match, query: str) -> tuple[str, dict, float]:
        name = match.group(1) if match.groups() else ""
        return "birthday_lookup", {
            "action": "birthdays",
            "search_name": name.strip()
        }, 0.8
    
    def _parse_wish_birthday_intent(self, match, query: str) -> tuple[str, dict, float]:
        name = match.group(1) if match.groups() else ""
        return "birthday_wish", {
            "action": "birthdays",
            "wish_name": name.strip()
        }, 0.85
    
    # ============== Contact Parsers ==============
    
    def _parse_find_contact_intent(self, match, query: str) -> tuple[str, dict, float]:
        name = match.group(1) if match.groups() else ""
        return "contact_find", {"action": "search", "query": name.strip()}, 0.8
    
    # ============== Briefing Parsers ==============
    
    def _parse_morning_briefing_intent(self, match, query: str) -> tuple[str, dict, float]:
        return "morning_briefing", {"action": "morning_briefing"}, 0.95
    
    # ============== Helper Methods ==============
    
    def _parse_time_to_iso(self, time_str: str | None, add_hours: int = 0) -> str:
        """Parse a time string to ISO format."""
        if not time_str:
            dt = datetime.now() + timedelta(hours=add_hours)
            return dt.isoformat()
        
        time_str = time_str.strip().lower()
        
        # Try to parse relative times
        if "tomorrow" in time_str or "morgen" in time_str:
            dt = datetime.now() + timedelta(days=1)
            # Try to extract time
            time_match = re.search(r'(\d{1,2})[:\.](\d{2})', time_str)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            return (dt + timedelta(hours=add_hours)).isoformat()
        
        if "today" in time_str or "vandaag" in time_str:
            dt = datetime.now()
            time_match = re.search(r'(\d{1,2})[:\.](\d{2})', time_str)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return (dt + timedelta(hours=add_hours)).isoformat()
        
        # Try ISO format
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            return (dt + timedelta(hours=add_hours)).isoformat()
        except:
            pass
        
        # Default
        dt = datetime.now() + timedelta(hours=add_hours)
        return dt.isoformat()
    
    def _get_default_event_time(self, add_hours: int = 0) -> str:
        """Get default event time (next hour)."""
        now = datetime.now()
        # Round to next hour
        if now.minute > 0:
            now = now + timedelta(hours=1)
        now = now.replace(minute=0, second=0, microsecond=0)
        return (now + timedelta(hours=add_hours)).isoformat()


class NaturalLanguageTool(BaseTool):
    """
    Tool for understanding and processing natural language commands.
    
    This tool acts as a translator between conversational language
    and structured commands. It helps the AI understand what the user
    wants even when they don't use specific command syntax.
    
    Actions:
    - parse: Parse a natural language query into a structured intent
    - suggest: Suggest what the user might want to do
    - examples: Show examples of natural language commands
    
    The AI should use this tool when:
    - The user asks something in conversational language
    - You're not sure what action the user wants
    - You want to provide smart suggestions
    """
    
    name = "natural_language"
    description = """Understand and process natural language commands.

This tool translates conversational language into structured commands,
allowing users to speak naturally instead of using specific syntax.

Use this when:
- The user asks something in natural/conversational language
- You're not sure what specific action they want
- You want to understand the intent behind a vague request

Actions:
- parse: Analyze a query and return the detected intent and parameters
- suggest: Get smart suggestions for what the user might want
- examples: Show example natural language commands

Parameters for 'parse':
- query: The natural language query to parse (required)

Parameters for 'suggest':
- context: Optional context about what the user is doing

The tool returns structured information that helps you decide
which other tools to call to fulfill the user's request.
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["parse", "suggest", "examples"],
                "description": "Action to perform"
            },
            "query": {
                "type": "string",
                "description": "Natural language query to parse"
            },
            "context": {
                "type": "string",
                "description": "Optional context for suggestions"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.processor = NaturalLanguageProcessor()
    
    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "parse")
        
        if action == "parse":
            return await self._parse(**kwargs)
        elif action == "suggest":
            return await self._suggest(**kwargs)
        elif action == "examples":
            return await self._examples()
        else:
            return f"Unknown action: {action}"
    
    async def _parse(self, **kwargs) -> str:
        """Parse a natural language query."""
        query = kwargs.get("query", "")
        
        if not query:
            return "❌ Error: query is required for parsing."
        
        intent = self.processor.parse(query)
        
        if intent:
            return (
                f"**Begrepen intentie:**\n\n"
                f"📋 **Type:** {intent.intent}\n"
                f"🔧 **Actie:** {intent.action}\n"
                f"📊 **Zekerheid:** {intent.confidence * 100:.0f}%\n\n"
                f"**Parameters:**\n"
                f"```json\n{json.dumps(intent.parameters, indent=2, default=str)}\n```\n\n"
                f"_Je kunt nu de juiste tools aanroepen met deze parameters._"
            )
        else:
            return (
                f"❓ **Kon de vraag niet begrijpen:** '{query}'\n\n"
                f"Probeer het te herformuleren of gebruik specifiekere commando's.\n\n"
                f"Gebruik `action: examples` om voorbeelden te zien van wat ik begrijp."
            )
    
    async def _suggest(self, **kwargs) -> str:
        """Suggest actions based on context."""
        context = kwargs.get("context", "")
        
        # Get time-based suggestions
        hour = datetime.now().hour
        suggestions = []
        
        if 7 <= hour < 10:
            suggestions.append("🌅 Goedemorgen! Wil je je dagoverzicht zien?")
            suggestions.append("📅 Check je agenda voor vandaag")
        elif 10 <= hour < 12:
            suggestions.append("📧 Bekijk belangrijke emails")
        elif 12 <= hour < 14:
            suggestions.append("🍽️ Lunchtijd! Check of je afspraken hebt vanmiddag")
        elif 14 <= hour < 17:
            suggestions.append("📅 Komende afspraken bekijken")
        elif 17 <= hour < 19:
            suggestions.append("🌆 Einde werkdag - samenvatting van morgen bekijken?")
        else:
            suggestions.append("📅 Agenda voor morgen bekijken")
        
        # Add context-specific suggestions
        if context:
            if "meeting" in context.lower() or "afspraak" in context.lower():
                suggestions.append("🤔 Moet je nog een meeting inplannen?")
            if "birthday" in context.lower() or "verjaardag" in context.lower():
                suggestions.append("🎂 Komende verjaardagen bekijken")
        
        lines = ["**💡 Suggesties:**\n"]
        for i, s in enumerate(suggestions[:3], 1):
            lines.append(f"{i}. {s}")
        
        return "\n".join(lines)
    
    async def _examples(self) -> str:
        """Show example natural language commands."""
        return """**🗣️ Voorbeelden van natuurlijke commando's:**

**Agenda & Afspraken:**
• "Hoe ziet mijn dag eruit?" / "What does my day look like?"
• "Wat staat er deze week op de agenda?"
• "Plan een meeting met John morgen om 14:00"
• "Heb ik morgen tijd om 15:00?"
• "Wat komt er aan?"

**Herinneringen:**
• "Herinner me om morgen de belasting te doen"
• "Remind me to call mom in 30 minutes"
• "Laat me niet vergeten om de presentatie te maken"

**Email:**
• "Heb ik belangrijke emails?"
• "Check mijn inbox"
• "Stuur een email aan Peter over het project"

**Verjaardagen:**
• "Zijn er binnenkort verjaardagen?"
• "Wanneer is Anna jarig?"
• "Feliciteer John met zijn verjaardag"

**Contacten:**
• "Zoek het telefoonnummer van Sarah"
• "Find contact info for the marketing team"

**Overzicht:**
• "Goedemorgen" / "Morning briefing"
• "Geef me een overzicht"

_You can speak naturally - I'll do my best to understand!_ 🎯
"""


import json  # Import at end to avoid circular issues
