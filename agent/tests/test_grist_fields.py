"""Tests for Grist field formatting."""
from datetime import datetime, timezone, timedelta
from agent.integrations.grist import _format_datetime, _event_to_grist_fields


class TestFormatDatetime:
    def test_none_returns_none(self):
        assert _format_datetime(None) is None

    def test_naive_datetime(self):
        dt = datetime(2026, 3, 15, 19, 0, 0)
        result = _format_datetime(dt)
        assert result == "2026-03-15T19:00:00"

    def test_aware_datetime_strips_timezone(self):
        dt = datetime(2026, 3, 15, 19, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
        result = _format_datetime(dt)
        # Timezone should be stripped — Grist stores naive datetimes
        assert result == "2026-03-15T19:00:00"
        assert "+" not in result and "-07" not in result

    def test_utc_datetime_converts_to_pacific(self):
        # 2026-03-15 is during PDT (UTC-7), so 02:00 UTC = 19:00 PDT previous day
        dt = datetime(2026, 3, 16, 2, 0, 0, tzinfo=timezone.utc)
        result = _format_datetime(dt)
        assert result == "2026-03-15T19:00:00"


class TestEventToGristFields:
    def test_basic_fields(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        assert fields["Title"] == "Test Event"
        assert fields["Description"] == "A test event for unit testing"
        assert fields["SourceURL"] == "https://example.com/event"
        assert fields["Price"] == "$15"

    def test_location_fields(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        assert fields["Venue"] == "The Grand Theater"
        assert fields["Address"] == "123 Main St"
        assert fields["City"] == "Oakland"
        assert fields["LocationType"] == "physical"

    def test_organizer_field(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        assert fields["OrganizerName"] == "Test Org"

    def test_tags_joined(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        assert fields["Tags"] == "music, community"

    def test_none_values_excluded(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        # extraction_notes is None, should not be in output
        assert "extraction_notes" not in fields

    def test_created_at_present(self, sample_event):
        fields = _event_to_grist_fields(sample_event)
        assert "CreatedAt" in fields
        # Should be a valid ISO format string
        datetime.fromisoformat(fields["CreatedAt"])
