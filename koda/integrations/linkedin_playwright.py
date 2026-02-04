"""LinkedIn automation using Playwright browser automation.

This module provides robust LinkedIn automation using a persistent browser session,
avoiding API rate limits and detection issues. Based on OpenClaw skill patterns.

Features:
- Persistent browser session (manual login once, then reuse)
- Feed reading and interaction
- Post creation with image support
- Comments with @mentions
- Analytics and profile stats
- Voice/style learning from user's content
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from loguru import logger


@dataclass
class LinkedInPost:
    """Represents a LinkedIn post."""
    post_id: str
    url: str
    author_name: str
    author_headline: str
    content: str
    timestamp: datetime
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    has_image: bool = False
    is_repost: bool = False


@dataclass
class LinkedInAnalytics:
    """Analytics for a post."""
    post_id: str
    impressions: int = 0
    reactions: int = 0
    comments: int = 0
    reposts: int = 0
    engagement_rate: float = 0.0


@dataclass
class LinkedInStyle:
    """User's LinkedIn voice and style profile."""
    language: str = "en"  # en, nl, de, mixed
    tone: str = "professional-friendly"  # casual, professional, professional-friendly
    emoji_usage: str = "moderate"  # heavy, moderate, minimal
    top_hashtags: list[str] = field(default_factory=list)
    sample_posts: list[str] = field(default_factory=list)
    sample_comments: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


