"""LinkedIn automation service for monitoring and engagement."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from dataclasses import dataclass, field, asdict

from loguru import logger

from koda.integrations.linkedin_client import (
    LinkedInClient, 
    LinkedInMessage, 
    LinkedInConnection, 
    LinkedInPost,
    LinkedInProfile
)


@dataclass
class LinkedInConfig:
    """LinkedIn integration configuration."""
    enabled: bool = False
    email: str = ""
    password: str = ""
    
    # User profile for context
    user_role: str = ""  # What does the user do?
    user_goals: str = ""  # What are they looking for on LinkedIn?
    user_interests: list[str] = field(default_factory=list)  # Topics of interest
    
    # Automation settings
    auto_accept_connections: bool = True
    auto_reply_messages: bool = False  # Start conservative
    auto_post: bool = False  # Only when user trusts the bot
    auto_react: bool = False  # Only when user trusts the bot
    
    # Digest settings
    daily_digest_enabled: bool = True
    daily_digest_time: str = "09:00"  # When to send digest
    daily_digest_channel: str = "whatsapp"  # whatsapp or telegram
    daily_digest_recipient: str = ""  # Phone number or chat ID
    
    # Filtering
    connection_keywords: list[str] = field(default_factory=list)  # Keywords to auto-accept
    ignore_keywords: list[str] = field(default_factory=list)  # Keywords to ignore
    
    # Trust level (0-5): Higher = more automation allowed
    trust_level: int = 0


@dataclass
class PendingAction:
    """An action waiting for user approval."""
    action_type: str  # 'reply', 'post', 'comment', 'accept'
    target_id: str
    target_name: str
    context: str
    suggested_content: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class LinkedInDigest:
    """Daily LinkedIn digest for user review."""
    date: datetime
    new_messages: list[dict] = field(default_factory=list)
    pending_connections: list[dict] = field(default_factory=list)
    interesting_posts: list[dict] = field(default_factory=list)
    suggested_actions: list[dict] = field(default_factory=list)
    auto_accepted: list[str] = field(default_factory=list)
    auto_replied: list[str] = field(default_factory=list)


class LinkedInService:
    """
    LinkedIn automation service.
    
    Features:
    - Monitor incoming messages and identify interesting ones
    - Auto-accept connection requests based on criteria
    - Collect interesting posts for daily digest
    - Generate suggested replies and reactions
    - Send daily summary via WhatsApp/Telegram
    """
    
    def __init__(
        self,
        config: LinkedInConfig,
        llm_callback: Optional[Callable] = None,
        message_callback: Optional[Callable] = None,
        data_dir: Optional[Path] = None
    ):
        self.config = config
        self.llm_callback = llm_callback  # For AI-generated responses
        self.message_callback = message_callback  # For sending digest
        self.data_dir = data_dir or Path.home() / ".koda" / "linkedin"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._client: Optional[LinkedInClient] = None
        self._running = False
        self._last_check = datetime.now() - timedelta(hours=24)
        self._pending_actions: list[PendingAction] = []
        self._today_digest: Optional[LinkedInDigest] = None
    
    def _get_client(self) -> LinkedInClient:
        """Get or create LinkedIn client."""
        if self._client is None:
            self._client = LinkedInClient(
                email=self.config.email,
                password=self.config.password,
                cookies_path=self.data_dir / "cookies.json"
            )
        return self._client
    
    # ==================== MESSAGE HANDLING ====================
    
    async def check_messages(self) -> list[LinkedInMessage]:
        """Check for new unread messages."""
        try:
            client = self._get_client()
            messages = await asyncio.to_thread(client.get_unread_messages)
            
            interesting = []
            for msg in messages:
                # Analyze if message is interesting
                is_interesting = await self._is_message_interesting(msg)
                if is_interesting:
                    interesting.append(msg)
                    
                    # Auto-reply if enabled and trust level allows
                    if self.config.auto_reply_messages and self.config.trust_level >= 3:
                        await self._auto_reply_message(msg)
                    else:
                        # Queue for digest
                        suggested = await self._generate_reply_suggestion(msg)
                        self._pending_actions.append(PendingAction(
                            action_type='reply',
                            target_id=msg.conversation_id,
                            target_name=msg.sender_name,
                            context=msg.content[:200],
                            suggested_content=suggested
                        ))
            
            return interesting
        except Exception as e:
            logger.error(f"Failed to check messages: {e}")
            return []
    
    async def _is_message_interesting(self, msg: LinkedInMessage) -> bool:
        """Determine if a message is interesting based on user goals."""
        if not self.llm_callback:
            return True  # Without LLM, mark all as interesting
        
        prompt = f"""Analyze this LinkedIn message and determine if it's interesting for the user.

