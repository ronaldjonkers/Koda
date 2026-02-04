"""Web tools: web_search, web_fetch, and free alternatives."""
from __future__ import annotations

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from koda.core.tools.base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""
    
    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
        # Log API key status for debugging
        from loguru import logger
        if self.api_key:
            logger.debug(f"WebSearchTool initialized with API key: {self.api_key[:10]}...")
        else:
            logger.warning("WebSearchTool: No Brave API key configured - web_search will not work")
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"🔍 web_search called with query: '{query}'")
        
        if not self.api_key:
            logger.error("web_search failed: BRAVE_API_KEY not configured")
            return "Error: BRAVE_API_KEY not configured. Use DuckDuckGo search (ddg_search) instead, or configure Brave API key in ~/.koda/config.json under tools.web.search.api_key"
        
        try:
            n = min(max(count or self.max_results, 1), 10)
            logger.debug(f"Calling Brave Search API for '{query}' (count={n})")
            
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                    timeout=10.0
                )
                
                logger.debug(f"Brave API response status: {r.status_code}")
                
                if r.status_code == 401:
                    logger.error("Brave API: Invalid API key (401 Unauthorized)")
                    return "Error: Invalid Brave API key. Check your API key in ~/.koda/config.json"
                elif r.status_code == 429:
                    logger.error("Brave API: Rate limit exceeded (429)")
                    return "Error: Brave API rate limit exceeded. Try again later or use ddg_search."
                
                r.raise_for_status()
            
            data = r.json()
            results = data.get("web", {}).get("results", [])
            
            if not results:
                logger.info(f"No results found for: {query}")
                return f"No results for: {query}"
            
            logger.info(f"Found {len(results)} results for: {query}")
            
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except httpx.TimeoutException:
            logger.error(f"web_search timeout for query: {query}")
            return "Error: Search request timed out. Try again or use ddg_search."
        except httpx.HTTPStatusError as e:
            logger.error(f"web_search HTTP error: {e.response.status_code} - {e}")
            return f"Error: HTTP {e.response.status_code} - {e}"
        except Exception as e:
            logger.error(f"web_search unexpected error: {type(e).__name__}: {e}")
            return f"Error: {type(e).__name__}: {e}"


class DuckDuckGoSearchTool(Tool):
    """Search the web using DuckDuckGo - completely free, no API key needed."""
    
    name = "ddg_search"
    description = "Search the web using DuckDuckGo (free, no API key). Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, max_results: int = 5):
        self.max_results = max_results
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        from loguru import logger
        
        logger.info(f"🦆 ddg_search called with query: '{query}'")
        
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error("ddg_search failed: duckduckgo-search not installed")
            return "Error: duckduckgo-search not installed. Run: pip install duckduckgo-search"
        
        try:
            n = min(max(count or self.max_results, 1), 10)
            
            # DuckDuckGo search is synchronous, run in executor
            import asyncio
            loop = asyncio.get_event_loop()
            
            def do_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=n))
            
            logger.debug(f"Calling DuckDuckGo for '{query}' (count={n})")
            results = await loop.run_in_executor(None, do_search)
            
            if not results:
                logger.info(f"No results found for: {query}")
                return f"No results for: {query}"
            
            logger.info(f"Found {len(results)} results for: {query}")
            
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}")
                lines.append(f"   {item.get('href', '')}")
                if body := item.get("body"):
                    lines.append(f"   {body}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"ddg_search error: {type(e).__name__}: {e}")
            return f"Error: {type(e).__name__}: {e}"


class WikipediaSearchTool(Tool):
    """Search and read Wikipedia articles - completely free."""
    
    name = "wikipedia"
    description = "Search Wikipedia and get article content. Free, no API key needed."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query or article title"},
            "lang": {"type": "string", "description": "Language code (en, nl, de, etc.)", "default": "en"},
            "sentences": {"type": "integer", "description": "Number of sentences to return (0 for full article)", "minimum": 0, "maximum": 50}
        },
        "required": ["query"]
    }
    
    async def execute(self, query: str, lang: str = "en", sentences: int = 10, **kwargs: Any) -> str:
        try:
            # Use Wikipedia API directly - no external library needed
            api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(api_url, headers={"User-Agent": USER_AGENT})
                
                # If not found, try search
                if r.status_code == 404:
                    search_url = f"https://{lang}.wikipedia.org/w/api.php"
                    params = {
                        "action": "opensearch",
                        "search": query,
                        "limit": 5,
                        "format": "json"
                    }
                    sr = await client.get(search_url, params=params)
                    sr.raise_for_status()
                    data = sr.json()
                    
                    if len(data) >= 2 and data[1]:
                        # Return search suggestions
                        suggestions = data[1][:5]
                        return f"Article '{query}' not found. Did you mean:\n" + "\n".join(f"- {s}" for s in suggestions)
                    return f"No Wikipedia article found for: {query}"
                
                r.raise_for_status()
                data = r.json()
            
            title = data.get("title", query)
            extract = data.get("extract", "")
            url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            
            # If user wants full article, fetch it
            if sentences == 0:
                html_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{query.replace(' ', '_')}"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    hr = await client.get(html_url, headers={"User-Agent": USER_AGENT})
                    if hr.status_code == 200:
                        extract = _normalize(_strip_tags(hr.text))[:20000]
            
            result = f"# {title}\n\n{extract}"
            if url:
                result += f"\n\nSource: {url}"
            return result
            
        except Exception as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using multiple extractors."""
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content. Uses trafilatura (best) or readability as fallback."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars
    
    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        max_chars = maxChars or self.max_chars

        # Validate URL before fetching
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url})

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            
            ctype = r.headers.get("content-type", "")
            
            # JSON
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2), "json"
            # HTML - try trafilatura first, then readability
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                text, extractor = self._extract_content(r.text, extractMode)
            else:
                text, extractor = r.text, "raw"
            
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            return json.dumps({"url": url, "finalUrl": str(r.url), "status": r.status_code,
                              "extractor": extractor, "truncated": truncated, "length": len(text), "text": text})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})
    
    def _extract_content(self, html_content: str, mode: str) -> tuple:
        """Extract content using trafilatura (preferred) or readability (fallback)."""
        # Try trafilatura first - generally better extraction
        try:
            import trafilatura
            if mode == "markdown":
                text = trafilatura.extract(html_content, include_links=True, include_formatting=True, output_format="markdown")
            else:
                text = trafilatura.extract(html_content, include_links=False)
            if text:
                return text, "trafilatura"
        except ImportError:
            pass
        except Exception:
            pass
        
        # Fallback to readability
        try:
            from readability import Document
            doc = Document(html_content)
            content = self._to_markdown(doc.summary()) if mode == "markdown" else _strip_tags(doc.summary())
            text = f"# {doc.title()}\n\n{content}" if doc.title() else content
            return text, "readability"
        except ImportError:
            pass
        except Exception:
            pass
        
        # Last resort: basic tag stripping
        return _normalize(_strip_tags(html_content)), "basic"
    
    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
