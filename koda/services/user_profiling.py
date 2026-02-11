"""User profiling service for learning about the user over time.

Periodically asks questions to build a comprehensive user profile,
which is stored in memory and used for better personalization.

Examples of what we learn:
- Interests and hobbies
- Work/career details
- Family situation
- Preferences (food, music, travel, etc.)
- Goals and aspirations
- Daily routines
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from koda.config.loader import load_config
from koda.services.base import BaseService


@dataclass
class UserProfile:
    """Structured user profile data."""
    # Basic info
    name: str = ""
    age_range: str = ""  # "20s", "30s", etc.
    location: str = ""
    occupation: str = ""
    
    # Interests
    hobbies: list[str] = None
    sports_teams: list[str] = None
    music_genres: list[str] = None
    favorite_destinations: list[str] = None
    
    # Preferences
    food_preferences: list[str] = None  # "italian", "sushi", "vegetarian", etc.
    morning_person: Optional[bool] = None
    communication_style: str = ""  # "brief", "detailed", "formal", "casual"
    
    # Work
    work_schedule: str = ""  # "9-5", "flexible", "shift work"
    work_from_home: Optional[bool] = None
    industry: str = ""
    
    # Family
    relationship_status: str = ""  # "single", "married", "relationship"
    has_children: Optional[bool] = None
    has_pets: Optional[bool] = None
    
    # Goals
    short_term_goals: list[str] = None
    long_term_goals: list[str] = None
    
    # Learning progress
    profile_completeness: float = 0.0  # 0-100%
    last_question_date: Optional[str] = None
    questions_answered: int = 0
    
    def __post_init__(self):
        """Initialize list fields."""
        if self.hobbies is None:
            self.hobbies = []
        if self.sports_teams is None:
            self.sports_teams = []
        if self.music_genres is None:
            self.music_genres = []
        if self.favorite_destinations is None:
            self.favorite_destinations = []
        if self.food_preferences is None:
            self.food_preferences = []
        if self.short_term_goals is None:
            self.short_term_goals = []
        if self.long_term_goals is None:
            self.long_term_goals = []
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> UserProfile:
        return cls(**data)
    
    def calculate_completeness(self) -> float:
        """Calculate how complete the profile is (0-100%)."""
        fields = [
            self.name, self.age_range, self.location, self.occupation,
            self.hobbies, self.sports_teams, self.music_genres,
            self.food_preferences, self.communication_style,
            self.work_schedule, self.industry,
            self.relationship_status
        ]
        
        boolean_fields = [self.morning_person, self.work_from_home, self.has_children, self.has_pets]
        
        filled = sum(1 for f in fields if f)
        filled += sum(1 for f in boolean_fields if f is not None)
        
        total = len(fields) + len(boolean_fields)
        return (filled / total) * 100


class QuestionCategory:
    """Categories of profiling questions."""
    
    INTERESTS = [
        "What are your favorite hobbies or things to do in your free time?",
        "What kind of music do you enjoy listening to?",
        "Do you have any favorite sports teams?",
        "What type of movies or TV shows do you prefer?",
        "Are you into gaming? If so, what games?",
        "Do you enjoy reading? What genres?",
        "What kind of outdoor activities do you enjoy?",
        "Are there any causes or charities you care about?",
    ]
    
    WORK_CAREER = [
        "What industry do you work in?",
        "Do you prefer working from home or the office?",
        "Are you more productive in the morning or evening?",
        "What's your ideal work schedule?",
        "Do you have any career goals you're working toward?",
        "What do you enjoy most about your work?",
    ]
    
    PREFERENCES = [
        "What's your favorite cuisine or type of food?",
        "Do you prefer coffee or tea in the morning?",
        "Are you a planner or more spontaneous?",
        "Do you prefer brief updates or detailed explanations?",
        "What's your ideal way to relax after a busy day?",
        "Do you prefer traveling to cities or nature destinations?",
        "What's your favorite season and why?",
    ]
    
    PERSONAL = [
        "Do you have any pets?",
        "What's your family situation? (single, married, children?)",
        "Where did you grow up?",
        "Do you have any siblings?",
        "What's something most people don't know about you?",
    ]
    
    GOALS_ASPIRATIONS = [
        "What are you looking forward to in the coming months?",
        "Is there a skill you'd like to learn?",
        "Do you have any travel destinations on your bucket list?",
        "What would be your dream vacation?",
        "Are there any personal goals you're working toward?",
        "Where do you see yourself in 5 years?",
    ]
    
    ROUTINES = [
        "What's your typical morning routine like?",
        "How do you usually spend your weekends?",
        "Do you have any weekly traditions or rituals?",
        "What's your favorite time of day?",
        "How do you usually wind down before bed?",
    ]
    
    @classmethod
    def get_all_categories(cls) -> dict[str, list[str]]:
        return {
            "interests": cls.INTERESTS,
            "work_career": cls.WORK_CAREER,
            "preferences": cls.PREFERENCES,
            "personal": cls.PERSONAL,
            "goals": cls.GOALS_ASPIRATIONS,
            "routines": cls.ROUTINES,
        }


class UserProfilingService(BaseService):
    """
    Service that periodically asks questions to learn about the user.
    
    Builds a comprehensive profile over time through natural conversation,
    storing insights in both structured data and vector memory.
    
    Features:
    - Asks 1-2 questions per week
    - Tracks profile completeness
    - Adapts questions based on what we already know
    - Stores answers in memory for future reference
    """
    
    name = "user_profiling"
    description = "Periodically asks questions to learn about the user and build a profile"
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config
        self.profile: Optional[UserProfile] = None
        self.profile_file: Optional[Path] = None
        self.questions_asked_file: Optional[Path] = None
        self.asked_questions: list[str] = []
        
    def _init_storage(self):
        """Initialize storage paths."""
        workspace = Path.home() / ".koda" / "workspace"
        profile_dir = workspace / "user_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        self.profile_file = profile_dir / "profile.json"
        self.questions_asked_file = profile_dir / "questions_asked.json"
        
        self._load_profile()
        self._load_asked_questions()
    
    def _load_profile(self):
        """Load user profile from storage."""
        if self.profile_file and self.profile_file.exists():
            try:
                data = json.loads(self.profile_file.read_text())
                self.profile = UserProfile.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load profile: {e}")
                self.profile = UserProfile()
        else:
            self.profile = UserProfile()
    
    def _save_profile(self):
        """Save user profile to storage."""
        if self.profile and self.profile_file:
            self.profile_file.write_text(json.dumps(self.profile.to_dict(), indent=2))
    
    def _load_asked_questions(self):
        """Load list of already asked questions."""
        if self.questions_asked_file and self.questions_asked_file.exists():
            try:
                self.asked_questions = json.loads(self.questions_asked_file.read_text())
            except Exception:
                self.asked_questions = []
    
    def _save_asked_questions(self):
        """Save list of asked questions."""
        if self.questions_asked_file:
            # Keep only last 100 questions to avoid infinite growth
            self.questions_asked_file.write_text(
                json.dumps(self.asked_questions[-100:], indent=2)
            )
    
    async def start(self) -> None:
        """Start the user profiling service."""
        logger.info("👤 Starting User Profiling Service...")
        self._init_storage()
        
        # Update completeness
        if self.profile:
            self.profile.profile_completeness = self.profile.calculate_completeness()
            self._save_profile()
        
        logger.info(f"✅ User Profiling Service started (profile {self.profile.profile_completeness:.0f}% complete)")
    
    async def stop(self) -> None:
        """Stop the service."""
        logger.info("User Profiling Service stopped")
    
    def should_ask_question(self) -> bool:
        """Check if it's time to ask a new question."""
        if not self.profile:
            return False
        
        if not self.profile.last_question_date:
            return True
        
        try:
            last_date = datetime.fromisoformat(self.profile.last_question_date)
            days_since = (datetime.now() - last_date).days
            
            # Ask 1-2 questions per week (every 3-5 days)
            return days_since >= 4
        except:
            return True
    
    def select_question(self) -> tuple[str, str]:
        """Select an appropriate question to ask.
        
        Returns:
            Tuple of (category, question)
        """
        categories = QuestionCategory.get_all_categories()
        
        # Prioritize categories based on profile completeness
        # Focus on interests and preferences first, personal last
        priority_order = [
            ("interests", not self.profile.hobbies),
            ("preferences", not self.profile.food_preferences),
            ("work_career", not self.profile.occupation),
            ("routines", not self.profile.work_schedule),
            ("goals", not self.profile.short_term_goals),
            ("personal", not self.profile.relationship_status),
        ]
        
        # Sort by priority (missing info first)
        priority_order.sort(key=lambda x: not x[1])
        
        # Try to find a question we haven't asked yet
        for category_name, _ in priority_order:
            available = [
                q for q in categories.get(category_name, [])
                if q not in self.asked_questions
            ]
            if available:
                return category_name, random.choice(available)
        
        # If all questions asked, pick any random one
        all_questions = [q for qs in categories.values() for q in qs]
        return "general", random.choice(all_questions)
    
    def format_question_message(self, question: str) -> str:
        """Format a question for sending to the user."""
        intros = [
            "Ik ben bezig met het leren jou beter te kennen, zodat ik betere suggesties kan doen. 🎯",
            "Om je nog beter te kunnen helpen, zou ik graag wat meer over je willen weten. 🤔",
            "Ik bouw een profiel op om je persoonlijker van dienst te zijn. 💡",
            "Vraagje! Dit helpt me om je beter te begrijpen. 📝",
        ]
        
        intro = random.choice(intros)
        completeness = self.profile.profile_completeness if self.profile else 0
        
        message = f"{intro}\n\n*{question}*\n\n"
        
        if completeness < 30:
            message += "_Je kunt altijd antwoorden met 'sla over' als je dit nu niet wilt beantwoorden._"
        
        return message
    
    async def ask_question(self) -> Optional[str]:
        """Ask the user a profiling question.
        
        Returns:
            The question message sent, or None if no question was sent.
        """
        if not self.should_ask_question():
            return None
        
        category, question = self.select_question()
        message = self.format_question_message(question)
        
        # Send via WhatsApp
        try:
            from koda.services.manager import ServiceManager
            manager = ServiceManager()
            
            wa_channel = None
            for channel in manager.channels.values():
                if channel.name == "whatsapp":
                    wa_channel = channel
                    break
            
            if not wa_channel:
                logger.warning("WhatsApp channel not available for profiling")
                return None
            
            # Get owner phone
            config = load_config()
            owner_phone = config.channels.whatsapp.owner_phone
            
            if not owner_phone:
                return None
            
            # Format JID
            jid = f"{owner_phone.replace('+', '')}@s.whatsapp.net"
            
            # Send message
            from koda.messaging.queue import OutboundMessage
            msg = OutboundMessage(
                channel="whatsapp",
                chat_id=jid,
                content=message
            )
            
            await wa_channel.send(msg)
            
            # Track that we asked this question
            self.asked_questions.append(question)
            self._save_asked_questions()
            
            # Update last question date
            self.profile.last_question_date = datetime.now().isoformat()
            self._save_profile()
            
            logger.info(f"Sent profiling question: {question[:50]}...")
            return message
            
        except Exception as e:
            logger.error(f"Failed to send profiling question: {e}")
            return None
    
    def process_answer(self, question: str, answer: str) -> bool:
        """Process the user's answer to a profiling question.
        
        Args:
            question: The question that was asked
            answer: The user's answer
            
        Returns:
            True if the answer was processed successfully
        """
        try:
            # Store in vector memory
            self._store_in_memory(question, answer)
            
            # Extract structured data
            self._extract_structured_data(question, answer)
            
            # Update stats
            self.profile.questions_answered += 1
            self.profile.profile_completeness = self.profile.calculate_completeness()
            self._save_profile()
            
            logger.info(f"Processed profiling answer for: {question[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process profiling answer: {e}")
            return False
    
    def _store_in_memory(self, question: str, answer: str):
        """Store the Q&A in vector memory."""
        try:
            # This would integrate with your vector memory system
            # For now, we'll store it in a simple text file
            memory_file = self.profile_file.parent / "profile_memory.txt"
            
            entry = f"\n[{datetime.now().isoformat()}]\nQ: {question}\nA: {answer}\n{'='*50}"
            
            with open(memory_file, "a") as f:
                f.write(entry)
                
        except Exception as e:
            logger.error(f"Failed to store in memory: {e}")
    
    def _extract_structured_data(self, question: str, answer: str):
        """Extract structured data from the answer."""
        answer_lower = answer.lower()
        
        # Simple keyword extraction (in production, use LLM for this)
        if "hobby" in question.lower() or "free time" in question.lower():
            # Extract hobbies
            hobbies = [h.strip() for h in answer.split(",") if len(h.strip()) > 2]
            self.profile.hobbies.extend(hobbies)
        
        elif "sport" in question.lower() or "team" in question.lower():
            # Extract sports teams
            teams = [t.strip() for t in answer.split(",") if len(t.strip()) > 2]
            self.profile.sports_teams.extend(teams)
            
            # Auto-subscribe to football teams in public events
            for team in teams:
                if any(club in team.lower() for club in ["feyenoord", "ajax", "psv", "liverpool", "arsenal"]):
                    # This would trigger a subscription
                    logger.info(f"Detected football team: {team}")
        
        elif "food" in question.lower() or "cuisine" in question.lower():
            foods = [f.strip() for f in answer.split(",") if len(f.strip()) > 2]
            self.profile.food_preferences.extend(foods)
        
        elif "work" in question.lower() or "job" in question.lower() or "occupation" in question.lower():
            self.profile.occupation = answer[:100]
        
        elif "industry" in question.lower():
            self.profile.industry = answer[:50]
        
        elif "morning" in question.lower() and ("person" in question.lower() or "productive" in question.lower()):
            if any(word in answer_lower for word in ["morning", "early", "ochtend"]):
                self.profile.morning_person = True
            elif any(word in answer_lower for word in ["evening", "night", "avond", "nacht"]):
                self.profile.morning_person = False
        
        elif "home" in question.lower() and "work" in question.lower():
            if any(word in answer_lower for word in ["home", "thuis", "remote"]):
                self.profile.work_from_home = True
            elif any(word in answer_lower for word in ["office", "kantoor", "onsite"]):
                self.profile.work_from_home = False
    
    def get_profile_summary(self) -> str:
        """Get a summary of the user profile."""
        if not self.profile:
            return "No profile data yet."
        
        lines = ["👤 *Your Profile*\n"]
        
        if self.profile.occupation:
            lines.append(f"💼 *Work:* {self.profile.occupation}")
        
        if self.profile.hobbies:
            lines.append(f"🎯 *Hobbies:* {', '.join(self.profile.hobbies[:5])}")
        
        if self.profile.sports_teams:
            lines.append(f"⚽ *Teams:* {', '.join(self.profile.sports_teams)}")
        
        if self.profile.food_preferences:
            lines.append(f"🍽️ *Food:* {', '.join(self.profile.food_preferences[:5])}")
        
        lines.append(f"\n📊 *Profile completeness:* {self.profile.profile_completeness:.0f}%")
        lines.append(f"📝 *Questions answered:* {self.profile.questions_answered}")
        
        return "\n".join(lines)
    
    def get_suggestions(self) -> list[str]:
        """Get personalized suggestions based on the profile."""
        suggestions = []
        
        if not self.profile:
            return suggestions
        
        # Sports suggestions
        if self.profile.sports_teams:
            suggestions.append(f"🏎️ I've imported calendars for: {', '.join(self.profile.sports_teams)}")
        
        # Food suggestions
        if self.profile.food_preferences:
            suggestions.append(f"🍽️ Looking for {random.choice(self.profile.food_preferences)} restaurants?")
        
        # Activity suggestions based on hobbies
        if self.profile.hobbies:
            hobby = random.choice(self.profile.hobbies)
            suggestions.append(f"🎯 Since you enjoy {hobby}, would you like me to find related events?")
        
        # Weekend planning
        if self.profile.work_schedule:
            suggestions.append("📅 Shall I plan your weekend based on your preferences?")
        
        return suggestions


# Scheduler integration
async def send_profiling_question() -> str:
    """Send a profiling question (called by scheduler)."""
    service = UserProfilingService()
    await service.start()
    
    if service.should_ask_question():
        question = await service.ask_question()
        await service.stop()
        
        if question:
            return "Sent profiling question to user"
        return "Could not send profiling question"
    
    await service.stop()
    return "Not time for a new question yet"


async def process_profiling_answer(question: str, answer: str) -> str:
    """Process a user's answer to a profiling question."""
    service = UserProfilingService()
    await service.start()
    
    success = service.process_answer(question, answer)
    await service.stop()
    
    if success:
        return "Answer processed and saved to your profile"
    return "Failed to process answer"