User's role: {self.config.user_role}
User's goals: {self.config.user_goals}
User's interests: {', '.join(self.config.user_interests)}

Message from: {msg.sender_name}
Content: {msg.content}

Is this message interesting or relevant? Consider:
- Is it a potential business opportunity?
- Is it relevant to the user's work or interests?
- Is it a meaningful connection request?
- Is it spam or generic recruitment?

Reply with just 'YES' or 'NO' followed by a brief reason."""

        try:
            response = await self.llm_callback(prompt)
            return response.strip().upper().startswith('YES')
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return True
    
    async def _generate_reply_suggestion(self, msg: LinkedInMessage) -> str:
        """Generate a suggested reply to a message."""
        if not self.llm_callback:
            return "Thank you for reaching out. Could you tell me more about what you're looking for?"
        
        prompt = f"""Generate a professional LinkedIn reply to this message.

User's role: {self.config.user_role}
User's goals: {self.config.user_goals}

Message from: {msg.sender_name}
Content: {msg.content}

Write a friendly, professional reply that:
1. Acknowledges their message
2. Asks clarifying questions to understand their needs
3. Is concise (2-3 sentences max)
4. Matches the tone of the original message

Reply only with the message text, no quotes or explanation."""

        try:
            return await self.llm_callback(prompt)
        except Exception as e:
            logger.error(f"Failed to generate reply: {e}")
            return "Thank you for reaching out. Could you tell me more about what you're looking for?"
    
    async def _auto_reply_message(self, msg: LinkedInMessage) -> bool:
        """Auto-reply to a message."""
        try:
            reply = await self._generate_reply_suggestion(msg)
            client = self._get_client()
            success = await asyncio.to_thread(
                client.send_message, msg.conversation_id, reply
            )
            if success:
                logger.info(f"Auto-replied to {msg.sender_name}")
            return success
        except Exception as e:
            logger.error(f"Failed to auto-reply: {e}")
            return False
    
    # ==================== CONNECTION HANDLING ====================
    
    async def check_connections(self) -> list[LinkedInConnection]:
        """Check for pending connection requests."""
        try:
            client = self._get_client()
            invitations = await asyncio.to_thread(client.get_pending_invitations)
            
            for inv in invitations:
                should_accept = await self._should_accept_connection(inv)
                
                if should_accept and self.config.auto_accept_connections:
                    success = await asyncio.to_thread(
                        client.accept_invitation, inv.invitation_id
                    )
                    if success:
                        logger.info(f"Auto-accepted connection from {inv.sender_name}")
                        if self._today_digest:
                            self._today_digest.auto_accepted.append(inv.sender_name)
                else:
                    # Queue for digest
                    self._pending_actions.append(PendingAction(
                        action_type='accept',
                        target_id=inv.invitation_id,
                        target_name=inv.sender_name,
                        context=f"{inv.sender_headline}\n{inv.message or 'No message'}",
                        suggested_content='accept' if should_accept else 'review'
                    ))
            
            return invitations
        except Exception as e:
            logger.error(f"Failed to check connections: {e}")
            return []
    
    async def _should_accept_connection(self, inv: LinkedInConnection) -> bool:
        """Determine if a connection request should be accepted."""
        # Check keywords
        headline_lower = inv.sender_headline.lower()
        message_lower = (inv.message or '').lower()
        
        # Ignore if matches ignore keywords
        for kw in self.config.ignore_keywords:
            if kw.lower() in headline_lower or kw.lower() in message_lower:
                return False
        
        # Accept if matches connection keywords
        for kw in self.config.connection_keywords:
            if kw.lower() in headline_lower or kw.lower() in message_lower:
                return True
        
        # Use LLM if available
        if self.llm_callback:
            prompt = f"""Should we accept this LinkedIn connection request?

User's role: {self.config.user_role}
User's goals: {self.config.user_goals}

Request from: {inv.sender_name}
Headline: {inv.sender_headline}
Message: {inv.message or 'No message provided'}

Consider:
- Is this person relevant to the user's industry or goals?
- Does their profile suggest potential value?
- Is it likely spam or mass outreach?

