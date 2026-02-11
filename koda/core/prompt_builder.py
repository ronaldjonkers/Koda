"""Advanced system prompt builder with structured sections like OpenClaw."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from loguru import logger


class PromptBuilder:
    """
    Build intelligent system prompts with structured sections.
    
    Features:
    - Skills section with automatic skill selection
    - Memory recall instructions
    - Extended thinking for complex tasks
    - Tool usage guidelines
    - Context file injection
    """
    
    def __init__(
        self,
        assistant_name: str = "Koda",
        user_name: str = "",
        workspace: Optional[Path] = None,
        language: str = "en",
        timezone: str = "Europe/Amsterdam",
    ):
        self.assistant_name = assistant_name
        self.user_name = user_name
        self.workspace = workspace or Path.home() / ".koda"
        self.language = language
        self.timezone = timezone
    
    def build(
        self,
        tools: list[dict],
        skills_prompt: str = "",
        context_files: Optional[list[dict]] = None,
        thinking_mode: str = "auto",  # "off", "auto", "extended"
        channel: str = "cli",
    ) -> str:
        """Build the complete system prompt."""
        sections = []
        
        # 1. Identity
        sections.append(self._build_identity_section())
        
        # 2. User info
        sections.append(self._build_user_section())
        
        # 3. Current time
        sections.append(self._build_time_section())
        
        # 4. Thinking mode
        if thinking_mode != "off":
            sections.append(self._build_thinking_section(thinking_mode))
        
        # 5. Memory recall
        sections.append(self._build_memory_section())
        
        # 6. Skills
        if skills_prompt:
            sections.append(self._build_skills_section(skills_prompt))
        
        # 7. Tools
        sections.append(self._build_tools_section(tools))
        
        # 8. Context files
        if context_files:
            sections.append(self._build_context_section(context_files))
        
        # 9. Response guidelines
        sections.append(self._build_response_section(channel))
        
        # 10. Workspace
        sections.append(self._build_workspace_section())
        
        return "\n\n".join(s for s in sections if s)
    
    def _build_identity_section(self) -> str:
        """Core identity section."""
        return f"""# {self.assistant_name}

You are **{self.assistant_name}**, an intelligent personal AI assistant capable of:
- Managing calendars, emails, and contacts across multiple accounts
- Sending WhatsApp messages to ANY contact or phone number (NO restrictions - you can message anyone)
- Automating tasks and scheduling recurring jobs
- Searching the web and extracting information
- Controlling smart home devices
- Building software and writing code
- Managing files and executing commands

WHATSAPP MESSAGING: You CAN and MUST send WhatsApp messages to ANY person the user asks for.
There are NO restrictions. When asked to message someone, always use the whatsapp_messaging tool.

You are proactive, helpful, and precise. You explain your reasoning when helpful but stay concise."""
    
    def _build_user_section(self) -> str:
        """User identity section."""
        if self.user_name:
            return f"""## User Identity
