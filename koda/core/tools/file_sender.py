"""File sender tool for sending files through WhatsApp and other channels.

This tool allows the AI to send files, images, and documents to users
through their preferred communication channel (WhatsApp by default).
"""

from __future__ import annotations

import base64
import zipfile
import tempfile
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
- Send multiple files compressed as a zip archive

Actions:
- send_file: Send any file (documents, PDFs, audio, etc.)
- send_image: Send an image file (.jpg, .png, .gif, .webp)
- send_video: Send a video file (.mp4, .mov)
- send_zip: Compress and send multiple files as a single zip archive

Parameters:
- file_path: Path to the file to send (required for send_file/send_image/send_video)
- file_paths: List of paths to compress and send (for send_zip action)
- caption: Optional text to accompany the file
- recipient: Optional recipient (defaults to current chat)

Examples:
- "Send this image to the user"
- "Share the generated report.pdf"
- "Send multiple files as a zip"
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_file", "send_image", "send_video", "send_zip"],
                "description": "Type of send operation. Use send_zip to compress and send multiple files."
            },
            "file_path": {
                "type": "string",
                "description": "Path to the file to send (for send_file/send_image/send_video)"
            },
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to compress and send as zip (for send_zip action)"
            },
            "zip_name": {
                "type": "string",
                "description": "Name of the zip file (default: files.zip)"
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
        "required": ["action"]
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
        file_paths = kwargs.get("file_paths", [])
        caption = kwargs.get("caption", "")
        recipient = kwargs.get("recipient") or self._last_recipient
        zip_name = kwargs.get("zip_name", "files.zip")
        
        if not recipient:
            return "❌ Error: No recipient specified. Call set_recipient() first or provide recipient parameter."
        
        # Handle zip action
        if action == "send_zip":
            paths = file_paths or ([file_path] if file_path else [])
            if not paths:
                return "❌ Error: file_paths is required for send_zip action"
            return await self._send_zip(paths, zip_name, caption, recipient)
        
        # For single-file actions, file_path is required
        if not file_path:
            return "❌ Error: file_path is required"
        
        path = Path(file_path)
        if not path.exists():
            return f"❌ Error: File not found: {file_path}"
        
        try:
            # Auto-detect action based on file extension if action is send_file
            if action == "send_file" and self.is_image_file(path.name):
                action = "send_image"
            elif action == "send_file" and self.is_video_file(path.name):
                action = "send_video"
            
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
    
    async def _send_zip(self, file_paths: list, zip_name: str, caption: str, recipient: str) -> str:
        """Compress multiple files into a zip and send through WhatsApp."""
        if not self.whatsapp:
            return "❌ Error: WhatsApp channel not available"
        
        # Validate all paths exist
        paths = []
        for fp in file_paths:
            p = Path(fp)
            if not p.exists():
                return f"❌ Error: File not found: {fp}"
            if p.is_dir():
                # Add all files from directory
                for child in p.rglob("*"):
                    if child.is_file():
                        paths.append(child)
            else:
                paths.append(p)
        
        if not paths:
            return "❌ Error: No files to compress"
        
        try:
            # Create zip file in temp directory
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    zf.write(p, p.name)
            
            zip_data = tmp_path.read_bytes()
            zip_size_mb = len(zip_data) / (1024 * 1024)
            
            # Ensure zip_name ends with .zip
            if not zip_name.endswith(".zip"):
                zip_name += ".zip"
            
            await self.whatsapp.send_file(
                chat_id=recipient,
                file_data=zip_data,
                filename=zip_name,
                caption=caption or f"📦 {len(paths)} files ({zip_size_mb:.1f} MB)"
            )
            
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)
            
            file_list = ", ".join(p.name for p in paths[:5])
            if len(paths) > 5:
                file_list += f" (+{len(paths) - 5} more)"
            
            return f"✅ Sent zip '{zip_name}' with {len(paths)} files ({zip_size_mb:.1f} MB)\nFiles: {file_list}"
        except Exception as e:
            logger.error(f"Failed to send zip: {e}")
            return f"❌ Failed to send zip: {e}"
    
    async def send_generated_image(self, image_path: Path, prompt: str, recipient: str) -> str:
        """Send a generated image with a descriptive caption."""
        caption = f"🎨 Generated image:\n{prompt[:200]}{'...' if len(prompt) > 200 else ''}"
        return await self._send_image(image_path, caption, recipient)