Reply with just 'YES' or 'NO'."""

            try:
                response = await self.llm_callback(prompt)
                return response.strip().upper().startswith('YES')
            except:
                pass
        
        # Default: accept (LinkedIn is about networking)
        return True
    
    # ==================== FEED & POSTS ====================
    
    async def collect_interesting_posts(self, limit: int = 30) -> list[LinkedInPost]:
        """Collect interesting posts from the feed."""
        try:
            client = self._get_client()
            posts = await asyncio.to_thread(client.get_feed_posts, limit)
            
            interesting = []
            for post in posts:
                score = await self._score_post(post)
                if score >= 0.6:  # Threshold for interesting
                    interesting.append(post)
                    
                    # Generate suggested reaction
                    if self.config.auto_react and self.config.trust_level >= 4:
                        # Auto-like high-quality posts
                        await asyncio.to_thread(client.like_post, post.post_id)
                    else:
                        comment = await self._generate_comment_suggestion(post)
                        self._pending_actions.append(PendingAction(
                            action_type='comment',
                            target_id=post.post_id,
                            target_name=post.author_name,
                            context=post.content[:300],
                            suggested_content=comment
                        ))
            
            return interesting[:10]  # Limit to top 10
        except Exception as e:
            logger.error(f"Failed to collect posts: {e}")
            return []
    
    async def _score_post(self, post: LinkedInPost) -> float:
        """Score a post's relevance (0-1)."""
        if not self.llm_callback:
            # Simple heuristic: engagement-based
            engagement = post.likes + post.comments * 2
            return min(engagement / 100, 1.0)
        
        prompt = f"""Rate the relevance of this LinkedIn post for the user.

User's role: {self.config.user_role}
User's interests: {', '.join(self.config.user_interests)}

Post by: {post.author_name} ({post.author_headline})
Content: {post.content[:500]}
Engagement: {post.likes} likes, {post.comments} comments

Rate from 0.0 to 1.0 based on:
- Relevance to user's industry/interests
- Quality of insights
- Engagement potential

Reply with just a number between 0.0 and 1.0."""

        try:
            response = await self.llm_callback(prompt)
            return float(response.strip())
        except:
            return 0.5
    
    async def _generate_comment_suggestion(self, post: LinkedInPost) -> str:
        """Generate a suggested comment for a post."""
        if not self.llm_callback:
            return "Great insights! Thanks for sharing."
        
        prompt = f"""Generate a thoughtful LinkedIn comment for this post.

User's role: {self.config.user_role}

Post by: {post.author_name}
Content: {post.content[:500]}

Write a comment that:
1. Adds value or a unique perspective
2. Is authentic and not generic
3. Is concise (1-2 sentences)
4. Could spark further conversation

Reply only with the comment text."""

        try:
            return await self.llm_callback(prompt)
        except:
            return "Great insights! Thanks for sharing."
    
    # ==================== POSTING ====================
    
    async def generate_post_suggestion(self, topic: Optional[str] = None) -> str:
        """Generate a post suggestion based on user profile."""
        if not self.llm_callback:
            return ""
        
        prompt = f"""Generate a LinkedIn post for this user.

User's role: {self.config.user_role}
User's goals: {self.config.user_goals}
User's interests: {', '.join(self.config.user_interests)}
{f'Topic: {topic}' if topic else ''}

Write a LinkedIn post that:
1. Shares valuable insights or experiences
2. Is authentic to the user's voice
3. Encourages engagement
4. Is 100-200 words
5. Includes a question or call-to-action

Reply only with the post text."""

        try:
            return await self.llm_callback(prompt)
        except:
            return ""
    
    async def create_post(self, content: str) -> bool:
        """Create a new LinkedIn post."""
        if not self.config.auto_post or self.config.trust_level < 5:
            # Queue for approval
            self._pending_actions.append(PendingAction(
                action_type='post',
                target_id='new_post',
                target_name='My LinkedIn',
                context='New post',
                suggested_content=content
            ))
            return False
        
        try:
            client = self._get_client()
            return await asyncio.to_thread(client.create_post, content)
        except Exception as e:
            logger.error(f"Failed to create post: {e}")
            return False
    
    # ==================== DIGEST ====================
    
    async def generate_daily_digest(self) -> LinkedInDigest:
        """Generate the daily LinkedIn digest."""
        self._today_digest = LinkedInDigest(date=datetime.now())
        
        # Check messages
        messages = await self.check_messages()
        for msg in messages:
            self._today_digest.new_messages.append({
                'from': msg.sender_name,
                'content': msg.content[:200],
                'time': msg.timestamp.isoformat()
            })
        
        # Check connections
        connections = await self.check_connections()
        for conn in connections:
            if conn.sender_name not in self._today_digest.auto_accepted:
                self._today_digest.pending_connections.append({
                    'name': conn.sender_name,
                    'headline': conn.sender_headline,
                    'message': conn.message
                })
        
        # Collect interesting posts
        posts = await self.collect_interesting_posts()
        for post in posts:
            self._today_digest.interesting_posts.append({
                'author': post.author_name,
                'content': post.content[:200],
                'likes': post.likes,
                'url': post.url
            })
        
        # Add pending actions as suggestions
        for action in self._pending_actions:
            self._today_digest.suggested_actions.append({
                'type': action.action_type,
                'target': action.target_name,
                'context': action.context[:100],
                'suggestion': action.suggested_content[:200]
            })
        
        return self._today_digest
    
    def format_digest_message(self, digest: LinkedInDigest) -> str:
        """Format digest as a message for WhatsApp/Telegram."""
        lines = [f"📊 *LinkedIn Daily Digest* - {digest.date.strftime('%d %B %Y')}\n"]
        
        # Auto-accepted connections
        if digest.auto_accepted:
            lines.append(f"✅ *Auto-accepted {len(digest.auto_accepted)} connections:*")
            for name in digest.auto_accepted[:5]:
                lines.append(f"  • {name}")
            if len(digest.auto_accepted) > 5:
                lines.append(f"  • ...and {len(digest.auto_accepted) - 5} more")
            lines.append("")
        
        # New messages
        if digest.new_messages:
            lines.append(f"💬 *{len(digest.new_messages)} new messages:*")
            for msg in digest.new_messages[:5]:
                lines.append(f"  • *{msg['from']}*: {msg['content'][:50]}...")
            lines.append("")
        
        # Pending connections
        if digest.pending_connections:
            lines.append(f"🤝 *{len(digest.pending_connections)} connection requests to review:*")
            for conn in digest.pending_connections[:5]:
                lines.append(f"  • *{conn['name']}* - {conn['headline'][:40]}")
            lines.append("")
        
        # Interesting posts
        if digest.interesting_posts:
            lines.append(f"📰 *{len(digest.interesting_posts)} interesting posts:*")
            for post in digest.interesting_posts[:5]:
                lines.append(f"  • *{post['author']}*: {post['content'][:50]}...")
                if post.get('url'):
                    lines.append(f"    {post['url']}")
            lines.append("")
        
        # Suggested actions
        if digest.suggested_actions:
            lines.append(f"💡 *{len(digest.suggested_actions)} suggested actions:*")
            for action in digest.suggested_actions[:5]:
                lines.append(f"  • [{action['type']}] {action['target']}")
                lines.append(f"    Suggestion: {action['suggestion'][:60]}...")
            lines.append("")
        
        if not any([digest.new_messages, digest.pending_connections, 
                    digest.interesting_posts, digest.suggested_actions]):
            lines.append("No new activity today. Your LinkedIn is quiet! 🤫")
        
        lines.append("\n_Reply with action numbers to execute, or 'skip' to dismiss._")
        
        return "\n".join(lines)
    
    async def send_digest(self) -> bool:
        """Send the daily digest via configured channel."""
        if not self.config.daily_digest_enabled:
            return False
        
        digest = await self.generate_daily_digest()
        message = self.format_digest_message(digest)
        
        if self.message_callback:
            try:
                await self.message_callback(
                    channel=self.config.daily_digest_channel,
                    recipient=self.config.daily_digest_recipient,
                    content=message
                )
                logger.info("Sent LinkedIn daily digest")
                return True
            except Exception as e:
                logger.error(f"Failed to send digest: {e}")
        
        return False
    
    # ==================== MAIN LOOP ====================
    
    async def run(self) -> None:
        """Run the LinkedIn monitoring service."""
        if not self.config.enabled:
            logger.info("LinkedIn service is disabled")
            return
        
        self._running = True
        logger.info("LinkedIn service started")
        
        while self._running:
            try:
                now = datetime.now()
                
                # Check for daily digest time
                digest_time = datetime.strptime(self.config.daily_digest_time, "%H:%M").time()
                if (now.time().hour == digest_time.hour and 
                    now.time().minute == digest_time.minute and
                    (now - self._last_check) > timedelta(hours=20)):
                    await self.send_digest()
                    self._last_check = now
                    self._pending_actions.clear()
                
                # Periodic checks (every 30 minutes)
                if (now - self._last_check) > timedelta(minutes=30):
                    await self.check_connections()
                    self._last_check = now
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"LinkedIn service error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    def stop(self) -> None:
        """Stop the service."""
        self._running = False
        logger.info("LinkedIn service stopped")
