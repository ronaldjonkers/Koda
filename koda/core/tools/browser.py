"""Browser automation tool using Playwright for web interactions."""
from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Any, Optional

from koda.core.tools.base import Tool


class BrowserTool(Tool):
    """Control a web browser for automation, form filling, and purchases."""
    
    name = "browser"
    description = """Automate web browser for interactions, form filling, purchases, and screenshots.

Actions:
- open: Open a URL in browser
- screenshot: Take screenshot of current page
- click: Click an element by selector or text
- type: Type text into an input field
- fill_form: Fill a form with multiple fields
- get_text: Get text content from page or element
- get_links: Get all links from page
- scroll: Scroll page up/down
- wait: Wait for element or timeout
- close: Close browser

Selectors can be:
- CSS: "#id", ".class", "button"
- Text: "text=Submit", "text=Add to cart"
- Placeholder: "placeholder=Email"
- Label: "label=Password"

Examples:
- Open page: {"action": "open", "url": "https://example.com"}
- Click button: {"action": "click", "selector": "text=Submit"}
- Fill form: {"action": "fill_form", "fields": {"#email": "user@example.com", "#password": "secret"}}
- Screenshot: {"action": "screenshot", "full_page": true}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "screenshot", "click", "type", "fill_form", "get_text", "get_links", "scroll", "wait", "close"],
                "description": "Browser action to perform"
            },
            "url": {
                "type": "string",
                "description": "URL to open (for 'open' action)"
            },
            "selector": {
                "type": "string",
                "description": "Element selector (CSS, text=, placeholder=, label=)"
            },
            "text": {
                "type": "string",
                "description": "Text to type (for 'type' action)"
            },
            "fields": {
                "type": "object",
                "description": "Form fields as {selector: value} (for 'fill_form')"
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page screenshot",
                "default": False
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "Scroll direction"
            },
            "timeout": {
                "type": "integer",
                "description": "Wait timeout in milliseconds",
                "default": 5000
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, headless: bool = True, screenshots_dir: Optional[Path] = None):
        self.headless = headless
        self.screenshots_dir = screenshots_dir or Path.home() / ".koda" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._browser = None
        self._context = None
        self._page = None
    
    async def _ensure_browser(self):
        """Ensure browser is running."""
        if self._page is not None:
            return
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("playwright not installed. Run: pip install playwright && playwright install chromium")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()
    
    async def _close_browser(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._context = None
        self._page = None
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"🌐 browser: {action}")
        
        try:
            if action == "close":
                await self._close_browser()
                return json.dumps({"status": "closed"})
            
            await self._ensure_browser()
            
            if action == "open":
                return await self._open(kwargs.get("url", ""))
            elif action == "screenshot":
                return await self._screenshot(kwargs.get("full_page", False))
            elif action == "click":
                return await self._click(kwargs.get("selector", ""))
            elif action == "type":
                return await self._type(kwargs.get("selector", ""), kwargs.get("text", ""))
            elif action == "fill_form":
                return await self._fill_form(kwargs.get("fields", {}))
            elif action == "get_text":
                return await self._get_text(kwargs.get("selector"))
            elif action == "get_links":
                return await self._get_links()
            elif action == "scroll":
                return await self._scroll(kwargs.get("direction", "down"))
            elif action == "wait":
                return await self._wait(kwargs.get("selector"), kwargs.get("timeout", 5000))
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
                
        except Exception as e:
            logger.error(f"Browser error: {e}")
            return json.dumps({"error": str(e), "action": action})
    
    async def _open(self, url: str) -> str:
        """Open a URL."""
        if not url:
            return json.dumps({"error": "URL required"})
        
        await self._page.goto(url, wait_until="domcontentloaded")
        return json.dumps({
            "status": "opened",
            "url": self._page.url,
            "title": await self._page.title()
        })
    
    async def _screenshot(self, full_page: bool = False) -> str:
        """Take screenshot and return path."""
        from datetime import datetime
        
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = self.screenshots_dir / filename
        
        await self._page.screenshot(path=str(path), full_page=full_page)
        
        return json.dumps({
            "status": "captured",
            "path": str(path),
            "url": self._page.url
        })
    
    async def _click(self, selector: str) -> str:
        """Click an element."""
        if not selector:
            return json.dumps({"error": "Selector required"})
        
        await self._page.click(selector)
        return json.dumps({"status": "clicked", "selector": selector})
    
    async def _type(self, selector: str, text: str) -> str:
        """Type text into an element."""
        if not selector or not text:
            return json.dumps({"error": "Selector and text required"})
        
        await self._page.fill(selector, text)
        return json.dumps({"status": "typed", "selector": selector})
    
    async def _fill_form(self, fields: dict) -> str:
        """Fill multiple form fields."""
        if not fields:
            return json.dumps({"error": "Fields required"})
        
        filled = []
        for selector, value in fields.items():
            await self._page.fill(selector, str(value))
            filled.append(selector)
        
        return json.dumps({"status": "filled", "fields": filled})
    
    async def _get_text(self, selector: Optional[str] = None) -> str:
        """Get text content from page or element."""
        if selector:
            element = await self._page.query_selector(selector)
            if element:
                text = await element.text_content()
            else:
                text = ""
        else:
            text = await self._page.text_content("body")
        
        # Truncate if too long
        if text and len(text) > 10000:
            text = text[:10000] + "... [truncated]"
        
        return json.dumps({
            "text": text,
            "url": self._page.url
        })
    
    async def _get_links(self) -> str:
        """Get all links from page."""
        links = await self._page.eval_on_selector_all(
            "a[href]",
            "elements => elements.map(e => ({text: e.textContent?.trim(), href: e.href})).filter(l => l.href)"
        )
        
        # Limit to 50 links
        return json.dumps({
            "links": links[:50],
            "total": len(links),
            "url": self._page.url
        })
    
    async def _scroll(self, direction: str) -> str:
        """Scroll page."""
        if direction == "up":
            await self._page.evaluate("window.scrollBy(0, -500)")
        else:
            await self._page.evaluate("window.scrollBy(0, 500)")
        
        return json.dumps({"status": "scrolled", "direction": direction})
    
    async def _wait(self, selector: Optional[str], timeout: int) -> str:
        """Wait for element or timeout."""
        if selector:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return json.dumps({"status": "found", "selector": selector})
        else:
            import asyncio
            await asyncio.sleep(timeout / 1000)
            return json.dumps({"status": "waited", "ms": timeout})
