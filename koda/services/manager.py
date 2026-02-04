"""Channel manager for coordinating chat channels."""

import asyncio
from typing import Any

from loguru import logger

from koda.messaging.events import OutboundMessage
from koda.messaging.queue import MessageBus
from koda.services.base import BaseChannel
from koda.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.
    
    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """
    
    def __init__(self, config: Config, bus: MessageBus):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None
        
        self._init_channels()
    
    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        
        # Telegram channel
        if self.config.channels.telegram.enabled:
            try:
                from koda.services.telegram import TelegramChannel
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self.bus,
                    groq_api_key=self.config.providers.groq.api_key,
                )
                logger.info("Telegram channel enabled")
            except ImportError as e:
                logger.warning(f"Telegram channel not available: {e}")
        
        # WhatsApp channel
        if self.config.channels.whatsapp.enabled:
            try:
                from koda.services.whatsapp import WhatsAppChannel
                
                # Get assistant name for WhatsApp greetings
                assistant_name = self.config.assistant.name
                
                # Create WhatsApp channel with full configuration
                wa_config = self.config.channels.whatsapp
                self.channels["whatsapp"] = WhatsAppChannel(
                    config=wa_config,
                    bus=self.bus,
                    assistant_name=assistant_name,
                )
                
                # Log WhatsApp mode
                if wa_config.bot_mode:
                    logger.info(f"WhatsApp channel enabled (Bot Mode: respond to everyone)")
                    if wa_config.owner_phone:
                        logger.info(f"  Escalations will be sent to: {wa_config.owner_phone}")
                    if wa_config.contact_rules:
                        logger.info(f"  Custom rules for {len(wa_config.contact_rules)} contacts")
                else:
                    logger.info("WhatsApp channel enabled (Restricted Mode)")
            except ImportError as e:
                logger.warning(f"WhatsApp channel not available: {e}")
    
    async def start_all(self) -> None:
        """Start WhatsApp channel and the outbound dispatcher."""
        if not self.channels:
            logger.warning("No channels enabled")
            return
        
        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        
        # Start WhatsApp channel
        tasks = []
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            tasks.append(asyncio.create_task(channel.start()))
        
        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")
        
        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
    
    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")
        
        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )
                
                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error(f"Error sending to {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
    
    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)
    
    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }
    
    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
    
    def reload_config(self, new_config: Config) -> None:
        """
        Reload configuration without restarting channels.
        
        Updates config for running channels so they pick up changes
        like allow_from, bot_mode, contact_rules, etc.
        """
        self.config = new_config
        
        # Update each channel's config
        for name, channel in self.channels.items():
            try:
                if name == "whatsapp" and hasattr(channel, 'reload_config'):
                    channel.reload_config(new_config.channels.whatsapp)
                    logger.info(f"Reloaded config for {name} channel")
                elif name == "telegram" and hasattr(channel, 'reload_config'):
                    channel.reload_config(new_config.channels.telegram)
                    logger.info(f"Reloaded config for {name} channel")
            except Exception as e:
                logger.error(f"Error reloading config for {name}: {e}")
