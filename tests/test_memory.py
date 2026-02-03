"""Tests for memory systems."""

import pytest
from pathlib import Path

from koda.core.memory import MemoryStore


class TestMemoryStore:
    """Test file-based memory store."""
    
    @pytest.fixture
    def memory_store(self, temp_workspace):
        """Create a memory store with temp workspace."""
        return MemoryStore(temp_workspace)
    
    def test_memory_dir_creation(self, temp_workspace):
        """Test that memory directory is created."""
        store = MemoryStore(temp_workspace)
        assert (temp_workspace / "memory").exists()
    
    def test_get_memory_context_empty(self, memory_store):
        """Test getting memory context when empty."""
        context = memory_store.get_memory_context()
        # Should return empty or minimal context
        assert context is not None
    
    def test_get_todays_notes_empty(self, memory_store):
        """Test getting today's notes when none exist."""
        notes = memory_store.read_today()
        assert notes == ""
    
    def test_append_to_memory(self, memory_store):
        """Test appending to today's memory."""
        test_content = "Test memory content"
        memory_store.append_today(test_content)
        
        today_file = memory_store.get_today_file()
        assert today_file.exists()
        assert test_content in today_file.read_text()
    
    def test_memory_file_path(self, memory_store, temp_workspace):
        """Test memory file path is correct."""
        assert memory_store.memory_file == temp_workspace / "memory" / "MEMORY.md"
