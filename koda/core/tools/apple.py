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


class AppleMessagesTool(Tool):
    """Send and read iMessages/SMS on macOS."""
    
    name = "apple_messages"
    description = """Send and read iMessages/SMS via Messages.app (macOS only).

Actions:
- send: Send a message to a phone number or email
- recent: Get recent messages from a contact
- chats: List recent chat conversations

Examples:
- Send: {"action": "send", "to": "+31612345678", "message": "Hello!"}
- Recent: {"action": "recent", "contact": "+31612345678", "limit": 10}
- Chats: {"action": "chats", "limit": 20}

Note: Sending messages requires Messages.app to be set up with iMessage/SMS.
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "recent", "chats"],
                "description": "Action to perform"
            },
            "to": {
                "type": "string",
                "description": "Phone number or email to send to"
            },
            "message": {
                "type": "string",
                "description": "Message text to send"
            },
            "contact": {
                "type": "string",
                "description": "Phone/email to get messages from"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum messages/chats to return",
                "default": 20
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        import platform
        
        if platform.system() != "Darwin":
            return json.dumps({"error": "Apple Messages only available on macOS"})
        
        logger.info(f"💬 apple_messages: {action}")
        
        try:
            if action == "send":
                return self._send_message(kwargs.get("to", ""), kwargs.get("message", ""))
            elif action == "recent":
                return self._get_recent(kwargs.get("contact", ""), kwargs.get("limit", 20))
            elif action == "chats":
                return self._get_chats(kwargs.get("limit", 20))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"Apple Messages error: {e}")
            return json.dumps({"error": str(e)})
    
    def _send_message(self, to: str, message: str) -> str:
        """Send an iMessage/SMS."""
        if not to or not message:
            return json.dumps({"error": "Both 'to' and 'message' are required"})
        
        # Escape special characters
        message_escaped = message.replace('"', '\\"').replace('\n', '\\n')
        
        script = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{to}" of targetService
            send "{message_escaped}" to targetBuddy
        end tell
        '''
        
        try:
            run_applescript(script)
            return json.dumps({"status": "sent", "to": to})
        except RuntimeError as e:
            # Fallback for SMS
            if "iMessage" in str(e):
                script_sms = f'''
                tell application "Messages"
                    set targetService to 1st account whose service type = SMS
                    set targetBuddy to participant "{to}" of targetService
                    send "{message_escaped}" to targetBuddy
                end tell
                '''
                try:
                    run_applescript(script_sms)
                    return json.dumps({"status": "sent_sms", "to": to})
                except:
                    pass
            raise
    
    def _get_recent(self, contact: str, limit: int) -> str:
        """Get recent messages from a contact using Messages database."""
        if not contact:
            return json.dumps({"error": "Contact phone/email required"})
        
        import sqlite3
        from pathlib import Path
        
        db_path = Path.home() / "Library/Messages/chat.db"
        if not db_path.exists():
            return json.dumps({"error": "Messages database not found"})
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Find chat ID for contact
            cursor.execute("""
                SELECT chat.ROWID, chat.chat_identifier
                FROM chat
                WHERE chat.chat_identifier LIKE ?
                LIMIT 1
            """, (f"%{contact}%",))
            
            chat_row = cursor.fetchone()
            if not chat_row:
                return json.dumps({"error": f"No chat found for {contact}", "messages": []})
            
            chat_id = chat_row[0]
            
            # Get messages
            cursor.execute("""
                SELECT 
                    message.text,
                    message.is_from_me,
                    datetime(message.date/1000000000 + 978307200, 'unixepoch', 'localtime') as timestamp
                FROM message
                JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
                WHERE chat_message_join.chat_id = ?
                AND message.text IS NOT NULL
                ORDER BY message.date DESC
                LIMIT ?
            """, (chat_id, limit))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "text": row[0],
                    "from_me": bool(row[1]),
                    "timestamp": row[2]
                })
            
            conn.close()
            
            return json.dumps({
                "contact": contact,
                "messages": messages[::-1],  # Chronological order
                "count": len(messages)
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": f"Database error: {e}"})
    
    def _get_chats(self, limit: int) -> str:
        """Get list of recent chat conversations."""
        import sqlite3
        from pathlib import Path
        
        db_path = Path.home() / "Library/Messages/chat.db"
        if not db_path.exists():
            return json.dumps({"error": "Messages database not found"})
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT
                    chat.chat_identifier,
                    chat.display_name,
                    (SELECT message.text FROM message 
                     JOIN chat_message_join ON message.ROWID = chat_message_join.message_id 
                     WHERE chat_message_join.chat_id = chat.ROWID 
                     ORDER BY message.date DESC LIMIT 1) as last_message
                FROM chat
                ORDER BY chat.ROWID DESC
                LIMIT ?
            """, (limit,))
            
            chats = []
            for row in cursor.fetchall():
                chats.append({
                    "identifier": row[0],
                    "display_name": row[1] or row[0],
                    "last_message": (row[2] or "")[:100]
                })
            
            conn.close()
            
            return json.dumps({
                "chats": chats,
                "count": len(chats)
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": f"Database error: {e}"})
