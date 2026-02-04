"""LinkedIn tool for the agent."""
from __future__ import annotations

import json
from typing import Any, Optional

from loguru import logger
from koda.core.tools.base import Tool
from koda.integrations.linkedin_client import LinkedInClient


def _load_linkedin_config() -> dict:
    """Load LinkedIn config from file at runtime."""
    try:
        from koda.config.loader import load_config
        config = load_config()
        li = config.integrations.linkedin
        return {
            "enabled": li.enabled,
            "email": li.email,
            "password": li.password
        }
    except Exception:
        return {"enabled": False, "email": "", "password": ""}


class LinkedInTool(Tool):
    """
    Tool for LinkedIn operations.
    
    Allows the agent to:
    - Check messages and reply
    - Manage connection requests
    - View and interact with posts
    - Create posts
    - Search for people
    
    If LinkedIn is not configured, this tool helps the user set it up.
    """
    
    name = "linkedin"
    description = """Manage LinkedIn: messages, connections, posts, and search.

Actions:
**Inbox/Messages:**
- get_messages: Get unread LinkedIn messages
- get_conversations: Get all recent conversations (inbox overview)
- get_conversation: Get messages from a specific conversation
- reply_message: Reply to a conversation
- send_new_message: Start a new conversation with someone

**Connections:**
- get_connections: Get pending connection requests  
- accept_connection: Accept a connection request
- reject_connection: Reject a connection request
- send_connection: Send a connection request to someone

**Posts & Feed (uses browser automation):**
- get_feed: Get interesting posts from feed
- get_my_posts: Get my own LinkedIn posts
- get_post_comments: Get comments on a specific post
- like_post: Like a post
- comment_post: Comment on a post (supports @mentions)
- reply_to_comment: Reply to a specific comment
- create_post: Create a new LinkedIn post (with optional image)

**Analytics & Style:**
- get_analytics: Get profile stats and post analytics
- learn_style: Learn user's writing style for personalized suggestions
- get_style: Get learned writing style profile

**Profiles:**
- search_people: Search for people on LinkedIn
- get_profile: Get someone's profile
- get_my_profile: Get my own profile

**Session:**
- check_session: Check if browser session is valid
- login: Open browser for manual login (use when session expired)"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "get_messages", "get_conversations", "get_conversation", "reply_message", "send_new_message",
                    "get_connections", "accept_connection", "reject_connection", "send_connection",
                    "get_feed", "get_my_posts", "get_post_comments",
                    "like_post", "comment_post", "reply_to_comment", "create_post",
                    "search_people", "get_profile", "get_my_profile",
                    "get_analytics", "learn_style", "get_style",
                    "check_session", "login"
                ],
                "description": "The LinkedIn action to perform"
            },
            "image_path": {
                "type": "string",
                "description": "Path to image file for create_post"
            },
            "post_url": {
                "type": "string",
                "description": "Full LinkedIn post URL for comment_post"
            },
            "conversation_id": {
                "type": "string",
                "description": "Conversation ID for reply_message or get_conversation"
            },
            "message": {
                "type": "string",
                "description": "Message content for reply_message, send_new_message, create_post, or send_connection"
            },
            "recipient_id": {
                "type": "string",
                "description": "Profile public ID for send_new_message or send_connection (the part after /in/)"
            },
            "invitation_id": {
                "type": "string",
                "description": "Invitation ID for accept/reject_connection"
            },
            "post_id": {
                "type": "string",
                "description": "Post ID for like_post, comment_post, get_post_comments, or reply_to_comment"
            },
            "comment": {
                "type": "string",
                "description": "Comment text for comment_post"
            },
            "comment_id": {
                "type": "string",
                "description": "Comment ID for reply_to_comment"
            },
            "reply_text": {
                "type": "string",
                "description": "Reply text for reply_to_comment"
            },
            "query": {
                "type": "string",
                "description": "Search query for search_people"
            },
            "profile_id": {
                "type": "string",
                "description": "Profile public ID for get_profile (the part after /in/)"
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return",
                "default": 10
            }
        },
        "required": ["action"]
    }
    
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        enabled: bool = False
    ):
        # Initial values (can be overridden by dynamic config)
        self._initial_email = email
        self._initial_password = password
        self._initial_enabled = enabled
        self._client: Optional[LinkedInClient] = None
        self._playwright_client = None
        self._playwright_available = False
        self._init_playwright()
    
    def _init_playwright(self):
        """Initialize Playwright client if available."""
        try:
            from koda.integrations.linkedin_playwright import LinkedInPlaywright
            self._playwright_client = LinkedInPlaywright(headless=True)
            self._playwright_available = True
            logger.debug("LinkedIn Playwright client initialized")
        except ImportError as e:
            logger.debug(f"Playwright not available for LinkedIn: {e}")
    
    def _get_config(self) -> dict:
        """Get current LinkedIn config (reloads from file each time)."""
        cfg = _load_linkedin_config()
        # Use dynamic config if available, otherwise fall back to init values
        if cfg.get("enabled"):
            return cfg
        elif self._initial_enabled:
            return {
                "enabled": self._initial_enabled,
                "email": self._initial_email,
                "password": self._initial_password
            }
        return cfg
    
    def _get_client(self) -> LinkedInClient:
        """Get or create LinkedIn client."""
        cfg = self._get_config()
        if not cfg.get("enabled") or not cfg.get("email") or not cfg.get("password"):
            raise ValueError("LinkedIn is not configured")
        
        # Recreate client if credentials changed
        if self._client is None or self._client.email != cfg["email"]:
            self._client = LinkedInClient(
                email=cfg["email"],
                password=cfg["password"]
            )
        return self._client
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        cfg = self._get_config()
        if not cfg.get("enabled"):
            return json.dumps({
                "error": "LinkedIn is not configured",
                "setup_required": True,
                "message": "LinkedIn is not set up yet. To configure LinkedIn, the user needs to provide their LinkedIn email and password. You can ask them directly or they can use the /addlinkedin command via WhatsApp.",
                "instructions": "Ask the user: 'I need your LinkedIn credentials to access your profile. What is your LinkedIn email address?'"
            })
        
        try:
            if action == "get_messages":
                return await self._get_messages(kwargs.get('limit', 10))
            elif action == "get_conversations":
                return await self._get_conversations(kwargs.get('limit', 20))
            elif action == "get_conversation":
                return await self._get_conversation(
                    kwargs.get('conversation_id', ''),
                    kwargs.get('limit', 20)
                )
            elif action == "reply_message":
                return await self._reply_message(
                    kwargs.get('conversation_id', ''),
                    kwargs.get('message', '')
                )
            elif action == "send_new_message":
                return await self._send_new_message(
                    kwargs.get('recipient_id', ''),
                    kwargs.get('message', '')
                )
            elif action == "get_connections":
                return await self._get_connections()
            elif action == "accept_connection":
                return await self._accept_connection(kwargs.get('invitation_id', ''))
            elif action == "reject_connection":
                return await self._reject_connection(kwargs.get('invitation_id', ''))
            elif action == "send_connection":
                return await self._send_connection(
                    kwargs.get('recipient_id', ''),
                    kwargs.get('message', '')
                )
            elif action == "get_feed":
                return await self._get_feed(kwargs.get('limit', 10))
            elif action == "get_my_posts":
                return await self._get_my_posts(kwargs.get('limit', 10))
            elif action == "get_post_comments":
                return await self._get_post_comments(
                    kwargs.get('post_id', ''),
                    kwargs.get('limit', 20)
                )
            elif action == "like_post":
                return await self._like_post(kwargs.get('post_id', ''))
            elif action == "comment_post":
                return await self._comment_post(
                    kwargs.get('post_id', ''),
                    kwargs.get('comment', '')
                )
            elif action == "reply_to_comment":
                return await self._reply_to_comment(
                    kwargs.get('post_id', ''),
                    kwargs.get('comment_id', ''),
                    kwargs.get('reply_text', '')
                )
            elif action == "create_post":
                return await self._create_post(kwargs.get('message', ''))
            elif action == "search_people":
                return await self._search_people(
                    kwargs.get('query', ''),
                    kwargs.get('limit', 10)
                )
            elif action == "get_profile":
                return await self._get_profile(kwargs.get('profile_id', ''))
            elif action == "get_my_profile":
                return await self._get_my_profile()
            # Playwright-based actions
            elif action == "get_analytics":
                return await self._get_analytics()
            elif action == "learn_style":
                return await self._learn_style()
            elif action == "get_style":
                return await self._get_style()
            elif action == "check_session":
                return await self._check_session()
            elif action == "login":
                return await self._login()
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    async def _get_conversations(self, limit: int) -> str:
        """Get all recent conversations (inbox overview)."""
        import asyncio
        client = self._get_client()
        conversations = await asyncio.to_thread(client.get_conversations, limit)
        
        result = []
        for conv in conversations:
            participants = conv.get('participants', [])
            participant_names = []
            for p in participants:
                member = p.get('com.linkedin.voyager.messaging.MessagingMember', {})
                mini = member.get('miniProfile', {})
                name = f"{mini.get('firstName', '')} {mini.get('lastName', '')}".strip()
                if name and not member.get('isSelf', False):
                    participant_names.append(name)
            
            result.append({
                "conversation_id": conv.get('entityUrn', ''),
                "participants": participant_names or ["Unknown"],
                "unread_count": conv.get('unreadCount', 0),
                "last_activity": conv.get('lastActivityAt', 0)
            })
        
        return json.dumps({
            "conversations": result,
            "count": len(result)
        }, indent=2)
    
    async def _get_conversation(self, conversation_id: str, limit: int) -> str:
        """Get messages from a specific conversation."""
        if not conversation_id:
            return json.dumps({"error": "conversation_id is required"})
        
        import asyncio
        client = self._get_client()
        messages = await asyncio.to_thread(client.get_conversation_messages, conversation_id, limit)
        
        result = []
        for msg in messages:
            result.append({
                "from": msg.sender_name,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "is_from_me": msg.is_from_me
            })
        
        return json.dumps({
            "messages": result,
            "count": len(result),
            "conversation_id": conversation_id
        }, indent=2)
    
    async def _get_messages(self, limit: int) -> str:
        """Get unread messages."""
        import asyncio
        client = self._get_client()
        messages = await asyncio.to_thread(client.get_unread_messages)
        
        result = []
        for msg in messages[:limit]:
            result.append({
                "conversation_id": msg.conversation_id,
                "from": msg.sender_name,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            })
        
        return json.dumps({
            "messages": result,
            "count": len(result)
        }, indent=2)
    
    async def _reply_message(self, conversation_id: str, message: str) -> str:
        """Reply to a conversation."""
        if not conversation_id or not message:
            return json.dumps({"error": "conversation_id and message are required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.send_message, conversation_id, message)
        
        return json.dumps({
            "success": success,
            "conversation_id": conversation_id
        })
    
    async def _send_new_message(self, recipient_id: str, message: str) -> str:
        """Send a new message to someone (start new conversation)."""
        if not recipient_id or not message:
            return json.dumps({"error": "recipient_id and message are required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.send_message_to_profile, recipient_id, message)
        
        return json.dumps({
            "success": success,
            "recipient_id": recipient_id,
            "action": "message_sent"
        })
    
    async def _get_connections(self) -> str:
        """Get pending connection requests."""
        import asyncio
        client = self._get_client()
        invitations = await asyncio.to_thread(client.get_pending_invitations)
        
        result = []
        for inv in invitations:
            result.append({
                "invitation_id": inv.invitation_id,
                "name": inv.sender_name,
                "headline": inv.sender_headline,
                "message": inv.message,
                "profile_url": inv.sender_profile_url
            })
        
        return json.dumps({
            "pending_connections": result,
            "count": len(result)
        }, indent=2)
    
    async def _accept_connection(self, invitation_id: str) -> str:
        """Accept a connection request."""
        if not invitation_id:
            return json.dumps({"error": "invitation_id is required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.accept_invitation, invitation_id)
        
        return json.dumps({
            "success": success,
            "invitation_id": invitation_id,
            "action": "accepted"
        })
    
    async def _reject_connection(self, invitation_id: str) -> str:
        """Reject a connection request."""
        if not invitation_id:
            return json.dumps({"error": "invitation_id is required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.reject_invitation, invitation_id)
        
        return json.dumps({
            "success": success,
            "invitation_id": invitation_id,
            "action": "rejected"
        })
    
    async def _send_connection(self, recipient_id: str, message: str = "") -> str:
        """Send a connection request to someone."""
        if not recipient_id:
            return json.dumps({"error": "recipient_id is required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.send_connection_request, recipient_id, message)
        
        return json.dumps({
            "success": success,
            "recipient_id": recipient_id,
            "action": "connection_request_sent"
        })
    
    async def _get_feed(self, limit: int) -> str:
        """Get posts from feed."""
        import asyncio
        client = self._get_client()
        posts = await asyncio.to_thread(client.get_feed_posts, limit)
        
        result = []
        for post in posts:
            result.append({
                "post_id": post.post_id,
                "author": post.author_name,
                "headline": post.author_headline,
                "content": post.content[:500],
                "likes": post.likes,
                "comments": post.comments,
                "url": post.url
            })
        
        return json.dumps({
            "posts": result,
            "count": len(result)
        }, indent=2)
    
    async def _like_post(self, post_id: str) -> str:
        """Like a post."""
        if not post_id:
            return json.dumps({"error": "post_id is required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.like_post, post_id)
        
        return json.dumps({
            "success": success,
            "post_id": post_id,
            "action": "liked"
        })
    
    async def _comment_post(self, post_id: str, comment: str) -> str:
        """Comment on a post."""
        if not post_id or not comment:
            return json.dumps({"error": "post_id and comment are required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.comment_on_post, post_id, comment)
        
        return json.dumps({
            "success": success,
            "post_id": post_id,
            "action": "commented"
        })
    
    async def _create_post(self, content: str) -> str:
        """Create a new post."""
        if not content:
            return json.dumps({"error": "message content is required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.create_post, content)
        
        return json.dumps({
            "success": success,
            "action": "posted"
        })
    
    async def _get_my_posts(self, limit: int) -> str:
        """Get my own posts."""
        import asyncio
        client = self._get_client()
        posts = await asyncio.to_thread(client.get_my_posts, limit)
        
        result = []
        for post in posts:
            result.append({
                "post_id": post.post_id,
                "content": post.content[:500],
                "likes": post.likes,
                "comments": post.comments,
                "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                "url": post.url
            })
        
        return json.dumps({
            "my_posts": result,
            "count": len(result)
        }, indent=2)
    
    async def _get_post_comments(self, post_id: str, limit: int) -> str:
        """Get comments on a post."""
        if not post_id:
            return json.dumps({"error": "post_id is required"})
        
        import asyncio
        client = self._get_client()
        comments = await asyncio.to_thread(client.get_post_comments, post_id, limit)
        
        return json.dumps({
            "comments": comments,
            "count": len(comments),
            "post_id": post_id
        }, indent=2)
    
    async def _reply_to_comment(self, post_id: str, comment_id: str, reply_text: str) -> str:
        """Reply to a comment on a post."""
        if not post_id or not comment_id or not reply_text:
            return json.dumps({"error": "post_id, comment_id, and reply_text are required"})
        
        import asyncio
        client = self._get_client()
        success = await asyncio.to_thread(client.reply_to_comment, post_id, comment_id, reply_text)
        
        return json.dumps({
            "success": success,
            "post_id": post_id,
            "comment_id": comment_id,
            "action": "replied"
        })
    
    async def _search_people(self, query: str, limit: int) -> str:
        """Search for people."""
        if not query:
            return json.dumps({"error": "query is required"})
        
        import asyncio
        client = self._get_client()
        profiles = await asyncio.to_thread(client.search_people, query, limit)
        
        result = []
        for p in profiles:
            result.append({
                "name": f"{p.first_name} {p.last_name}",
                "headline": p.headline,
                "location": p.location,
                "profile_url": p.profile_url
            })
        
        return json.dumps({
            "results": result,
            "count": len(result)
        }, indent=2)
    
    async def _get_profile(self, profile_id: str) -> str:
        """Get a profile."""
        if not profile_id:
            return json.dumps({"error": "profile_id is required"})
        
        import asyncio
        client = self._get_client()
        profile = await asyncio.to_thread(client.get_profile, profile_id)
        
        if not profile:
            return json.dumps({"error": f"Profile not found: {profile_id}"})
        
        return json.dumps({
            "name": f"{profile.first_name} {profile.last_name}",
            "headline": profile.headline,
            "summary": profile.summary,
            "industry": profile.industry,
            "location": profile.location,
            "profile_url": profile.profile_url
        }, indent=2)
    
    async def _get_my_profile(self) -> str:
        """Get my own profile."""
        import asyncio
        client = self._get_client()
        profile = await asyncio.to_thread(client.get_my_profile)
        
        if not profile:
            return json.dumps({"error": "Could not retrieve your profile"})
        
        return json.dumps({
            "name": f"{profile.first_name} {profile.last_name}",
            "headline": profile.headline,
            "summary": profile.summary,
            "industry": profile.industry,
            "location": profile.location,
            "profile_url": profile.profile_url
        }, indent=2)
    
    # =========================================================================
    # Playwright-based methods (browser automation)
    # =========================================================================
    
    async def _check_session(self) -> str:
        """Check if browser session is valid."""
        if not self._playwright_available:
            return json.dumps({
                "error": "Playwright not available",
                "message": "Install Playwright: pip install playwright && playwright install chromium"
            })
        
        valid, message = await self._playwright_client.check_session()
        return json.dumps({
            "valid": valid,
            "message": message,
            "tip": "Use 'login' action if session expired" if not valid else None
        })
    
    async def _login(self) -> str:
        """Open browser for manual login."""
        if not self._playwright_available:
            return json.dumps({
                "error": "Playwright not available",
                "message": "Install Playwright: pip install playwright && playwright install chromium"
            })
        
        return json.dumps({
            "message": "To log in to LinkedIn, run this command in terminal:",
            "command": "python3 -c \"import asyncio; from koda.integrations.linkedin_playwright import LinkedInPlaywright; c = LinkedInPlaywright(headless=False); asyncio.run(c.login_interactive())\"",
            "note": "After login, the session will be saved for future use"
        })
    
    async def _get_analytics(self) -> str:
        """Get profile analytics using Playwright."""
        if not self._playwright_available:
            return json.dumps({"error": "Playwright not available for analytics"})
        
        stats = await self._playwright_client.get_profile_stats()
        
        if not stats:
            return json.dumps({
                "error": "Could not retrieve analytics",
                "tip": "Check session with 'check_session' action"
            })
        
        return json.dumps({
            "profile_views": stats.get("profile_views", 0),
            "post_impressions": stats.get("post_impressions", 0),
            "search_appearances": stats.get("search_appearances", 0)
        }, indent=2)
    
    async def _learn_style(self) -> str:
        """Learn user's writing style from their LinkedIn content."""
        if not self._playwright_available:
            return json.dumps({"error": "Playwright not available for style learning"})
        
        style = await self._playwright_client.learn_style()
        
        return json.dumps({
            "success": True,
            "style": {
                "language": style.language,
                "tone": style.tone,
                "emoji_usage": style.emoji_usage,
                "top_hashtags": style.top_hashtags[:5],
                "sample_posts_count": len(style.sample_posts)
            },
            "message": "Style profile saved. I'll use this to match your voice when suggesting content."
        }, indent=2)
    
    async def _get_style(self) -> str:
        """Get the learned style profile."""
        if not self._playwright_available:
            return json.dumps({"error": "Playwright not available"})
        
        style = self._playwright_client.get_style()
        
        if not style:
            return json.dumps({
                "error": "No style profile found",
                "tip": "Use 'learn_style' action to analyze your writing style"
            })
        
        return json.dumps({
            "language": style.language,
            "tone": style.tone,
            "emoji_usage": style.emoji_usage,
            "top_hashtags": style.top_hashtags,
            "sample_posts": style.sample_posts[:3] if style.sample_posts else []
        }, indent=2)
