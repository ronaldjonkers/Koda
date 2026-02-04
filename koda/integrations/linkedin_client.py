"""LinkedIn client for automation and monitoring."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class LinkedInMessage:
    """A LinkedIn message."""
    conversation_id: str
    sender_name: str
    sender_urn: str
    content: str
    timestamp: datetime
    is_from_me: bool = False


@dataclass
class LinkedInConnection:
    """A LinkedIn connection request."""
    invitation_id: str
    sender_name: str
    sender_urn: str
    sender_headline: str
    sender_profile_url: str
    message: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class LinkedInPost:
    """A LinkedIn post from feed."""
    post_id: str
    author_name: str
    author_urn: str
    author_headline: str
    content: str
    timestamp: datetime
    likes: int = 0
    comments: int = 0
    url: Optional[str] = None


@dataclass
class LinkedInProfile:
    """LinkedIn profile information."""
    urn: str
    first_name: str
    last_name: str
    headline: str
    summary: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None


class LinkedInClient:
    """
    LinkedIn client using the unofficial linkedin-api library.
    
    This client provides access to LinkedIn features:
    - Messages/conversations
    - Connection requests
    - Feed posts
    - Profile information
    """
    
    def __init__(
        self,
        email: str,
        password: str,
        cookies_path: Optional[Path] = None,
        refresh_cookies: bool = False
    ):
        self.email = email
        self.password = password
        self.cookies_path = cookies_path or Path.home() / ".koda" / "linkedin_cookies.json"
        self._api = None
        self._refresh_cookies = refresh_cookies
    
    def _ensure_connected(self) -> None:
        """Ensure we have an authenticated API connection."""
        if self._api is not None:
            return
        
        try:
            from linkedin_api import Linkedin
        except ImportError:
            raise ImportError(
                "linkedin-api not installed. Run: pip install linkedin-api"
            )
        
        # Try to load existing cookies (but be ready to retry without them)
        cookies = None
        if self.cookies_path.exists() and not self._refresh_cookies:
            try:
                import requests
                with open(self.cookies_path) as f:
                    cookies_dict = json.load(f)
                # Convert dict back to RequestsCookieJar
                cookies = requests.cookies.RequestsCookieJar()
                for name, value in cookies_dict.items():
                    cookies.set(name, value)
                logger.debug(f"Loaded {len(cookies_dict)} LinkedIn cookies from cache")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
                cookies = None
        
        # Authenticate - try with cookies first, then without
        try:
            if cookies:
                try:
                    self._api = Linkedin(self.email, self.password, cookies=cookies)
                    # Test the connection by making a simple call
                    self._api.get_user_profile()
                    logger.info("LinkedIn connected with cached cookies")
                except Exception as cookie_err:
                    logger.warning(f"Cached cookies failed: {cookie_err}, trying fresh login")
                    # Delete old cookies and try fresh
                    if self.cookies_path.exists():
                        self.cookies_path.unlink()
                    self._api = Linkedin(self.email, self.password)
                    self._save_cookies()
                    logger.info("LinkedIn connected with fresh login")
            else:
                self._api = Linkedin(self.email, self.password)
                self._save_cookies()
                logger.info("LinkedIn connected with fresh login")
        except Exception as e:
            logger.error(f"LinkedIn authentication failed: {e}")
            # Clear any stale cookies
            if self.cookies_path.exists():
                try:
                    self.cookies_path.unlink()
                except:
                    pass
            raise
    
    def _save_cookies(self) -> None:
        """Save authentication cookies."""
        if self._api and hasattr(self._api, 'client') and hasattr(self._api.client, 'cookies'):
            try:
                self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
                # Save as simple dict of name:value
                cookies_dict = {c.name: c.value for c in self._api.client.cookies}
                with open(self.cookies_path, 'w') as f:
                    json.dump(cookies_dict, f)
                logger.debug("Saved LinkedIn cookies")
            except Exception as e:
                logger.warning(f"Failed to save cookies: {e}")
    
    # ==================== MESSAGES ====================
    
    def get_conversations(self, limit: int = 20) -> list[dict]:
        """Get recent conversations."""
        self._ensure_connected()
        try:
            conversations = self._api.get_conversations()
            return conversations.get('elements', [])[:limit]
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}")
            return []
    
    def get_conversation_messages(
        self, 
        conversation_urn: str, 
        limit: int = 20
    ) -> list[LinkedInMessage]:
        """Get messages from a specific conversation."""
        self._ensure_connected()
        try:
            conv = self._api.get_conversation(conversation_urn)
            messages = []
            
            for msg in conv.get('elements', [])[:limit]:
                event = msg.get('eventContent', {})
                msg_content = event.get('messageEvent', {})
                
                # Get sender info
                sender = msg.get('from', {})
                sender_profile = sender.get('com.linkedin.voyager.messaging.MessagingMember', {})
                mini_profile = sender_profile.get('miniProfile', {})
                
                messages.append(LinkedInMessage(
                    conversation_id=conversation_urn,
                    sender_name=f"{mini_profile.get('firstName', '')} {mini_profile.get('lastName', '')}".strip(),
                    sender_urn=mini_profile.get('entityUrn', ''),
                    content=msg_content.get('attributedBody', {}).get('text', ''),
                    timestamp=datetime.fromtimestamp(msg.get('createdAt', 0) / 1000),
                    is_from_me=sender_profile.get('isSelf', False)
                ))
            
            return messages
        except Exception as e:
            logger.error(f"Failed to get conversation messages: {e}")
            return []
    
    def get_unread_messages(self) -> list[LinkedInMessage]:
        """Get all unread messages."""
        self._ensure_connected()
        messages = []
        
        try:
            conversations = self.get_conversations(limit=50)
            
            for conv in conversations:
                # Check if conversation has unread messages
                if conv.get('unreadCount', 0) > 0:
                    conv_urn = conv.get('entityUrn', '')
                    if conv_urn:
                        conv_messages = self.get_conversation_messages(conv_urn, limit=5)
                        # Get only messages not from me
                        unread = [m for m in conv_messages if not m.is_from_me]
                        messages.extend(unread[:conv.get('unreadCount', 1)])
            
            return messages
        except Exception as e:
            logger.error(f"Failed to get unread messages: {e}")
            return []
    
    def send_message(self, conversation_urn: str, message: str) -> bool:
        """Send a message to a conversation."""
        self._ensure_connected()
        try:
            self._api.send_message(message, conversation_urn_id=conversation_urn)
            logger.info(f"Sent message to conversation {conversation_urn}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    def send_message_to_profile(self, profile_urn: str, message: str) -> bool:
        """Send a message to a profile (new conversation)."""
        self._ensure_connected()
        try:
            # Extract profile ID from URN
            profile_id = profile_urn.split(':')[-1] if ':' in profile_urn else profile_urn
            self._api.send_message(message, recipients=[profile_id])
            logger.info(f"Sent message to profile {profile_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to profile: {e}")
            return False
    
    # ==================== CONNECTIONS ====================
    
    def get_pending_invitations(self) -> list[LinkedInConnection]:
        """Get pending connection requests."""
        self._ensure_connected()
        try:
            invitations = self._api.get_invitations()
            connections = []
            
            for inv in invitations:
                sender = inv.get('fromMember', {})
                connections.append(LinkedInConnection(
                    invitation_id=inv.get('entityUrn', ''),
                    sender_name=f"{sender.get('firstName', '')} {sender.get('lastName', '')}".strip(),
                    sender_urn=sender.get('entityUrn', ''),
                    sender_headline=sender.get('occupation', ''),
                    sender_profile_url=f"https://linkedin.com/in/{sender.get('publicIdentifier', '')}",
                    message=inv.get('message'),
                    timestamp=datetime.fromtimestamp(inv.get('sentTime', 0) / 1000) if inv.get('sentTime') else None
                ))
            
            return connections
        except Exception as e:
            logger.error(f"Failed to get invitations: {e}")
            return []
    
    def accept_invitation(self, invitation_urn: str) -> bool:
        """Accept a connection request."""
        self._ensure_connected()
        try:
            # Extract invitation ID
            inv_id = invitation_urn.split(':')[-1] if ':' in invitation_urn else invitation_urn
            self._api.reply_invitation(inv_id, action='accept')
            logger.info(f"Accepted invitation {inv_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to accept invitation: {e}")
            return False
    
    def reject_invitation(self, invitation_urn: str) -> bool:
        """Reject a connection request."""
        self._ensure_connected()
        try:
            inv_id = invitation_urn.split(':')[-1] if ':' in invitation_urn else invitation_urn
            self._api.reply_invitation(inv_id, action='reject')
            logger.info(f"Rejected invitation {inv_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reject invitation: {e}")
            return False
    
    def send_connection_request(self, profile_id: str, message: str = "") -> bool:
        """Send a connection request to someone."""
        self._ensure_connected()
        try:
            if message:
                self._api.add_connection(profile_id, message=message)
            else:
                self._api.add_connection(profile_id)
            logger.info(f"Sent connection request to {profile_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send connection request: {e}")
            return False
    
    # ==================== FEED & POSTS ====================
    
    def get_feed_posts(self, limit: int = 20) -> list[LinkedInPost]:
        """Get posts from the feed."""
        self._ensure_connected()
        try:
            feed = self._api.get_feed_posts(limit=limit)
            posts = []
            
            for item in feed:
                # Extract post data
                update = item.get('value', {}).get('com.linkedin.voyager.feed.render.UpdateV2', {})
                actor = update.get('actor', {})
                content = update.get('commentary', {}).get('text', {}).get('text', '')
                
                # Get engagement stats
                social = update.get('socialDetail', {})
                likes = social.get('totalSocialActivityCounts', {}).get('numLikes', 0)
                comments = social.get('totalSocialActivityCounts', {}).get('numComments', 0)
                
                if content:  # Only include posts with content
                    posts.append(LinkedInPost(
                        post_id=update.get('urn', ''),
                        author_name=actor.get('name', {}).get('text', ''),
                        author_urn=actor.get('urn', ''),
                        author_headline=actor.get('description', {}).get('text', ''),
                        content=content,
                        timestamp=datetime.fromtimestamp(update.get('createdTime', 0) / 1000) if update.get('createdTime') else datetime.now(),
                        likes=likes,
                        comments=comments,
                        url=update.get('permalink')
                    ))
            
            return posts
        except Exception as e:
            logger.error(f"Failed to get feed posts: {e}")
            return []
    
    def like_post(self, post_urn: str) -> bool:
        """Like a post."""
        self._ensure_connected()
        try:
            self._api.react_to_post(post_urn, 'LIKE')
            logger.info(f"Liked post {post_urn}")
            return True
        except Exception as e:
            logger.error(f"Failed to like post: {e}")
            return False
    
    def comment_on_post(self, post_urn: str, comment: str) -> bool:
        """Comment on a post."""
        self._ensure_connected()
        try:
            self._api.comment_on_post(post_urn, comment)
            logger.info(f"Commented on post {post_urn}")
            return True
        except Exception as e:
            logger.error(f"Failed to comment on post: {e}")
            return False
    
    def create_post(self, content: str, visibility: str = "PUBLIC") -> bool:
        """Create a new post."""
        self._ensure_connected()
        try:
            self._api.post(content)
            logger.info("Created new post")
            return True
        except Exception as e:
            logger.error(f"Failed to create post: {e}")
            return False
    
    def get_my_posts(self, limit: int = 10) -> list[LinkedInPost]:
        """Get my own posts."""
        self._ensure_connected()
        try:
            # Get my profile URN first
            my_profile = self._api.get_user_profile()
            my_urn = my_profile.get('entityUrn', '') or my_profile.get('publicIdentifier', '')
            
            # Get posts from my profile
            posts = self._api.get_profile_posts(my_urn, post_count=limit)
            result = []
            
            for item in posts:
                update = item if isinstance(item, dict) else {}
                content = ''
                post_urn = ''
                likes = 0
                comments = 0
                
                # Try different content locations
                if 'commentary' in update:
                    content = update.get('commentary', {}).get('text', '')
                elif 'specificContent' in update:
                    share = update.get('specificContent', {}).get('com.linkedin.ugc.ShareContent', {})
                    content = share.get('shareCommentary', {}).get('text', '')
                
                # Get URN
                post_urn = update.get('urn', '') or update.get('entityUrn', '')
                
                # Get social counts
                social = update.get('socialDetail', {})
                if social:
                    counts = social.get('totalSocialActivityCounts', {})
                    likes = counts.get('numLikes', 0)
                    comments = counts.get('numComments', 0)
                
                if content or post_urn:
                    result.append(LinkedInPost(
                        post_id=post_urn,
                        author_name="Me",
                        author_urn=my_urn,
                        author_headline="",
                        content=content[:500] if content else "(media/share)",
                        timestamp=datetime.fromtimestamp(update.get('createdTime', 0) / 1000) if update.get('createdTime') else datetime.now(),
                        likes=likes,
                        comments=comments,
                        url=update.get('permalink')
                    ))
            
            return result
        except Exception as e:
            logger.error(f"Failed to get my posts: {e}")
            return []
    
    def get_post_comments(self, post_urn: str, limit: int = 20) -> list[dict]:
        """Get comments on a post."""
        self._ensure_connected()
        try:
            comments = self._api.get_post_comments(post_urn, comment_count=limit)
            result = []
            
            for comment in comments:
                commenter = comment.get('commenter', {})
                commenter_info = commenter.get('com.linkedin.voyager.feed.MemberActor', {})
                mini_profile = commenter_info.get('miniProfile', {})
                
                result.append({
                    'comment_id': comment.get('urn', ''),
                    'author_name': f"{mini_profile.get('firstName', '')} {mini_profile.get('lastName', '')}".strip() or commenter_info.get('name', 'Unknown'),
                    'author_urn': mini_profile.get('entityUrn', ''),
                    'content': comment.get('comment', {}).get('values', [{}])[0].get('value', '') if isinstance(comment.get('comment', {}).get('values'), list) else comment.get('commentV2', {}).get('text', ''),
                    'likes': comment.get('socialDetail', {}).get('totalSocialActivityCounts', {}).get('numLikes', 0),
                    'timestamp': datetime.fromtimestamp(comment.get('createdTime', 0) / 1000).isoformat() if comment.get('createdTime') else None
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get post comments: {e}")
            return []
    
    def reply_to_comment(self, post_urn: str, comment_urn: str, reply_text: str) -> bool:
        """Reply to a comment on a post."""
        self._ensure_connected()
        try:
            # The linkedin-api library may not have direct reply support
            # We'll use comment_on_post with parent reference if available
            self._api.comment_on_post(post_urn, reply_text, parent_comment_urn=comment_urn)
            logger.info(f"Replied to comment {comment_urn}")
            return True
        except TypeError:
            # If parent_comment_urn not supported, fall back to regular comment
            try:
                self._api.comment_on_post(post_urn, f"@reply: {reply_text}")
                logger.info(f"Posted reply as new comment (reply threading not supported)")
                return True
            except Exception as e:
                logger.error(f"Failed to reply to comment: {e}")
                return False
        except Exception as e:
            logger.error(f"Failed to reply to comment: {e}")
            return False
    
    # ==================== PROFILES ====================
    
    def get_profile(self, public_id: str) -> Optional[LinkedInProfile]:
        """Get a profile by public ID (the part after /in/)."""
        self._ensure_connected()
        try:
            profile = self._api.get_profile(public_id)
            return LinkedInProfile(
                urn=profile.get('entityUrn', ''),
                first_name=profile.get('firstName', ''),
                last_name=profile.get('lastName', ''),
                headline=profile.get('headline', ''),
                summary=profile.get('summary'),
                industry=profile.get('industryName'),
                location=profile.get('locationName'),
                profile_url=f"https://linkedin.com/in/{public_id}"
            )
        except Exception as e:
            logger.error(f"Failed to get profile {public_id}: {e}")
            return None
    
    def get_my_profile(self) -> Optional[LinkedInProfile]:
        """Get my own profile."""
        self._ensure_connected()
        try:
            profile = self._api.get_user_profile()
            return LinkedInProfile(
                urn=profile.get('entityUrn', ''),
                first_name=profile.get('firstName', ''),
                last_name=profile.get('lastName', ''),
                headline=profile.get('headline', ''),
                summary=profile.get('summary'),
                industry=profile.get('industryName'),
                location=profile.get('locationName'),
                profile_url=profile.get('publicIdentifier')
            )
        except Exception as e:
            logger.error(f"Failed to get my profile: {e}")
            return None
    
    def search_people(
        self, 
        keywords: str, 
        limit: int = 10,
        network_depth: Optional[str] = None  # 'F' = 1st, 'S' = 2nd, 'O' = 3rd+
    ) -> list[LinkedInProfile]:
        """Search for people on LinkedIn."""
        self._ensure_connected()
        try:
            results = self._api.search_people(
                keywords=keywords,
                limit=limit,
                network_depths=[network_depth] if network_depth else None
            )
            
            profiles = []
            for person in results:
                profiles.append(LinkedInProfile(
                    urn=person.get('urn_id', ''),
                    first_name=person.get('name', '').split()[0] if person.get('name') else '',
                    last_name=' '.join(person.get('name', '').split()[1:]) if person.get('name') else '',
                    headline=person.get('jobtitle', ''),
                    location=person.get('location', ''),
                    profile_url=f"https://linkedin.com/in/{person.get('public_id', '')}"
                ))
            
            return profiles
        except Exception as e:
            logger.error(f"Failed to search people: {e}")
            return []
