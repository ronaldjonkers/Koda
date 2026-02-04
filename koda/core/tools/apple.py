"""Apple integrations: Notes and Reminders via AppleScript (macOS only)."""
from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

from koda.core.tools.base import Tool


def run_applescript(script: str) -> str:
    """Run AppleScript and return output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


class AppleNotesTool(Tool):
    """Manage Apple Notes on macOS."""
    
    name = "apple_notes"
    description = """Create, read, and search Apple Notes (macOS only).

Actions:
- list: List recent notes
- search: Search notes by text
- read: Read a specific note
- create: Create a new note
- append: Append text to existing note

Examples:
- List notes: {"action": "list", "limit": 10}
- Search: {"action": "search", "query": "meeting"}
- Create: {"action": "create", "title": "Shopping List", "body": "- Milk\\n- Bread"}
- Read: {"action": "read", "title": "Shopping List"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "read", "create", "append"],
                "description": "Action to perform"
            },
            "title": {
                "type": "string",
                "description": "Note title (for create/read/append)"
            },
            "body": {
                "type": "string",
                "description": "Note content (for create/append)"
            },
            "query": {
                "type": "string",
                "description": "Search query (for search)"
            },
            "folder": {
                "type": "string",
                "description": "Folder name (default: Notes)"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum notes to return",
                "default": 20
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        import platform
        
        if platform.system() != "Darwin":
            return json.dumps({"error": "Apple Notes only available on macOS"})
        
        logger.info(f"📝 apple_notes: {action}")
        
        try:
            if action == "list":
                return self._list_notes(kwargs.get("limit", 20), kwargs.get("folder"))
            elif action == "search":
                return self._search_notes(kwargs.get("query", ""), kwargs.get("limit", 20))
            elif action == "read":
                return self._read_note(kwargs.get("title", ""))
            elif action == "create":
                return self._create_note(kwargs.get("title", ""), kwargs.get("body", ""), kwargs.get("folder"))
            elif action == "append":
                return self._append_note(kwargs.get("title", ""), kwargs.get("body", ""))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"Apple Notes error: {e}")
            return json.dumps({"error": str(e)})
    
    def _list_notes(self, limit: int, folder: Optional[str] = None) -> str:
        """List recent notes."""
        folder_filter = f'of folder "{folder}"' if folder else ""
        script = f'''
        tell application "Notes"
            set noteList to {{}}
            repeat with n in (notes {folder_filter})
                if (count of noteList) ≥ {limit} then exit repeat
                set end of noteList to {{name of n, id of n, modification date of n as string}}
            end repeat
            return noteList
        end tell
        '''
        result = run_applescript(script)
        
        notes = []
        if result:
            # Parse AppleScript list output
            items = result.split(", ")
            for i in range(0, len(items), 3):
                if i + 2 < len(items):
                    notes.append({
                        "title": items[i].strip(),
                        "id": items[i+1].strip(),
                        "modified": items[i+2].strip()
                    })
        
        return json.dumps({"notes": notes, "count": len(notes)})
    
    def _search_notes(self, query: str, limit: int) -> str:
        """Search notes by content."""
        script = f'''
        tell application "Notes"
            set foundNotes to {{}}
            repeat with n in notes
                if (name of n contains "{query}") or (body of n as string contains "{query}") then
                    set end of foundNotes to name of n
                    if (count of foundNotes) ≥ {limit} then exit repeat
                end if
            end repeat
            return foundNotes
        end tell
        '''
        result = run_applescript(script)
        notes = [n.strip() for n in result.split(", ")] if result else []
        return json.dumps({"query": query, "results": notes, "count": len(notes)})
    
    def _read_note(self, title: str) -> str:
        """Read a note by title."""
        if not title:
            return json.dumps({"error": "Title required"})
        
        script = f'''
        tell application "Notes"
            set n to first note whose name is "{title}"
            return body of n as string
        end tell
        '''
        content = run_applescript(script)
        return json.dumps({"title": title, "content": content})
    
    def _create_note(self, title: str, body: str, folder: Optional[str] = None) -> str:
        """Create a new note."""
        if not title:
            return json.dumps({"error": "Title required"})
        
        # Escape quotes in body
        body_escaped = body.replace('"', '\\"').replace('\n', '\\n')
        
        if folder:
            script = f'''
            tell application "Notes"
                tell folder "{folder}"
                    make new note with properties {{name:"{title}", body:"{body_escaped}"}}
                end tell
            end tell
            '''
        else:
            script = f'''
            tell application "Notes"
                make new note with properties {{name:"{title}", body:"{body_escaped}"}}
            end tell
            '''
        
        run_applescript(script)
        return json.dumps({"status": "created", "title": title})
    
    def _append_note(self, title: str, body: str) -> str:
        """Append text to existing note."""
        if not title or not body:
            return json.dumps({"error": "Title and body required"})
        
        body_escaped = body.replace('"', '\\"').replace('\n', '\\n')
        script = f'''
        tell application "Notes"
            set n to first note whose name is "{title}"
            set body of n to (body of n as string) & "\\n" & "{body_escaped}"
        end tell
        '''
        run_applescript(script)
        return json.dumps({"status": "appended", "title": title})