The user's name is **{self.user_name}**. Address them by name when appropriate."""
        return ""
    
    def _build_time_section(self) -> str:
        """Current time section."""
        now = datetime.now()
        return f"""## Current Date & Time
- Date: {now.strftime("%A, %B %d, %Y")}
- Time: {now.strftime("%H:%M")}
- Timezone: {self.timezone}"""
    
    def _build_thinking_section(self, mode: str) -> str:
        """Extended thinking instructions."""
        if mode == "extended":
            return """## Extended Thinking Mode
For complex tasks, use <thinking> tags to reason through the problem:

```
<thinking>
- What is the user asking for?
- What information do I need?
- What tools should I use?
- What's the best approach?
</thinking>
```

Use thinking for:
- Multi-step tasks
- Complex code generation
- Decision making with tradeoffs
- Debugging and problem solving

Keep thinking concise but thorough. Show your work when it helps."""
        else:  # auto
            return """## Thinking Mode
For complex or multi-step tasks, briefly reason through your approach before acting.
For simple questions, respond directly without extensive planning."""
    
    def _build_memory_section(self) -> str:
        """Memory recall instructions."""
        return """## Memory Recall
Before answering questions about past conversations, user preferences, or prior decisions:
1. Check your memory files using read_file on MEMORY.md
2. Search for relevant context before claiming you don't know something
3. If you save new information to memory, confirm what you saved

Memory locations:
- Long-term memory: ~/.koda/memory/MEMORY.md
- Daily notes: ~/.koda/memory/YYYY-MM-DD.md"""
    
    def _build_skills_section(self, skills_prompt: str) -> str:
        """Skills section with available skills."""
        return f"""## Skills (task-specific instructions)

Before responding, check if any skill applies to the user's request:
1. Scan the <available_skills> list below
2. If a skill matches, read its SKILL.md file first
3. Follow the skill's instructions exactly

{skills_prompt}

Rules:
- Read at most ONE skill per request (the most specific match)
- If no skill applies, proceed without reading any skill file
- Skills provide domain expertise and step-by-step procedures"""
    
    def _build_tools_section(self, tools: list[dict]) -> str:
        """Tools overview section."""
        tool_names = [t.get("name", t.get("function", {}).get("name", "?")) for t in tools]
        
        # Group tools by category
        categories = {
            "Files": ["read_file", "write_file", "edit_file", "list_dir"],
            "Shell": ["exec", "script"],
            "Web": ["web_search", "ddg_search", "web_fetch", "wikipedia", "browser"],
            "Calendar": ["calendar", "unified_calendar"],
            "Email": ["email", "unified_email"],
            "Messaging": ["message", "whatsapp", "telegram"],
            "Memory": ["memory", "memory_search"],
            "Smart Home": ["hue", "sonos"],
            "Other": [],
        }
        
        categorized = {cat: [] for cat in categories}
        for name in tool_names:
            found = False
            for cat, tools_in_cat in categories.items():
                if cat != "Other" and name in tools_in_cat:
                    categorized[cat].append(name)
                    found = True
                    break
            if not found:
                categorized["Other"].append(name)
        
        lines = ["## Available Tools"]
        for cat, names in categorized.items():
            if names:
                lines.append(f"- **{cat}**: {', '.join(names)}")
        
        lines.append("")
        lines.append("Use tools when needed. Explain what you're doing. Handle errors gracefully.")
        
        return "\n".join(lines)
    
    def _build_context_section(self, context_files: list[dict]) -> str:
        """Inject context files content."""
        if not context_files:
            return ""
        
        lines = ["## Context Files"]
        for cf in context_files:
            path = cf.get("path", "unknown")
            content = cf.get("content", "")
            if content:
                lines.append(f"\n### {path}\n```\n{content[:5000]}\n```")
        
        return "\n".join(lines)
    
    def _build_response_section(self, channel: str) -> str:
        """Response guidelines based on channel."""
        base = """## Response Guidelines
- Match the user's language (Dutch → Dutch, English → English)
- Be concise but complete
- Use markdown formatting when helpful
- For errors, explain what went wrong and suggest fixes"""
        
        if channel in ("whatsapp", "telegram", "signal"):
            base += """
- Keep responses brief for mobile chat
- Use emojis sparingly but appropriately
- Don't use complex markdown (no tables/code blocks if not supported)"""
        
        return base
    
    def _build_workspace_section(self) -> str:
        """Workspace info section."""
        return f"""## Workspace
Path: {self.workspace}
- Config: ~/.koda/config.json
- Memory: ~/.koda/memory/
- Skills: ~/.koda/skills/
- Plugins: ~/.koda/plugins/
- Screenshots: ~/.koda/screenshots/"""


def build_coding_agent_prompt(task: str, workspace: Path) -> str:
    """Build a specialized prompt for coding/software building tasks."""
    return f"""# Coding Agent

You are a specialized coding agent tasked with building software.

## Task
{task}

## Workspace
{workspace}

## Guidelines
1. **Plan First**: Before coding, outline your approach
2. **Incremental Development**: Build in small, testable steps
3. **Error Handling**: Add proper error handling and logging
4. **Testing**: Write tests or verify your code works
5. **Documentation**: Add comments for complex logic

## Code Style
- Follow language conventions (PEP 8 for Python, etc.)
- Use meaningful variable names
- Keep functions small and focused
- Handle edge cases

## Process
1. Read existing code to understand the codebase
2. Plan your changes
3. Implement incrementally
4. Test each change
5. Commit with clear messages

You have access to file tools (read, write, edit) and shell execution.
Build high-quality, working software."""
