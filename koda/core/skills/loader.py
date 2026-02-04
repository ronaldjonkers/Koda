"""Skills loader - load SKILL.md instruction files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class Skill:
    """A loadable skill with instructions for a specific task."""
    name: str
    description: str
    location: Path
    content: str
    triggers: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    priority: int = 0
    
    def matches_query(self, query: str) -> bool:
        """Check if this skill matches a user query."""
        query_lower = query.lower()
        
        # Check triggers
        for trigger in self.triggers:
            if trigger.lower() in query_lower:
                return True
        
        # Check name/description
        if self.name.lower() in query_lower:
            return True
        
        for word in self.description.lower().split():
            if len(word) > 4 and word in query_lower:
                return True
        
        return False


class SkillsLoader:
    """Load skills from filesystem."""
    
    def __init__(self, skills_dirs: Optional[list[Path]] = None):
        self.skills_dirs = skills_dirs or [
            Path.home() / ".koda" / "skills",
            Path(__file__).parent.parent.parent.parent / "skills",  # Project skills dir
        ]
        self._skills: dict[str, Skill] = {}
        self._loaded = False
    
    def load_all(self) -> dict[str, Skill]:
        """Load all skills from configured directories."""
        if self._loaded:
            return self._skills
        
        for skills_dir in self.skills_dirs:
            if not skills_dir.exists():
                continue
            
            # Load skills from subdirectories
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        try:
                            skill = self._load_skill(skill_file)
                            if skill:
                                self._skills[skill.name] = skill
                                logger.debug(f"Loaded skill: {skill.name}")
                        except Exception as e:
                            logger.warning(f"Failed to load skill from {skill_file}: {e}")
            
            # Also load standalone .md files
            for md_file in skills_dir.glob("*.md"):
                if md_file.name != "README.md":
                    try:
                        skill = self._load_skill(md_file)
                        if skill:
                            self._skills[skill.name] = skill
                    except Exception as e:
                        logger.warning(f"Failed to load skill from {md_file}: {e}")
        
        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")
        return self._skills
    
    def _load_skill(self, path: Path) -> Optional[Skill]:
        """Load a single skill from a markdown file."""
        content = path.read_text(encoding="utf-8")
        
        # Parse frontmatter if present
        name = path.stem
        description = ""
        triggers: list[str] = []
        tools_required: list[str] = []
        priority = 0
        
        # Check for YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content = parts[2].strip()
                
                # Parse simple YAML
                for line in frontmatter.strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        
                        if key == "name":
                            name = value
                        elif key == "description":
                            description = value
                        elif key == "triggers":
                            triggers = [t.strip() for t in value.split(",")]
                        elif key == "tools":
                            tools_required = [t.strip() for t in value.split(",")]
                        elif key == "priority":
                            try:
                                priority = int(value)
                            except:
                                pass
        
        # Extract description from first paragraph if not in frontmatter
        if not description:
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line[:200]
                    break
        
        return Skill(
            name=name,
            description=description,
            location=path,
            content=content,
            triggers=triggers,
            tools_required=tools_required,
            priority=priority
        )
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)
    
    def find_matching_skills(self, query: str) -> list[Skill]:
        """Find skills that match a query."""
        if not self._loaded:
            self.load_all()
        
        matches = [s for s in self._skills.values() if s.matches_query(query)]
        return sorted(matches, key=lambda s: -s.priority)
    
    def get_skills_prompt(self) -> str:
        """Generate a prompt section listing available skills."""
        if not self._loaded:
            self.load_all()
        
        if not self._skills:
            return ""
        
        lines = ["<available_skills>"]
        for name, skill in sorted(self._skills.items()):
            lines.append(f"  <skill name=\"{name}\">")
            lines.append(f"    <description>{skill.description}</description>")
            lines.append(f"    <location>{skill.location}</location>")
            if skill.triggers:
                lines.append(f"    <triggers>{', '.join(skill.triggers)}</triggers>")
            lines.append(f"  </skill>")
        lines.append("</available_skills>")
        
        return "\n".join(lines)
