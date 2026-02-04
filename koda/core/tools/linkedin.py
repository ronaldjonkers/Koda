"""LinkedIn tool for the agent."""

import json
from typing import Any, Optional

from koda.core.tools.base import Tool
from koda.integrations.linkedin_client import LinkedInClient


class LinkedInTool(Tool):
    """
    Tool for LinkedIn operations.
    
    Allows the agent to:
    - Check messages and reply
    - Manage connection requests
    - View and interact with posts
    - Create posts
    - Search for people
    """
    
    name = "linkedin"
    description = """Manage LinkedIn: messages, connections, posts, and search.

Actions:
- get_messages: Get unread LinkedIn messages
- reply_message: Reply to a conversation
- get_connections: Get pending connection requests  
- accept_connection: Accept a connection request
- reject_connection: Reject a connection request
- get_feed: Get interesting posts from feed
- get_my_posts: Get my own LinkedIn posts
- get_post_comments: Get comments on a specific post
- like_post: Like a post
- comment_post: Comment on a post
- reply_to_comment: Reply to a specific comment
- create_post: Create a new LinkedIn post
- search_people: Search for people on LinkedIn
- get_profile: Get someone's profile"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "get_messages", "reply_message",
                    "get_connections", "accept_connection", "reject_connection",
                    "get_feed", "get_my_posts", "get_post_comments",
                    "like_post", "comment_post", "reply_to_comment", "create_post",
                    "search_people", "get_profile"
                ],
                "description": "The LinkedIn action to perform"
            },
            "conversation_id": {
                "type": "string",
                "description": "Conversation ID for reply_message"
            },
            "message": {
                "type": "string",
                "description": "Message content for reply_message or create_post"
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
        self.email = email
        self.password = password
        self.enabled = enabled
        self._client: Optional[LinkedInClient] = None
    
    def _get_client(self) -> LinkedInClient:
        """Get or create LinkedIn client."""
        if not self.enabled or not self.email or not self.password:
            raise ValueError("LinkedIn is not configured. Run 'koda config linkedin' first.")
        
        if self._client is None:
            self._client = LinkedInClient(
                email=self.email,
                password=self.password
            )
        return self._client
    
    async def execute(self, action: str, **kwargs: Any) -> str:
        if not self.enabled:
            return json.dumps({"error": "LinkedIn integration is not enabled. Run 'koda config linkedin' to set it up."})
        
        try:
            if action == "get_messages":
                return await self._get_messages(kwargs.get('limit', 10))
            elif action == "reply_message":
                return await self._reply_message(
                    kwargs.get('conversation_id', ''),
                    kwargs.get('message', '')
                )
            elif action == "get_connections":
                return await self._get_connections()
            elif action == "accept_connection":
                return await self._accept_connection(kwargs.get('invitation_id', ''))
            elif action == "reject_connection":
                return await self._reject_connection(kwargs.get('invitation_id', ''))
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
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    
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
