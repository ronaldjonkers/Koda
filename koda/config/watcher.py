"""Config file watcher for automatic reload on changes."""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger


class ConfigWatcher:
    """
    Watch config file for changes and trigger reload callbacks.
    
    Uses file modification time polling (works everywhere, no dependencies).
    For production, could be extended to use watchdog or inotify.
    """
    
    def __init__(
        self,
        config_path: Optional[Path] = None,
        poll_interval: float = 2.0,  # Check every 2 seconds
    ):
        self.config_path = config_path or (Path.home() / ".koda" / "config.json")
        self.poll_interval = poll_interval
        self._callbacks: list[Callable[[], None]] = []
        self._async_callbacks: list[Callable[[], asyncio.coroutine]] = []
        self._last_mtime: float = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def on_change(self, callback: Callable[[], None]) -> None:
        """Register a sync callback to be called when config changes."""
        self._callbacks.append(callback)
    
    def on_change_async(self, callback: Callable[[], asyncio.coroutine]) -> None:
        """Register an async callback to be called when config changes."""
        self._async_callbacks.append(callback)
    
    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start watching for config changes."""
        if self._running:
            return
        
        self._loop = loop
        self._running = True
        
        # Get initial mtime
        if self.config_path.exists():
            self._last_mtime = self.config_path.stat().st_mtime
        
        # Start polling thread
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.debug(f"Config watcher started for {self.config_path}")
    
    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.debug("Config watcher stopped")
    
    def _poll_loop(self) -> None:
        """Polling loop that runs in a separate thread."""
        import time
        
        while self._running:
            try:
                if self.config_path.exists():
                    current_mtime = self.config_path.stat().st_mtime
                    
                    if current_mtime > self._last_mtime:
                        self._last_mtime = current_mtime
                        logger.info("Config file changed, triggering reload...")
                        self._trigger_callbacks()
            except Exception as e:
                logger.debug(f"Config watcher error: {e}")
            
            time.sleep(self.poll_interval)
    
    def _trigger_callbacks(self) -> None:
        """Trigger all registered callbacks."""
        # Sync callbacks
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Config reload callback error: {e}")
        
        # Async callbacks
        if self._async_callbacks and self._loop:
            for callback in self._async_callbacks:
                try:
                    asyncio.run_coroutine_threadsafe(callback(), self._loop)
                except Exception as e:
                    logger.error(f"Async config reload callback error: {e}")


# Global watcher instance
_watcher: Optional[ConfigWatcher] = None


def get_config_watcher() -> ConfigWatcher:
    """Get or create the global config watcher."""
    global _watcher
    if _watcher is None:
        _watcher = ConfigWatcher()
    return _watcher


def start_config_watcher(
    on_reload: Optional[Callable[[], None]] = None,
    on_reload_async: Optional[Callable[[], asyncio.coroutine]] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None
) -> ConfigWatcher:
    """
    Start the config file watcher.
    
    Args:
        on_reload: Sync callback when config changes
        on_reload_async: Async callback when config changes
        loop: Event loop for async callbacks
    
    Returns:
        The ConfigWatcher instance
    """
    watcher = get_config_watcher()
    
    if on_reload:
        watcher.on_change(on_reload)
    if on_reload_async:
        watcher.on_change_async(on_reload_async)
    
    watcher.start(loop)
    return watcher


def stop_config_watcher() -> None:
    """Stop the global config watcher."""
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None