class AppleRemindersTool(Tool):
    """Manage Apple Reminders on macOS."""
    
    name = "apple_reminders"
    description = """Create and manage Apple Reminders (macOS only).

Actions:
- list: List reminders from a list
- lists: Show all reminder lists
- create: Create a new reminder
- complete: Mark reminder as complete
- delete: Delete a reminder

Examples:
- Show lists: {"action": "lists"}
- List reminders: {"action": "list", "list_name": "Shopping"}
- Create: {"action": "create", "title": "Buy milk", "list_name": "Shopping", "due_date": "2024-01-15"}
- Complete: {"action": "complete", "title": "Buy milk", "list_name": "Shopping"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "lists", "create", "complete", "delete"],
                "description": "Action to perform"
            },
            "list_name": {
                "type": "string",
                "description": "Reminder list name"
            },
            "title": {
                "type": "string",
                "description": "Reminder title"
            },
            "notes": {
                "type": "string",
                "description": "Reminder notes/body"
            },
            "due_date": {
                "type": "string",
                "description": "Due date (YYYY-MM-DD format)"
            },
            "priority": {
                "type": "integer",
                "description": "Priority (0=none, 1=high, 5=medium, 9=low)",
                "minimum": 0,
                "maximum": 9
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        import platform
        
        if platform.system() != "Darwin":
            return json.dumps({"error": "Apple Reminders only available on macOS"})
        
        logger.info(f"✅ apple_reminders: {action}")
        
        try:
            if action == "lists":
                return self._get_lists()
            elif action == "list":
                return self._list_reminders(kwargs.get("list_name", "Reminders"))
            elif action == "create":
                return self._create_reminder(
                    kwargs.get("title", ""),
                    kwargs.get("list_name", "Reminders"),
                    kwargs.get("notes"),
                    kwargs.get("due_date"),
                    kwargs.get("priority", 0)
                )
            elif action == "complete":
                return self._complete_reminder(kwargs.get("title", ""), kwargs.get("list_name", "Reminders"))
            elif action == "delete":
                return self._delete_reminder(kwargs.get("title", ""), kwargs.get("list_name", "Reminders"))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"Apple Reminders error: {e}")
            return json.dumps({"error": str(e)})
    
    def _get_lists(self) -> str:
        """Get all reminder lists."""
        script = '''
        tell application "Reminders"
            return name of every list
        end tell
        '''
        result = run_applescript(script)
        lists = [l.strip() for l in result.split(", ")] if result else []
        return json.dumps({"lists": lists})
    
    def _list_reminders(self, list_name: str) -> str:
        """List reminders in a list."""
        script = f'''
        tell application "Reminders"
            set reminderList to {{}}
            repeat with r in (reminders of list "{list_name}" whose completed is false)
                set end of reminderList to name of r
            end repeat
            return reminderList
        end tell
        '''
        result = run_applescript(script)
        reminders = [r.strip() for r in result.split(", ")] if result else []
        return json.dumps({"list": list_name, "reminders": reminders, "count": len(reminders)})
    
    def _create_reminder(self, title: str, list_name: str, notes: Optional[str], due_date: Optional[str], priority: int) -> str:
        """Create a new reminder."""
        if not title:
            return json.dumps({"error": "Title required"})
        
        props = [f'name:"{title}"']
        if notes:
            props.append(f'body:"{notes}"')
        if priority:
            props.append(f'priority:{priority}')
        
        props_str = ", ".join(props)
        
        script = f'''
        tell application "Reminders"
            tell list "{list_name}"
                make new reminder with properties {{{props_str}}}
            end tell
        end tell
        '''
        
        run_applescript(script)
        
        # Set due date separately if provided (AppleScript date handling is tricky)
        if due_date:
            try:
                script = f'''
                tell application "Reminders"
                    set r to first reminder of list "{list_name}" whose name is "{title}"
                    set due date of r to date "{due_date}"
                end tell
                '''
                run_applescript(script)
            except:
                pass  # Due date setting may fail, that's okay
        
        return json.dumps({"status": "created", "title": title, "list": list_name})
    
    def _complete_reminder(self, title: str, list_name: str) -> str:
        """Mark reminder as complete."""
        if not title:
            return json.dumps({"error": "Title required"})
        
        script = f'''
        tell application "Reminders"
            set r to first reminder of list "{list_name}" whose name is "{title}"
            set completed of r to true
        end tell
        '''
        run_applescript(script)
        return json.dumps({"status": "completed", "title": title})
    
    def _delete_reminder(self, title: str, list_name: str) -> str:
        """Delete a reminder."""
        if not title:
            return json.dumps({"error": "Title required"})
        
        script = f'''
        tell application "Reminders"
            delete (first reminder of list "{list_name}" whose name is "{title}")
        end tell
        '''
        run_applescript(script)
        return json.dumps({"status": "deleted", "title": title})
