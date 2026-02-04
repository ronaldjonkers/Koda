"""Agent loop: the core processing engine."""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from koda.messaging.events import InboundMessage, OutboundMessage
from koda.messaging.queue import MessageBus
from koda.providers.base import LLMProvider
from koda.core.context import ContextBuilder
from koda.core.tools.registry import ToolRegistry
from koda.core.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from koda.core.tools.shell import ExecTool
from koda.core.tools.web import WebSearchTool, WebFetchTool, DuckDuckGoSearchTool, WikipediaSearchTool
from koda.core.tools.message import MessageTool
from koda.core.tools.spawn import SpawnTool
from koda.core.tools.unified_calendar import UnifiedCalendarTool
from koda.core.tools.unified_email import UnifiedEmailTool
from koda.core.tools.accounts import AccountsTool
from koda.core.tools.contacts import ContactsTool
from koda.core.tools.memory import MemoryTool
from koda.core.tools.script import ScriptTool
from koda.core.tools.schedule import ScheduleTool
from koda.core.tools.plugin import PluginTool, PluginWrapperTool
from koda.core.tools.linkedin import LinkedInTool
from koda.plugins.loader import PluginLoader
from koda.core.subagent import SubagentManager
from koda.core.vector_memory import VectorMemoryStore
from koda.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        calendar_config: dict | None = None,
        reminder_service: Any = None,
        cron_service: Any = None
    ):
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.calendar_config = calendar_config or {}
        self.reminder_service = reminder_service
        self.cron_service = cron_service
        self.assistant_config = calendar_config.get("assistant_config", {}) if calendar_config else {}
        
        # Build context with assistant personalization
        self.context = ContextBuilder(
            workspace=workspace,
            assistant_name=self.assistant_config.get("name", "Koda"),
            user_name=self.assistant_config.get("user_name", ""),
            default_language=self.assistant_config.get("language", "en")
        )
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()
        self.vector_memory = VectorMemoryStore(workspace / "vector_db")
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
        )
        
        self._running = False
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools
        self.tools.register(ReadFileTool())
        self.tools.register(WriteFileTool())
        self.tools.register(EditFileTool())
        self.tools.register(ListDirTool())
        
        # Shell tool
        self.tools.register(ExecTool(working_dir=str(self.workspace)))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))  # Brave (paid)
        self.tools.register(DuckDuckGoSearchTool())  # Free alternative
        self.tools.register(WikipediaSearchTool())   # Free Wikipedia access
        self.tools.register(WebFetchTool())          # URL fetching with trafilatura
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Get full config object for account-based tools
        full_config = self.calendar_config.get('config') if self.calendar_config else None
        cal_cfg = self.calendar_config
        
        # Accounts tool - lets LLM discover available accounts
        self.tools.register(AccountsTool(config=full_config))
        
        # Build calendar accounts list from config
        calendar_accounts = []
        if full_config and hasattr(full_config, 'integrations'):
            # First, get from unified accounts list (filter by calendar capability)
            unified_accounts = getattr(full_config.integrations, 'accounts', []) or []
            for acc in unified_accounts:
                # Get capabilities
                if isinstance(acc, dict):
                    caps = acc.get('capabilities', [])
                    acc_type = acc.get('type', '')
                else:
                    caps = getattr(acc, 'capabilities', [])
                    acc_type = getattr(acc, 'type', '')
                
                # Include if has calendar capability or is calendar-compatible type
                if 'calendar' in caps or acc_type in ('exchange', 'google', 'caldav'):
                    calendar_accounts.append(self._account_to_dict(acc))
            
            # Also include legacy calendar_accounts for backward compatibility
            raw_accounts = getattr(full_config.integrations, 'calendar_accounts', []) or []
            for acc in raw_accounts:
                calendar_accounts.append(self._account_to_dict(acc))
        
        # Unified calendar tool (supports multiple named accounts)
        self.tools.register(UnifiedCalendarTool(
            calendar_accounts=calendar_accounts,
            # Legacy parameters for backward compatibility
            google_enabled=cal_cfg.get("google_enabled", False),
            google_credentials_file=cal_cfg.get("google_credentials_file", ""),
            google_token_file=cal_cfg.get("google_token_file", ""),
            exchange_enabled=cal_cfg.get("exchange_enabled", False),
            exchange_email=cal_cfg.get("exchange_email", ""),
            exchange_password=cal_cfg.get("exchange_password", ""),
            exchange_server=cal_cfg.get("exchange_server", ""),
            caldav_enabled=cal_cfg.get("caldav_enabled", False),
            caldav_url=cal_cfg.get("caldav_url", ""),
            caldav_username=cal_cfg.get("caldav_username", ""),
            caldav_password=cal_cfg.get("caldav_password", ""),
            reminder_service=self.reminder_service,
            default_reminder_phone=cal_cfg.get("default_reminder_phone", "")
        ))
        
        # Legacy individual calendar/email tools are NOT registered
        # The unified calendar and email tools handle all account types
        
        # Unified email tool for email_accounts configuration
        self.tools.register(UnifiedEmailTool(config=full_config))
        
        # Contacts tool
        self.tools.register(ContactsTool())
        
        # Memory tool (vector-based)
        self.tools.register(MemoryTool(memory_store=self.vector_memory))
        
        # Script tool (Python, Bash, Node.js)
        self.tools.register(ScriptTool(workspace=self.workspace))
        
        # Schedule tool (cron jobs for recurring tasks)
        if self.cron_service:
            self.tools.register(ScheduleTool(cron_service=self.cron_service))
        
        # Plugin tool (create/manage plugins)
        self.tools.register(PluginTool())
        
        # Load user plugins from ~/.koda/plugins/
        self.plugin_loader = PluginLoader()
        self._load_plugins()
        
        # LinkedIn tool - always register, it loads config dynamically
        linkedin_cfg = self.calendar_config.get("linkedin", {})
        self.tools.register(LinkedInTool(
            email=linkedin_cfg.get("email", ""),
            password=linkedin_cfg.get("password", ""),
            enabled=linkedin_cfg.get("enabled", False)
        ))
    
    def _load_plugins(self) -> None:
        """Load plugins from the plugins directory and register their tools."""
        try:
            plugins = self.plugin_loader.load_all()
            for name, plugin in plugins.items():
                # Create a wrapper tool for each plugin
                wrapper = PluginWrapperTool(plugin, self.plugin_loader)
                self.tools.register(wrapper)
                logger.info(f"Registered plugin: {name}")
        except Exception as e:
            logger.warning(f"Error loading plugins: {e}")
    
    def _account_to_dict(self, acc) -> dict:
        """Convert account (dict or Pydantic model) to dict with snake_case keys."""
        if isinstance(acc, dict):
            # Handle camelCase to snake_case conversion
            return {
                "name": acc.get('name', ''),
                "type": acc.get('type', ''),
                "enabled": acc.get('enabled', True),
                "email": acc.get('email', ''),
                "username": acc.get('username', ''),
                "password": acc.get('password', ''),
                "server": acc.get('server', ''),
                "use_autodiscover": acc.get('use_autodiscover', acc.get('useAutodiscover', False)),
                "credentials_file": acc.get('credentials_file', acc.get('credentialsFile', '')),
                "token_file": acc.get('token_file', acc.get('tokenFile', '')),
                "url": acc.get('url', ''),
                "calendar_path": acc.get('calendar_path', acc.get('calendarPath', '')),
                "capabilities": acc.get('capabilities', []),
            }
        else:
            # Convert Pydantic model to dict
            return {
                "name": getattr(acc, 'name', ''),
                "type": getattr(acc, 'type', ''),
                "enabled": getattr(acc, 'enabled', True),
                "email": getattr(acc, 'email', ''),
                "username": getattr(acc, 'username', ''),
                "password": getattr(acc, 'password', ''),
                "server": getattr(acc, 'server', ''),
                "use_autodiscover": getattr(acc, 'use_autodiscover', False),
                "credentials_file": getattr(acc, 'credentials_file', ''),
                "token_file": getattr(acc, 'token_file', ''),
                "url": getattr(acc, 'url', ''),
                "calendar_path": getattr(acc, 'calendar_path', ''),
                "capabilities": getattr(acc, 'capabilities', []),
            }
    
    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        logger.info(f"🤖 Processing message from {msg.channel}:{msg.sender_id}: {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}")
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
        )
        
        # Agent loop
        iteration = 0
        final_content = None
        
        logger.info(f"🧠 Calling LLM ({self.model})...")
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Call LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            # Handle tool calls
            if response.has_tool_calls:
                logger.info(f"🔧 LLM requested {len(response.tool_calls)} tool(s): {', '.join(tc.name for tc in response.tool_calls)}")
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts
                )
                
                # Execute tools
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments)
                    logger.debug(f"Executing tool: {tool_call.name} with arguments: {args_str}")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # No tool calls, we're done
                final_content = response.content
                logger.info(f"💬 LLM response ready ({len(final_content)} chars)")
                break
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        logger.info(f"📤 Sending response to {msg.channel}:{msg.chat_id[:20]}...")
        
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments)
                    logger.debug(f"Executing tool: {tool_call.name} with arguments: {args_str}")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(self, content: str, session_key: str = "cli:direct") -> str:
        """
        Process a message directly (for CLI usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="direct",
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
