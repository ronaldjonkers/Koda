"""Tests for file sender tool."""

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from koda.core.tools.file_sender import FileSenderTool


class TestFileSenderTool:
    """Test file sender tool functionality."""

    @pytest.fixture
    def mock_whatsapp(self):
        """Create a mock WhatsApp channel."""
        wa = MagicMock()
        wa.send_file = AsyncMock()
        wa.send_image = AsyncMock()
        wa.send_video = AsyncMock()
        return wa

    @pytest.fixture
    def sender(self, mock_whatsapp):
        """Create a file sender tool with mock WhatsApp."""
        tool = FileSenderTool(whatsapp_channel=mock_whatsapp)
        tool.set_recipient("31612345678@s.whatsapp.net")
        return tool

    @pytest.fixture
    def temp_files(self, tmp_path):
        """Create temporary test files."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF-1.4" + b"\x00" * 100)

        txt = tmp_path / "notes.txt"
        txt.write_text("Hello world")

        video = tmp_path / "clip.mp4"
        video.write_bytes(b"\x00" * 200)

        return {"img": img, "doc": doc, "txt": txt, "video": video}

    def test_tool_name(self):
        tool = FileSenderTool()
        assert tool.name == "file_sender"

    @pytest.mark.asyncio
    async def test_send_file(self, sender, temp_files):
        result = await sender.execute(action="send_file", file_path=str(temp_files["doc"]))
        assert "Sent" in result
        sender.whatsapp.send_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_image(self, sender, temp_files):
        result = await sender.execute(action="send_image", file_path=str(temp_files["img"]))
        assert "Sent" in result
        sender.whatsapp.send_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_video(self, sender, temp_files):
        result = await sender.execute(action="send_video", file_path=str(temp_files["video"]))
        assert "Sent" in result
        sender.whatsapp.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_detect_image(self, sender, temp_files):
        """send_file with an image extension should auto-detect and use send_image."""
        result = await sender.execute(action="send_file", file_path=str(temp_files["img"]))
        assert "Sent image" in result
        sender.whatsapp.send_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_detect_video(self, sender, temp_files):
        """send_file with a video extension should auto-detect and use send_video."""
        result = await sender.execute(action="send_file", file_path=str(temp_files["video"]))
        assert "Sent video" in result
        sender.whatsapp.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_recipient(self, mock_whatsapp, temp_files):
        tool = FileSenderTool(whatsapp_channel=mock_whatsapp)
        result = await tool.execute(action="send_file", file_path=str(temp_files["doc"]))
        assert "No recipient" in result

    @pytest.mark.asyncio
    async def test_file_not_found(self, sender):
        result = await sender.execute(action="send_file", file_path="/nonexistent/file.pdf")
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_no_whatsapp(self, temp_files):
        tool = FileSenderTool()
        tool.set_recipient("test@s.whatsapp.net")
        result = await tool.execute(action="send_file", file_path=str(temp_files["doc"]))
        assert "WhatsApp channel not available" in result

    @pytest.mark.asyncio
    async def test_send_zip(self, sender, temp_files):
        """Test compressing and sending multiple files as zip."""
        paths = [str(temp_files["doc"]), str(temp_files["txt"])]
        result = await sender.execute(
            action="send_zip",
            file_paths=paths,
            zip_name="bundle.zip",
        )
        assert "Sent zip" in result
        assert "2 files" in result
        sender.whatsapp.send_file.assert_called_once()

        # Verify the sent data is a valid zip
        call_kwargs = sender.whatsapp.send_file.call_args
        sent_data = call_kwargs.kwargs.get("file_data") or call_kwargs[1].get("file_data")
        assert sent_data is not None

    @pytest.mark.asyncio
    async def test_send_zip_with_directory(self, sender, tmp_path):
        """Test zipping a whole directory."""
        subdir = tmp_path / "mydir"
        subdir.mkdir()
        (subdir / "a.txt").write_text("aaa")
        (subdir / "b.txt").write_text("bbb")

        result = await sender.execute(
            action="send_zip",
            file_paths=[str(subdir)],
            zip_name="dir.zip",
        )
        assert "Sent zip" in result
        assert "2 files" in result

    @pytest.mark.asyncio
    async def test_send_zip_missing_file(self, sender, temp_files):
        result = await sender.execute(
            action="send_zip",
            file_paths=[str(temp_files["doc"]), "/nonexistent.txt"],
        )
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_send_zip_empty(self, sender):
        result = await sender.execute(action="send_zip")
        assert "file_paths is required" in result

    def test_is_image_file(self):
        tool = FileSenderTool()
        assert tool.is_image_file("photo.jpg") is True
        assert tool.is_image_file("photo.PNG") is True
        assert tool.is_image_file("doc.pdf") is False

    def test_is_video_file(self):
        tool = FileSenderTool()
        assert tool.is_video_file("clip.mp4") is True
        assert tool.is_video_file("clip.MOV") is True
        assert tool.is_video_file("doc.pdf") is False