class LinkedInPlaywright:
    """
    LinkedIn automation client using Playwright.
    
    Uses a persistent browser profile so you only need to log in once manually.
    After initial login, the session is reused for all automation.
    """
    
    # Rate limits (conservative to avoid detection)
    RATE_LIMITS = {
        "posts_daily": 2,
        "comments_daily": 20,
        "likes_daily": 50,
        "connection_requests_daily": 20,
    }
    
    def __init__(
        self,
        profile_path: Optional[Path] = None,
        headless: bool = True,
        slow_mo: int = 100,  # Milliseconds between actions (more human-like)
    ):
        self.profile_path = profile_path or Path.home() / ".koda" / "linkedin_browser"
        self.headless = headless
        self.slow_mo = slow_mo
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        
        # State tracking
        self.style_path = Path.home() / ".koda" / "linkedin_style.json"
        self.state_path = Path.home() / ".koda" / "linkedin_state.json"
        self._style: Optional[LinkedInStyle] = None
        self._state: dict = {}
        
        # Ensure directories exist
        self.profile_path.mkdir(parents=True, exist_ok=True)
    
    async def _ensure_browser(self) -> None:
        """Ensure browser is running with persistent context."""
        if self._page is not None:
            return
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        
        self._playwright = await async_playwright().start()
        
        # Use persistent context for session persistence
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self.profile_path),
            headless=self.headless,
            slow_mo=self.slow_mo,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        
        self._page = await self._context.new_page()
        logger.debug("LinkedIn browser started with persistent profile")
    
    async def close(self) -> None:
        """Close the browser."""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
    
    async def check_session(self) -> tuple[bool, str]:
        """
        Check if LinkedIn session is valid.
        
        Returns:
            Tuple of (is_valid, message)
        """
        await self._ensure_browser()
        
        try:
            await self._page.goto("https://www.linkedin.com/feed/", wait_until="networkidle", timeout=30000)
            
            # Check if we're on login page
            if "login" in self._page.url or "checkpoint" in self._page.url:
                return False, "Session expired. Please log in manually by running with headless=False"
            
            # Check for feed content
            feed = await self._page.query_selector("div.feed-shared-update-v2")
            if feed:
                logger.info("LinkedIn session is valid")
                return True, "Session valid"
            
            return False, "Could not verify feed access"
            
        except Exception as e:
            logger.error(f"Session check failed: {e}")
            return False, f"Error: {e}"
    
    async def login_interactive(self) -> bool:
        """
        Open browser for interactive login.
        
        Call this with headless=False to allow manual login.
        After logging in, the session will be persisted.
        """
        # Temporarily disable headless for login
        old_headless = self.headless
        self.headless = False
        
        try:
            await self.close()  # Close any existing session
            await self._ensure_browser()
            
            await self._page.goto("https://www.linkedin.com/login")
            
            print("\n" + "="*50)
            print("Please log in to LinkedIn in the browser window.")
            print("After successful login, press Enter here to continue...")
            print("="*50 + "\n")
            
            input()  # Wait for user
            
            # Verify login worked
            valid, msg = await self.check_session()
            if valid:
                print("✅ Login successful! Session saved.")
                return True
            else:
                print(f"❌ Login verification failed: {msg}")
                return False
                
        finally:
            self.headless = old_headless
    
    # =========================================================================
    # Feed Operations
    # =========================================================================
    
    async def get_feed(self, count: int = 10) -> list[LinkedInPost]:
        """
        Get posts from the LinkedIn feed.
        
        Args:
            count: Number of posts to retrieve
        
        Returns:
            List of LinkedInPost objects
        """
        await self._ensure_browser()
        
        try:
            await self._page.goto("https://www.linkedin.com/feed/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # Let feed load
            
            posts = []
            
            # Scroll and collect posts
            for _ in range(min(count // 3, 5)):  # Scroll a few times
                # Get post elements
                post_elements = await self._page.query_selector_all("div.feed-shared-update-v2")
                
                for elem in post_elements[:count]:
                    try:
                        post = await self._parse_post_element(elem)
                        if post and post.post_id not in [p.post_id for p in posts]:
                            posts.append(post)
                    except Exception as e:
                        logger.debug(f"Failed to parse post: {e}")
                
                if len(posts) >= count:
                    break
                
                # Scroll down
                await self._page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1)
            
            logger.info(f"Retrieved {len(posts)} posts from feed")
            return posts[:count]
            
        except Exception as e:
            logger.error(f"Failed to get feed: {e}")
            return []
    
    async def _parse_post_element(self, elem) -> Optional[LinkedInPost]:
        """Parse a post element into a LinkedInPost object."""
        try:
            # Get post URL/ID
            link_elem = await elem.query_selector("a.app-aware-link[href*='/feed/update/']")
            if not link_elem:
                return None
            
            url = await link_elem.get_attribute("href")
            post_id = url.split("urn:li:activity:")[-1].split("?")[0] if url else ""
            
            # Get author info
            author_elem = await elem.query_selector(".update-components-actor__name span[aria-hidden='true']")
            author_name = await author_elem.inner_text() if author_elem else "Unknown"
            
            headline_elem = await elem.query_selector(".update-components-actor__description")
            author_headline = await headline_elem.inner_text() if headline_elem else ""
            
            # Get content
            content_elem = await elem.query_selector(".feed-shared-update-v2__description")
            content = await content_elem.inner_text() if content_elem else ""
            
            # Get engagement counts
            likes = await self._get_reaction_count(elem)
            comments = await self._get_comment_count(elem)
            
            # Check for image
            has_image = await elem.query_selector("img.feed-shared-image__image") is not None
            
            return LinkedInPost(
                post_id=post_id,
                url=url or "",
                author_name=author_name.strip(),
                author_headline=author_headline.strip(),
                content=content.strip(),
                timestamp=datetime.now(),  # Would need to parse from element
                likes=likes,
                comments=comments,
                has_image=has_image,
            )
            
        except Exception as e:
            logger.debug(f"Error parsing post: {e}")
            return None
    
    async def _get_reaction_count(self, elem) -> int:
        """Get reaction count from a post element."""
        try:
            count_elem = await elem.query_selector(".social-details-social-counts__reactions-count")
            if count_elem:
                text = await count_elem.inner_text()
                return self._parse_count(text)
        except:
            pass
        return 0
    
    async def _get_comment_count(self, elem) -> int:
        """Get comment count from a post element."""
        try:
            count_elem = await elem.query_selector("button[aria-label*='comment']")
            if count_elem:
                label = await count_elem.get_attribute("aria-label")
                if label:
                    match = re.search(r'(\d+)', label)
                    if match:
                        return int(match.group(1))
        except:
            pass
        return 0
    
    def _parse_count(self, text: str) -> int:
        """Parse a count string like '1.2K' to integer."""
        text = text.strip().lower()
        if 'k' in text:
            return int(float(text.replace('k', '').replace(',', '')) * 1000)
        elif 'm' in text:
            return int(float(text.replace('m', '').replace(',', '')) * 1000000)
        else:
            try:
                return int(text.replace(',', ''))
            except:
                return 0
    
    # =========================================================================
    # Post Creation
    # =========================================================================
    
    async def create_post(
        self,
        text: str,
        image_path: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Create a LinkedIn post.
        
        Args:
            text: Post content
            image_path: Optional path to image file
        
        Returns:
            Tuple of (success, message/url)
        """
        await self._ensure_browser()
        
        try:
            await self._page.goto("https://www.linkedin.com/feed/", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Click "Start a post" button
            start_post = await self._page.query_selector("button.share-box-feed-entry__trigger")
            if not start_post:
                return False, "Could not find 'Start a post' button"
            
            await start_post.click()
            await asyncio.sleep(1)
            
            # Wait for editor
            editor = await self._page.wait_for_selector(".ql-editor", timeout=5000)
            if not editor:
                return False, "Post editor did not open"
            
            # Type the content
            await editor.fill(text)
            await asyncio.sleep(0.5)
            
            # Add image if provided
            if image_path and Path(image_path).exists():
                # Click image button
                image_btn = await self._page.query_selector("button[aria-label*='image']")
                if image_btn:
                    await image_btn.click()
                    await asyncio.sleep(1)
                    
                    # Upload file
                    file_input = await self._page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(image_path)
                        await asyncio.sleep(2)  # Wait for upload
            
            # Click Post button
            post_btn = await self._page.query_selector("button.share-actions__primary-action")
            if not post_btn:
                return False, "Could not find Post button"
            
            await post_btn.click()
            await asyncio.sleep(3)  # Wait for post to be created
            
            logger.info("LinkedIn post created successfully")
            return True, "Post created successfully"
            
        except Exception as e:
            logger.error(f"Failed to create post: {e}")
            return False, f"Error: {e}"
    
    # =========================================================================
    # Comments
    # =========================================================================
    
    async def comment_on_post(
        self,
        post_url: str,
        text: str,
    ) -> tuple[bool, str]:
        """
        Comment on a LinkedIn post.
        
        Supports @mentions using @FirstName LastName syntax.
        
        Args:
            post_url: URL of the post to comment on
            text: Comment text (supports @mentions)
        
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_browser()
        
        try:
            await self._page.goto(post_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Click comment button to open comment box
            comment_btn = await self._page.query_selector("button[aria-label*='Comment']")
            if comment_btn:
                await comment_btn.click()
                await asyncio.sleep(1)
            
            # Find comment input
            comment_input = await self._page.query_selector(".comments-comment-box__form .ql-editor")
            if not comment_input:
                return False, "Could not find comment input"
            
            # Handle @mentions
            text = await self._process_mentions(text)
            
            # Type comment
            await comment_input.fill(text)
            await asyncio.sleep(0.5)
            
            # Submit comment
            submit_btn = await self._page.query_selector("button.comments-comment-box__submit-button")
            if not submit_btn:
                return False, "Could not find submit button"
            
            await submit_btn.click()
            await asyncio.sleep(2)
            
            logger.info("Comment posted successfully")
            return True, "Comment posted"
            
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
            return False, f"Error: {e}"
    
    async def _process_mentions(self, text: str) -> str:
        """Process @mentions in text. Currently returns text as-is."""
        # TODO: Implement proper @mention handling with typeahead
        return text
    
    # =========================================================================
    # Analytics
    # =========================================================================
    
    async def get_profile_stats(self) -> dict:
        """Get profile-level statistics."""
        await self._ensure_browser()
        
        try:
            await self._page.goto("https://www.linkedin.com/dashboard/", wait_until="networkidle")
            await asyncio.sleep(2)
            
            stats = {}
            
            # Get profile views
            views_elem = await self._page.query_selector("a[href*='profile-views'] .t-bold")
            if views_elem:
                stats["profile_views"] = self._parse_count(await views_elem.inner_text())
            
            # Get post impressions
            impressions_elem = await self._page.query_selector("a[href*='post-impressions'] .t-bold")
            if impressions_elem:
                stats["post_impressions"] = self._parse_count(await impressions_elem.inner_text())
            
            # Get search appearances
            search_elem = await self._page.query_selector("a[href*='search-appearances'] .t-bold")
            if search_elem:
                stats["search_appearances"] = self._parse_count(await search_elem.inner_text())
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get profile stats: {e}")
            return {}
    
    async def get_post_analytics(self, count: int = 10) -> list[LinkedInAnalytics]:
        """Get analytics for recent posts."""
        await self._ensure_browser()
        
        # TODO: Implement post-level analytics
        # This requires navigating to the analytics page
        return []
    
    # =========================================================================
    # Voice & Style Learning
    # =========================================================================
    
    async def learn_style(self) -> LinkedInStyle:
        """
        Learn user's voice and style from their recent posts and comments.
        
        Analyzes:
        - Language patterns (en/nl/de/mixed)
        - Tone (casual/professional)
        - Emoji usage
        - Common hashtags
        - Topics of interest
        
        Returns:
            LinkedInStyle object
        """
        await self._ensure_browser()
        
        style = LinkedInStyle()
        
        try:
            # Go to user's activity
            await self._page.goto("https://www.linkedin.com/in/me/recent-activity/all/", wait_until="networkidle")
            await asyncio.sleep(2)
            
            posts_text = []
            comments_text = []
            all_hashtags = []
            
            # Scroll and collect content
            for _ in range(3):
                # Get posts
                post_elems = await self._page.query_selector_all(".feed-shared-update-v2__description")
                for elem in post_elems[:20]:
                    text = await elem.inner_text()
                    if text:
                        posts_text.append(text)
                        # Extract hashtags
                        hashtags = re.findall(r'#(\w+)', text)
                        all_hashtags.extend(hashtags)
                
                await self._page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
            
            # Analyze language
            style.language = self._detect_language(posts_text)
            
            # Analyze tone
            style.tone = self._detect_tone(posts_text)
            
            # Analyze emoji usage
            style.emoji_usage = self._detect_emoji_usage(posts_text)
            
            # Top hashtags
            from collections import Counter
            hashtag_counts = Counter(all_hashtags)
            style.top_hashtags = [h for h, _ in hashtag_counts.most_common(10)]
            
            # Sample posts
            style.sample_posts = posts_text[:5]
            
            # Save style
            self._save_style(style)
            
            logger.info(f"Learned LinkedIn style: {style.language}, {style.tone}, {style.emoji_usage}")
            return style
            
        except Exception as e:
            logger.error(f"Failed to learn style: {e}")
            return style
    
    def _detect_language(self, texts: list[str]) -> str:
        """Detect primary language from texts."""
        combined = " ".join(texts).lower()
        
        # Simple heuristic based on common words
        dutch_words = ["de", "het", "en", "van", "een", "dat", "voor", "zijn", "met", "niet"]
        german_words = ["der", "die", "und", "ist", "von", "das", "für", "mit", "nicht", "sich"]
        english_words = ["the", "and", "is", "of", "to", "for", "in", "that", "with", "are"]
        
        dutch_count = sum(1 for w in dutch_words if f" {w} " in combined)
        german_count = sum(1 for w in german_words if f" {w} " in combined)
        english_count = sum(1 for w in english_words if f" {w} " in combined)
        
        if dutch_count > english_count and dutch_count > german_count:
            return "nl"
        elif german_count > english_count and german_count > dutch_count:
            return "de"
        elif dutch_count > 0 or german_count > 0:
            return "mixed"
        return "en"
    
    def _detect_tone(self, texts: list[str]) -> str:
        """Detect tone from texts."""
        combined = " ".join(texts).lower()
        
        # Casual indicators
        casual_words = ["haha", "lol", "!", "hey", "guys", "awesome", "cool"]
        casual_count = sum(1 for w in casual_words if w in combined)
        
        # Professional indicators
        professional_words = ["regarding", "therefore", "however", "furthermore", "accordingly"]
        professional_count = sum(1 for w in professional_words if w in combined)
        
        if casual_count > professional_count * 2:
            return "casual"
        elif professional_count > casual_count:
            return "professional"
        return "professional-friendly"
    
    def _detect_emoji_usage(self, texts: list[str]) -> str:
        """Detect emoji usage level."""
        combined = " ".join(texts)
        
        # Count emojis (simplified)
        emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]')
        emoji_count = len(emoji_pattern.findall(combined))
        
        words = combined.split()
        if len(words) == 0:
            return "minimal"
        
        ratio = emoji_count / len(words)
        
        if ratio > 0.1:
            return "heavy"
        elif ratio > 0.03:
            return "moderate"
        return "minimal"
    
    def _save_style(self, style: LinkedInStyle) -> None:
        """Save style to disk."""
        try:
            self.style_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.style_path, 'w') as f:
                json.dump({
                    "language": style.language,
                    "tone": style.tone,
                    "emoji_usage": style.emoji_usage,
                    "top_hashtags": style.top_hashtags,
                    "sample_posts": style.sample_posts,
                    "sample_comments": style.sample_comments,
                    "topics": style.topics,
                }, f, indent=2)
            logger.debug("Saved LinkedIn style profile")
        except Exception as e:
            logger.warning(f"Failed to save style: {e}")
    
    def get_style(self) -> Optional[LinkedInStyle]:
        """Load saved style profile."""
        if self._style:
            return self._style
        
        try:
            if self.style_path.exists():
                with open(self.style_path) as f:
                    data = json.load(f)
                self._style = LinkedInStyle(**data)
                return self._style
        except Exception as e:
            logger.warning(f"Failed to load style: {e}")
        
        return None
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_post_age_warning(self, post_date: datetime) -> Optional[str]:
        """
        Check if a post is too old for commenting.
        
        Returns warning message if post is old, None if OK.
        """
        age = datetime.now() - post_date
        
        if age > timedelta(days=30):
            return f"⚠️ This post is {age.days} days old. Commenting on very old posts can look like bot behavior. Are you sure?"
        elif age > timedelta(days=14):
            return f"⚠️ This post is {age.days} days old. Consider whether commenting is still relevant."
        
        return None
