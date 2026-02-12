"""Tests for CalendarSyncService."""

import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from koda.services.calendar_sync import CalendarSyncService, CachedEvent, SyncState


class TestCalendarSyncService:
    """Test calendar sync service functionality."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sync_service(self, temp_cache_dir):
        """Create a sync service with temporary cache."""
        return CalendarSyncService(
            cache_dir=temp_cache_dir,
            sync_interval=60,
            lookahead_days=14,
            lookbehind_days=3,
        )

    def test_init_creates_cache_dir(self, temp_cache_dir):
        """Test that init creates the cache directory."""
        cache_dir = temp_cache_dir / "subcache"
        service = CalendarSyncService(cache_dir=cache_dir)
        assert cache_dir.exists()

    def test_set_accounts(self, sync_service):
        """Test setting calendar accounts."""
        accounts = [
            {"name": "Work", "type": "google_workspace", "calendar_id": "primary"},
            {"name": "Personal", "type": "exchange", "email": "me@example.com"},
        ]
        sync_service.set_accounts(accounts)
        assert len(sync_service._calendar_accounts) == 2

    def test_get_events_empty(self, sync_service):
        """Test getting events when cache is empty."""
        events = sync_service.get_events()
        assert events == []

    def test_get_events_with_cache(self, sync_service):
        """Test getting events from cache."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="Meeting",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
            CachedEvent(
                id="2",
                account_name="Work",
                account_type="google",
                summary="Old Event",
                start=(now - timedelta(days=30)).isoformat(),
                end=(now - timedelta(days=30, hours=-1)).isoformat(),
            ),
        ]

        events = sync_service.get_events()
        # Should only return the future event, not the old one
        assert len(events) == 1
        assert events[0]["summary"] == "Meeting"

    def test_get_events_filter_by_account(self, sync_service):
        """Test filtering events by account name."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="Work Meeting",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
            CachedEvent(
                id="2",
                account_name="Personal",
                account_type="exchange",
                summary="Dentist",
                start=(now + timedelta(hours=3)).isoformat(),
                end=(now + timedelta(hours=4)).isoformat(),
            ),
        ]

        work_events = sync_service.get_events(account_name="Work")
        assert len(work_events) == 1
        assert work_events[0]["summary"] == "Work Meeting"

        personal_events = sync_service.get_events(account_name="Personal")
        assert len(personal_events) == 1
        assert personal_events[0]["summary"] == "Dentist"

    def test_get_today_events(self, sync_service):
        """Test getting today's events."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="Today Meeting",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
            CachedEvent(
                id="2",
                account_name="Work",
                account_type="google",
                summary="Tomorrow Meeting",
                start=(now + timedelta(days=2)).isoformat(),
                end=(now + timedelta(days=2, hours=1)).isoformat(),
            ),
        ]

        today = sync_service.get_today_events()
        assert len(today) == 1
        assert today[0]["summary"] == "Today Meeting"

    def test_get_upcoming_events(self, sync_service):
        """Test getting upcoming events within N hours."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="Soon",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
            CachedEvent(
                id="2",
                account_name="Work",
                account_type="google",
                summary="Later",
                start=(now + timedelta(hours=25)).isoformat(),
                end=(now + timedelta(hours=26)).isoformat(),
            ),
        ]

        upcoming = sync_service.get_upcoming_events(hours=4)
        assert len(upcoming) == 1
        assert upcoming[0]["summary"] == "Soon"

    def test_get_sync_status(self, sync_service):
        """Test getting sync status."""
        status = sync_service.get_sync_status()
        assert status["total_events"] == 0
        assert status["sync_interval_seconds"] == 60
        assert status["lookahead_days"] == 14

    def test_save_and_load_cache(self, sync_service):
        """Test persisting and loading cache."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="Persisted Event",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
        ]

        sync_service._save_cache()
        assert sync_service.cache_file.exists()

        # Load into a new service
        new_service = CalendarSyncService(cache_dir=sync_service.cache_dir)
        assert len(new_service._events) == 1
        assert new_service._events[0].summary == "Persisted Event"

    def test_get_account_names(self, sync_service):
        """Test getting unique account names from cached events."""
        sync_service._events = [
            CachedEvent(id="1", account_name="Work", account_type="google", summary="A"),
            CachedEvent(id="2", account_name="Work", account_type="google", summary="B"),
            CachedEvent(id="3", account_name="Personal", account_type="exchange", summary="C"),
        ]

        names = sync_service.get_account_names()
        assert set(names) == {"Work", "Personal"}

    def test_events_sorted_by_start(self, sync_service):
        """Test that returned events are sorted by start time."""
        now = datetime.now(timezone.utc)
        sync_service._events = [
            CachedEvent(
                id="2",
                account_name="Work",
                account_type="google",
                summary="Second",
                start=(now + timedelta(hours=3)).isoformat(),
                end=(now + timedelta(hours=4)).isoformat(),
            ),
            CachedEvent(
                id="1",
                account_name="Work",
                account_type="google",
                summary="First",
                start=(now + timedelta(hours=1)).isoformat(),
                end=(now + timedelta(hours=2)).isoformat(),
            ),
        ]

        events = sync_service.get_events()
        assert events[0]["summary"] == "First"
        assert events[1]["summary"] == "Second"


class TestCachedEvent:
    """Test CachedEvent dataclass."""

    def test_defaults(self):
        """Test default values."""
        event = CachedEvent(id="1", account_name="Test", account_type="google")
        assert event.summary == ""
        assert event.all_day is False
        assert event.is_recurring is False
        assert event.attendees == []

    def test_all_fields(self):
        """Test all fields set."""
        event = CachedEvent(
            id="1",
            account_name="Work",
            account_type="google",
            calendar_id="primary",
            calendar_name="Work Calendar",
            summary="Meeting",
            description="Important",
            location="Office",
            start="2024-01-15T10:00:00+00:00",
            end="2024-01-15T11:00:00+00:00",
            all_day=False,
            is_recurring=True,
            is_shared=False,
            meet_link="https://meet.google.com/abc",
            attendees=["a@b.com"],
            organizer="org@b.com",
            status="confirmed",
        )
        assert event.summary == "Meeting"
        assert event.is_recurring is True
        assert event.meet_link == "https://meet.google.com/abc"
