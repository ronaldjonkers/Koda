"""Memory tool for vector-based memory operations."""

from typing import Any

from loguru import logger

from koda.core.tools.base import BaseTool
from koda.core.vector_memory import VectorMemoryStore


class MemoryTool(BaseTool):
    """
    Tool for managing Koda's vector-based memory system.
    
    Allows the agent to:
    - Store important facts, preferences, and context
    - Search memories semantically
    - Update or delete memories
    - Retrieve relevant context for queries
    """
    
    name = "memory"
    description = """Manage persistent vector-based memory. Use this to:
- Remember important facts about the user
- Store learned preferences and patterns
- Save context for future conversations
- Search for relevant past information

Actions:
- add: Store a new memory
- search: Find memories by semantic similarity
- list: List memories by category
- delete: Remove a memory
- update: Modify an existing memory"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "search", "list", "delete", "update"],
                "description": "The memory operation to perform"
            },
            "content": {
                "type": "string",
                "description": "For 'add': the memory content. For 'search': the query. For 'update': new content."
            },
            "category": {
                "type": "string",
                "enum": ["facts", "preferences", "context", "tasks", "general"],
                "description": "Memory category (default: general)"
            },
            "memory_id": {
                "type": "string",
                "description": "For 'delete' or 'update': the memory ID"
            },
            "source": {
                "type": "string",
                "description": "For 'add': source of the memory (user, agent, system)"
            },
            "limit": {
                "type": "integer",
                "description": "For 'search' or 'list': max results (default: 5)"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, memory_store: VectorMemoryStore):
        self.memory_store = memory_store
    
    async def execute(self, **kwargs) -> str:
        """Execute a memory operation."""
        action = kwargs.get("action")
        content = kwargs.get("content", "")
        category = kwargs.get("category", "general")
        memory_id = kwargs.get("memory_id", "")
        source = kwargs.get("source", "agent")
        limit = kwargs.get("limit", 5)
        
        try:
            if action == "add":
                if not content:
                    return "Error: 'content' is required for adding memories"
                
                mem_id = self.memory_store.add(
                    content=content,
                    category=category,
                    source=source
                )
                return f"Memory stored successfully (ID: {mem_id}, category: {category})"
            
            elif action == "search":
                if not content:
                    return "Error: 'content' (query) is required for searching"
                
                results = self.memory_store.search(
                    query=content,
                    n_results=limit,
                    category=category if category != "general" else None
                )
                
                if not results:
                    return "No relevant memories found."
                
                output = [f"Found {len(results)} relevant memories:\n"]
                for mem in results:
                    cat = mem["metadata"].get("category", "general")
                    score = mem["score"]
                    output.append(f"- [{cat}] (score: {score:.2f}) {mem['content']}")
                    output.append(f"  ID: {mem['id']}")
                
                return "\n".join(output)
            
            elif action == "list":
                results = self.memory_store.list_by_category(category, limit=limit)
                
                if not results:
                    return f"No memories in category '{category}'."
                
                output = [f"Memories in '{category}' ({len(results)}):\n"]
                for mem in results:
                    output.append(f"- {mem['content'][:100]}...")
                    output.append(f"  ID: {mem['id']}")
                
                return "\n".join(output)
            
            elif action == "delete":
                if not memory_id:
                    return "Error: 'memory_id' is required for deletion"
                
                if self.memory_store.delete(memory_id):
                    return f"Memory {memory_id} deleted successfully."
                return f"Memory {memory_id} not found."
            
            elif action == "update":
                if not memory_id:
                    return "Error: 'memory_id' is required for update"
                if not content:
                    return "Error: 'content' is required for update"
                
                if self.memory_store.update(memory_id, content=content):
                    return f"Memory {memory_id} updated successfully."
                return f"Memory {memory_id} not found."
            
            else:
                return f"Unknown action: {action}"
        
        except ImportError as e:
            return f"Vector memory not available: {e}. Install chromadb and sentence-transformers."
        except Exception as e:
            logger.error(f"Memory operation failed: {e}")
            return f"Error: {str(e)}"
