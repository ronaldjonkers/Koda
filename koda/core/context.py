"""Context builder for assembling agent prompts."""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from koda.core.memory import MemoryStore
from koda.core.skills.loader import SkillsLoader


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(
        self,
        workspace: Path,
        assistant_name: str = "Koda",
        user_name: str = "",
        default_language: str = "en"
    ):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader([
            Path.home() / ".koda" / "skills",
            workspace / "skills",
        ])
        self.assistant_name = assistant_name
        self.user_name = user_name
        self.default_language = default_language
    
    def build_system_prompt(
        self,
        skill_names: list[str] | None = None,
        detected_language: str | None = None
    ) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
            detected_language: Language detected from user's message.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity with language detection
        parts.append(self._get_identity(detected_language))
        
        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - show available skills (agent uses read_file to load full content)
        skills_prompt = self.skills.get_skills_prompt()
        if skills_prompt:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Before responding, check if any skill matches the user's request.

{skills_prompt}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self, detected_language: str | None = None) -> str:
        """Get the core identity section."""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        
        # Language instruction
        lang = detected_language or self.default_language
        language_instruction = self._get_language_instruction(lang)
        
        # Build explicit identity section
        identity_section = f"""## Your Identity
**Your name is: {self.assistant_name}**
When someone asks your name, you answer: "{self.assistant_name}"."""

        # Build explicit user section
        if self.user_name:
            user_section = f"""## About the User
**The user's name is: {self.user_name}**
When someone asks who they are or what their name is, you answer: "{self.user_name}".
Always address {self.user_name} by name when appropriate."""
        else:
            user_section = """## About the User
The user has not provided their name. You may ask for it if needed."""
        
        return f"""# {self.assistant_name} 🐈

You are {self.assistant_name}, a personal AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Manage calendars (Google, Exchange, CalDAV)
- Send WhatsApp messages to ANY contact or phone number (not just the owner - ANYONE)
- Spawn subagents for complex background tasks

{identity_section}

{user_section}

## Language
{language_instruction}

## Current Time
{now}

## Workspace
Your workspace is at: {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering something, write to {workspace_path}/memory/MEMORY.md"""
    
    def _get_language_instruction(self, lang: str) -> str:
        """Get language instruction based on detected or default language."""
        language_names = {
            "nl": "Nederlands",
            "en": "English",
            "de": "Deutsch",
            "fr": "Français",
            "es": "Español",
            "it": "Italiano",
            "pt": "Português",
        }
        
        lang_name = language_names.get(lang, lang)
        
        return f"""**CRITICAL LANGUAGE RULES - ALWAYS FOLLOW:**

1. **Match the user's language**: Always respond in the SAME language the user writes in.
   - User writes Dutch → You respond in Dutch
   - User writes English → You respond in English
   - User writes German → You respond in German

2. **Honor explicit language requests**: If the user asks you to write something in a specific language, use THAT language for the content:
   - "Schrijf een email in het Engels" → Write the email in English
   - "Write this in Dutch" → Write it in Dutch
   - "Stel een bericht op in het Duits" → Compose the message in German

3. **Task language vs conversation language**: 
   - Your conversational replies should match the user's message language
   - Content you create (emails, documents) should be in the language the user specifies for that content

Current detected language: {lang_name}

This applies to ALL your output:
- Conversational replies
- Error messages and confirmations
- Questions you ask
- Calendar events and reminders
- Any generated content (unless user specifies otherwise)"""
    
    def detect_language(self, text: str) -> str:
        """
        Detect the language of the given text.
        
        Uses simple heuristics for common languages.
        Falls back to default_language if detection fails.
        """
        if not text or len(text) < 10:
            return self.default_language
        
        text_lower = text.lower()
        
        # Dutch indicators
        dutch_words = ["ik", "je", "het", "een", "van", "dat", "wat", "voor", "met", "aan", 
                       "naar", "zijn", "niet", "heb", "wil", "kan", "zou", "moet", "deze",
                       "afspraak", "agenda", "morgen", "vandaag", "graag", "alsjeblieft"]
        dutch_count = sum(1 for word in dutch_words if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}"))
        
        # German indicators
        german_words = ["ich", "du", "das", "ist", "ein", "eine", "und", "der", "die", 
                        "nicht", "auf", "mit", "für", "sie", "wir", "haben", "werden",
                        "können", "möchte", "bitte", "danke", "termin"]
        german_count = sum(1 for word in german_words if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}"))
        
        # French indicators
        french_words = ["je", "tu", "le", "la", "les", "un", "une", "est", "sont", 
                        "pour", "avec", "dans", "que", "qui", "nous", "vous", "ils",
                        "rendez-vous", "calendrier", "demain", "aujourd'hui", "merci"]
        french_count = sum(1 for word in french_words if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}"))
        
        # Spanish indicators
        spanish_words = ["yo", "el", "la", "los", "las", "un", "una", "es", "son",
                         "para", "con", "que", "por", "como", "pero", "cuando",
                         "cita", "calendario", "mañana", "hoy", "gracias", "por favor"]
        spanish_count = sum(1 for word in spanish_words if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}"))
        
        # English is the fallback, but check for some indicators
        english_words = ["the", "is", "are", "was", "were", "have", "has", "will",
                         "would", "could", "should", "can", "this", "that", "what",
                         "when", "where", "who", "how", "please", "thank", "meeting",
                         "calendar", "tomorrow", "today", "schedule", "appointment"]
        english_count = sum(1 for word in english_words if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}"))
        
        # Determine the most likely language
        scores = {
            "nl": dutch_count,
            "de": german_count,
            "fr": french_count,
            "es": spanish_count,
            "en": english_count,
        }
        
        max_score = max(scores.values())
        if max_score == 0:
            return self.default_language
        
        # Return language with highest score
        for lang, score in scores.items():
            if score == max_score:
                return lang
        
        return self.default_language
    
    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # Detect language from current message
        detected_language = self.detect_language(current_message)

        # System prompt with detected language
        system_prompt = self.build_system_prompt(skill_names, detected_language)
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.
        
        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.
        
        Returns:
            Updated message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        
        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
        
        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        messages.append(msg)
        return messages
