"""Tests for unified calendar tool."""

import pytest
from datetime import datetime, timedelta

from koda.core.tools.unified_calendar import UnifiedCalendarTool


class TestUnifiedCalendarTool:
    """Test unified calendar tool functionality."""
    
    @pytest.fixture
    def empty_calendar_tool(self):
        """Create calendar tool with no accounts."""
        return UnifiedCalendarTool()
    
    @pytest.fixture
    def multi_account_tool(self):
        """Create calendar tool with multiple named accounts."""
        return UnifiedCalendarTool(
            calendar_accounts=[
                {"name": "Werk", "type": "google", "credentials_file": "~/.koda/google.json"},
                {"name": "Privé", "type": "exchange", "email": "test@example.com"},
                {"name": "Familie", "type": "caldav", "url": "https://cal.example.com"}
            ]
        )
    
    def test_tool_name(self, empty_calendar_tool):
        """Test tool has correct name."""
        assert empty_calendar_tool.name == "calendar"
    
    def test_get_account_names_empty(self, empty_calendar_tool):
        """Test getting account names when empty."""
        names = empty_calendar_tool._get_account_names()
        assert names == []
    
    def test_get_account_names_multiple(self, multi_account_tool):
        """Test getting account names with multiple accounts."""
        names = multi_account_tool._get_account_names()
        assert "Werk" in names
        assert "Privé" in names
        assert "Familie" in names
        assert len(names) == 3
    
    def test_get_account_by_name_found(self, multi_account_tool):
        """Test finding account by name."""
        account = multi_account_tool._get_account_by_name("Werk")
        assert account is not None
        assert account["name"] == "Werk"
        assert account["type"] == "google"
    
    def test_get_account_by_name_case_insensitive(self, multi_account_tool):
        """Test that account lookup is case-insensitive."""
        account = multi_account_tool._get_account_by_name("werk")
        assert account is not None
        assert account["name"] == "Werk"
        
        account = multi_account_tool._get_account_by_name("WERK")
        assert account is not None
    
    def test_get_account_by_name_not_found(self, multi_account_tool):
        """Test account not found returns None."""
        account = multi_account_tool._get_account_by_name("NonExistent")
        assert account is None
    
    def test_legacy_compatibility(self):
        """Test backward compatibility with legacy parameters."""
        tool = UnifiedCalendarTool(
            google_enabled=True,
            google_credentials_file="~/.koda/creds.json",
            google_token_file="~/.koda/token.json"
        )
        # Should convert legacy params to named account
        assert len(tool.calendar_accounts) == 1
        assert tool.calendar_accounts[0]["name"] == "Google"
        assert tool.calendar_accounts[0]["type"] == "google"
    
    @pytest.mark.asyncio
    async def test_list_calendars_empty(self, empty_calendar_tool):
        """Test listing calendars when none configured."""
        result = await empty_calendar_tool._list_calendars()
        assert "No calendars configured" in result
    
    @pytest.mark.asyncio
    async def test_list_calendars_with_accounts(self, multi_account_tool):
        """Test listing calendars shows account names."""
        result = await multi_account_tool._list_calendars()
        assert "Werk" in result
        assert "Privé" in result
        assert "Familie" in result
        assert "Google" in result
        assert "Exchange" in result
        assert "CalDAV" in result
    
    @pytest.mark.asyncio
    async def test_create_event_no_calendars(self, empty_calendar_tool):
        """Test creating event with no calendars configured."""
        result = await empty_calendar_tool._create_event(
            summary="Test Meeting",
            start="2024-01-15T10:00:00",
            end="2024-01-15T11:00:00"
        )
        assert "No calendar accounts configured" in result or "No calendar" in result
    
    @pytest.mark.asyncio
    async def test_create_event_multiple_calendars_prompts(self, multi_account_tool):
        """Test that create event prompts for calendar when multiple available."""
        result = await multi_account_tool._create_event(
            summary="Test Meeting",
            start="2024-01-15T10:00:00",
            end="2024-01-15T11:00:00"
            # No calendar specified
        )
        assert "Which calendar" in result or "calendar" in result.lower()
        assert "Werk" in result
        assert "Privé" in result
    
    @pytest.mark.asyncio
    async def test_create_event_invalid_calendar(self, multi_account_tool):
        """Test error when specifying non-existent calendar."""
        result = await multi_account_tool._create_event(
            summary="Test Meeting",
            start="2024-01-15T10:00:00",
            end="2024-01-15T11:00:00",
            calendar="NonExistent"
        )
        assert "not found" in result
    
    @pytest.mark.asyncio
    async def test_create_event_missing_fields(self, multi_account_tool):
        """Test validation of required fields."""
        # Missing summary
        result = await multi_account_tool._create_event(
            start="2024-01-15T10:00:00",
            end="2024-01-15T11:00:00"
        )
        assert "summary" in result.lower() and "required" in result.lower()
        
        # Missing start
        result = await multi_account_tool._create_event(
            summary="Test",
            end="2024-01-15T11:00:00"
        )
        assert "start" in result.lower() and "required" in result.lower()
