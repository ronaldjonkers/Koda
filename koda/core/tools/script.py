"""Script generation and execution tool for autonomous task automation."""

import asyncio
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool


class ScriptTool(BaseTool):
    """
    Tool for generating and executing scripts in Python, Bash, or Node.js.
    
    Enables the agent to:
    - Generate scripts to automate complex tasks
    - Execute scripts in a sandboxed environment
    - Save scripts for reuse
    - Chain multiple script operations
    """
    
    name = "script"
    description = """Generate and execute scripts for task automation. Use this to:
- Create Python, Bash, or Node.js scripts for complex operations
- Execute data processing, API calls, file manipulation
- Automate repetitive tasks
- Run system commands with scripted logic

Actions:
- generate: Create a script file without executing
- execute: Run a script (inline code or from file)
- save: Save a script to the workspace for reuse
- list: List saved scripts"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "execute", "save", "list"],
                "description": "The script operation to perform"
            },
            "language": {
                "type": "string",
                "enum": ["python", "bash", "nodejs"],
                "description": "Script language (default: python)"
            },
            "code": {
                "type": "string",
                "description": "For 'generate' or 'execute': the script code"
            },
            "name": {
                "type": "string",
                "description": "For 'save': script name (without extension)"
            },
            "script_path": {
                "type": "string",
                "description": "For 'execute': path to existing script file"
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For 'execute': command line arguments"
            },
            "timeout": {
                "type": "integer",
                "description": "For 'execute': timeout in seconds (default: 60)"
            },
            "working_dir": {
                "type": "string",
                "description": "For 'execute': working directory"
            }
        },
        "required": ["action"]
    }
    
    LANGUAGE_CONFIG = {
        "python": {
            "extension": ".py",
            "interpreter": ["python3"],
            "shebang": "#!/usr/bin/env python3"
        },
        "bash": {
            "extension": ".sh",
            "interpreter": ["bash"],
            "shebang": "#!/bin/bash"
        },
        "nodejs": {
            "extension": ".js",
            "interpreter": ["node"],
            "shebang": "#!/usr/bin/env node"
        }
    }
    
    def __init__(self, workspace: Path, scripts_dir: str = "scripts"):
        self.workspace = workspace
        self.scripts_dir = workspace / scripts_dir
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_interpreter(self, language: str) -> list[str]:
        """Get the interpreter command for a language."""
        config = self.LANGUAGE_CONFIG.get(language, self.LANGUAGE_CONFIG["python"])
        return config["interpreter"]
    
    def _get_extension(self, language: str) -> str:
        """Get file extension for a language."""
        config = self.LANGUAGE_CONFIG.get(language, self.LANGUAGE_CONFIG["python"])
        return config["extension"]
    
    def _get_shebang(self, language: str) -> str:
        """Get shebang line for a language."""
        config = self.LANGUAGE_CONFIG.get(language, self.LANGUAGE_CONFIG["python"])
        return config["shebang"]
    
    async def execute(self, **kwargs) -> str:
        """Execute a script operation."""
        action = kwargs.get("action")
        language = kwargs.get("language", "python")
        code = kwargs.get("code", "")
        name = kwargs.get("name", "")
        script_path = kwargs.get("script_path", "")
        args = kwargs.get("args", [])
        timeout = kwargs.get("timeout", 60)
        working_dir = kwargs.get("working_dir", str(self.workspace))
        
        try:
            if action == "generate":
                return await self._generate(language, code, name)
            
            elif action == "execute":
                return await self._execute(
                    language=language,
                    code=code,
                    script_path=script_path,
                    args=args,
                    timeout=timeout,
                    working_dir=working_dir
                )
            
            elif action == "save":
                return await self._save(language, code, name)
            
            elif action == "list":
                return await self._list_scripts()
            
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            logger.error(f"Script operation failed: {e}")
            return f"Error: {str(e)}"
    
    async def _generate(self, language: str, code: str, name: str = "") -> str:
        """Generate a script file without executing."""
        if not code:
            return "Error: 'code' is required for generating scripts"
        
        # Add shebang if not present
        shebang = self._get_shebang(language)
        if not code.startswith("#!"):
            code = f"{shebang}\n\n{code}"
        
        # Generate filename
        ext = self._get_extension(language)
        if name:
            filename = f"{name}{ext}"
        else:
            filename = f"script_{uuid.uuid4().hex[:8]}{ext}"
        
        script_path = self.scripts_dir / filename
        script_path.write_text(code)
        script_path.chmod(0o755)
        
        return f"Script generated:\n- Path: {script_path}\n- Language: {language}\n- Lines: {len(code.splitlines())}"
    
    async def _execute(
        self,
        language: str,
        code: str = "",
        script_path: str = "",
        args: list[str] = None,
        timeout: int = 60,
        working_dir: str = ""
    ) -> str:
        """Execute a script and return output."""
        args = args or []
        
        # Determine what to execute
        if script_path:
            # Execute existing file
            path = Path(script_path)
            if not path.is_absolute():
                path = self.workspace / script_path
            
            if not path.exists():
                return f"Error: Script not found: {path}"
            
            # Detect language from extension if not specified
            if not language or language == "python":
                ext = path.suffix.lower()
                for lang, config in self.LANGUAGE_CONFIG.items():
                    if config["extension"] == ext:
                        language = lang
                        break
            
            temp_file = None
            exec_path = str(path)
        
        elif code:
            # Write to temp file
            ext = self._get_extension(language)
            temp_file = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=ext,
                delete=False
            )
            
            # Add shebang if needed
            if not code.startswith("#!"):
                code = f"{self._get_shebang(language)}\n\n{code}"
            
            temp_file.write(code)
            temp_file.close()
            os.chmod(temp_file.name, 0o755)
            exec_path = temp_file.name
        
        else:
            return "Error: Either 'code' or 'script_path' is required"
        
        try:
            # Build command
            interpreter = self._get_interpreter(language)
            cmd = interpreter + [exec_path] + args
            
            # Execute
            logger.debug(f"Executing: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir or str(self.workspace)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return f"Error: Script timed out after {timeout} seconds"
            
            # Format output
            output_parts = []
            
            if process.returncode == 0:
                output_parts.append("✓ Script executed successfully")
            else:
                output_parts.append(f"✗ Script failed with exit code {process.returncode}")
            
            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace").strip()
                if len(stdout_text) > 5000:
                    stdout_text = stdout_text[:5000] + "\n... (output truncated)"
                output_parts.append(f"\n**Output:**\n```\n{stdout_text}\n```")
            
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                if len(stderr_text) > 2000:
                    stderr_text = stderr_text[:2000] + "\n... (stderr truncated)"
                output_parts.append(f"\n**Errors:**\n```\n{stderr_text}\n```")
            
            return "\n".join(output_parts)
        
        finally:
            # Cleanup temp file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
    
    async def _save(self, language: str, code: str, name: str) -> str:
        """Save a script to the workspace for reuse."""
        if not code:
            return "Error: 'code' is required"
        if not name:
            return "Error: 'name' is required for saving scripts"
        
        # Sanitize name
        safe_name = "".join(c for c in name if c.isalnum() or c in "_-")
        if not safe_name:
            return "Error: Invalid script name"
        
        ext = self._get_extension(language)
        filename = f"{safe_name}{ext}"
        
        # Add shebang if needed
        if not code.startswith("#!"):
            code = f"{self._get_shebang(language)}\n\n{code}"
        
        script_path = self.scripts_dir / filename
        script_path.write_text(code)
        script_path.chmod(0o755)
        
        return f"Script saved:\n- Path: {script_path}\n- Name: {safe_name}\n- Language: {language}"
    
    async def _list_scripts(self) -> str:
        """List saved scripts."""
        if not self.scripts_dir.exists():
            return "No scripts directory found."
        
        scripts = []
        for ext_info in self.LANGUAGE_CONFIG.values():
            ext = ext_info["extension"]
            scripts.extend(self.scripts_dir.glob(f"*{ext}"))
        
        if not scripts:
            return "No saved scripts found."
        
        output = [f"Saved scripts ({len(scripts)}):\n"]
        for script in sorted(scripts):
            size = script.stat().st_size
            lang = "unknown"
            for l, config in self.LANGUAGE_CONFIG.items():
                if script.suffix == config["extension"]:
                    lang = l
                    break
            output.append(f"- {script.name} ({lang}, {size} bytes)")
        
        return "\n".join(output)
