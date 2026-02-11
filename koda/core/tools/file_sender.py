"""File sender tool for sending files through WhatsApp and other channels.

This tool allows the AI to send files, images, and documents to users
through their preferred communication channel (WhatsApp by default).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from koda.core.tools.base import BaseTool


class FileSenderTool(BaseTool):
    """
    Send files, images, and documents to users through WhatsApp or other channels.
    
    Use this tool when:
    - You need to send a generated image to the user
    - You need to send a document or file you created
    - You want to share results as a file rather than text
    - You generated a chart, diagram, or visualization
    
    Supported file types:
    - Images: .jpg, .jpeg, .png, .gif, .webp
    - Documents: .pdf, .doc, .docx, .txt
    - Videos: .mp4, .mov
    - Audio: .mp3, .ogg, .m4a
    
    Examples:
    - "Send this image to the user"
    - "Share the generated report"
    - "Send the chart I created"
    """
    
    name = "file_sender"
    description = """Send files, images, and documents to users through WhatsApp.

Use this to:
- Send generated images to the user
- Share documents or files you've created
- Send charts, diagrams, or visualizations
- Share any file the user requested

Parameters:
- file_path: Path to the file to send (required)
- caption: Optional text to accompany the file
- recipient: Optional recipient (defaults to current chat)

Examples:
- "Send this image to the user"
- "Share the generated report.pdf"
- "Send the chart I created"
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_file", "send_image", "send_video"],
                "description": "Type of send operation"
            },
            "file_path": {
                "type": "string",
                "description": "Path to the file to send"
            },
            "caption": {
                "type": "string",
                "description": "Optional caption or message to accompany the file"
            },
            "recipient": {
                "type": "string",
                "description": "Optional recipient identifier (defaults to current chat)"
            }
        },
        "required": ["action", "file_path"]
    }
    
    def __init__(self, whatsapp_channel=None):
        self.whatsapp = whatsapp_channel
        self._last_recipient: Optional[str] = None
    
    def set_recipient(self, chat_id: str) -> None:
        """Set the default recipient for file sending."""
        self._last_recipient = chat_id
    
    async def execute(self, **kwargs) -> str:
        """Execute file sending action."""
        action = kwargs.get("action", "send_file")
        file_path = kwargs.get("file_path", "")
        caption = kwargs.get("caption", "")
        recipient = kwargs.get("recipient") or self._last_recipient
        
        if not file_path:
            return "❌ Error: file_path is required"
        
        path = Path(file_path)
        if not path.exists():
            return f"❌ Error: File not found: {file_path}"
        
        if not recipient:
            return "❌ Error: No recipient specified. Call set_recipient() first or provide recipient parameter."
        
        try:
            if action == "send_image":
                return await self._send_image(path, caption, recipient)
            elif action == "send_video":
                return await self._send_video(path, caption, recipient)
            else:
                return await self._send_file(path, caption, recipient)
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            return f"❌ Error sending file: {e}"
    
    async def _send_file(self, path: Path, caption: str, recipient: str) -> str:
        """Send a file through WhatsApp."""
        if not self.whatsapp:
            return "❌ Error: WhatsApp channel not available"
        
        try:
            file_data = path.read_bytes()
            await self.whatsapp.send_file(
                chat_id=recipient,
                file_data=file_data,
                filename=path.name,
                caption=caption or None
            )
            return f"✅ Sent file '{path.name}' to recipient"
        except Exception as e:
            logger.error(f"Failed to send file: {e}")
            return f"❌ Failed to send file: {e}"
    
    async def _send_image(self, path: Path, caption: str, recipient: str) -> str:
        """Send an image through WhatsApp."""
        if not self.whatsapp:
            return "❌ Error: WhatsApp channel not available"
        
        try:
            image_data = path.read_bytes()
            await self.whatsapp.send_image(
                chat_id=recipient,
                image_data=image_data,
                caption=caption or None
            )
            return f"✅ Sent image '{path.name}' to recipient"
        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            return f"❌ Failed to send image: {e}"
    
    async def _send_video(self, path: Path, caption: str, recipient: str) -> str:
        """Send a video through WhatsApp."""
        if not self.whatsapp:
            return "❌ Error: WhatsApp channel not available"
        
        try:
            video_data = path.read_bytes()
            await self.whatsapp.send_video(
                chat_id=recipient,
                video_data=video_data,
                caption=caption or None
            )
            return f"✅ Sent video '{path.name}' to recipient"
        except Exception as e:
            logger.error(f"Failed to send video: {e}")
            return f"❌ Failed to send video: {e}"
    
    def is_image_file(self, filename: str) -> bool:
        """Check if a file is an image."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        return Path(filename).suffix.lower() in image_extensions
    
    def is_video_file(self, filename: str) -> bool:
        """Check if a file is a video."""
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
        return Path(filename).suffix.lower() in video_extensions
    
    async def send_generated_image(self, image_path: Path, prompt: str, recipient: str) -> str:
        """Send a generated image with a descriptive caption."""
        caption = f"🎨 Generated image:\n{prompt[:200]}{'...' if len(prompt) > 200 else ''}"
        return await self._send_image(image_path, caption, recipient)
