"""Skills manager - orchestrate skill loading and execution."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from koda.core.skills.loader import SkillsLoader, Skill


class SkillsManager:
    """Manage skills and provide context for agent runs."""
    
    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = workspace or Path.cwd()
        self.loader = SkillsLoader([
            Path.home() / ".koda" / "skills",
            self.workspace / "skills",
            self.workspace / ".koda" / "skills",
        ])
        self._active_skill: Optional[Skill] = None
    
    def get_skills_section(self) -> str:
        """Get the skills section for system prompt."""
        skills = self.loader.load_all()
        if not skills:
            return ""
        
        return f"""## Skills (task-specific instructions)

Before responding, scan the available skills below. If a skill clearly applies to the user's request:
1. Read the skill's SKILL.md file using the read_file tool
2. Follow the instructions in that skill exactly

{self.loader.get_skills_prompt()}

Guidelines:
- Only read ONE skill per request (the most specific match)
- If no skill applies, proceed without reading any skill file
- Skills provide domain-specific knowledge and procedures
"""
    
    def find_skill_for_query(self, query: str) -> Optional[Skill]:
        """Find the best matching skill for a query."""
        matches = self.loader.find_matching_skills(query)
        if matches:
            skill = matches[0]
            logger.debug(f"Found matching skill: {skill.name} for query: {query[:50]}...")
            return skill
        return None
    
    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """Get the content of a skill by name."""
        skill = self.loader.get_skill(skill_name)
        if skill:
            return skill.content
        return None
    
    def create_skill(self, name: str, description: str, content: str, triggers: Optional[list[str]] = None) -> Path:
        """Create a new skill file."""
        skills_dir = Path.home() / ".koda" / "skills" / name
        skills_dir.mkdir(parents=True, exist_ok=True)
        
        skill_file = skills_dir / "SKILL.md"
        
        # Build frontmatter
        frontmatter = [
            "---",
            f"name: {name}",
            f"description: {description}",
        ]
        if triggers:
            frontmatter.append(f"triggers: {', '.join(triggers)}")
        frontmatter.append("---")
        frontmatter.append("")
        
        full_content = "\n".join(frontmatter) + content
        skill_file.write_text(full_content, encoding="utf-8")
        
        # Reload skills
        self.loader._loaded = False
        self.loader.load_all()
        
        logger.info(f"Created skill: {name} at {skill_file}")
        return skill_file
