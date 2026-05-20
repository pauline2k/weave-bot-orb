"""Tests for timezone utilities."""
from datetime import datetime
from zoneinfo import ZoneInfo

from agent.core.time_utils import get_current_time, get_pacific_offset_str, PACIFIC


class TestGetCurrentTime:
    def test_returns_aware_datetime(self):
        now = get_current_time()
        assert now.tzinfo is not None

    def test_uses_pacific_timezone(self):
        now = get_current_time()
        assert now.tzinfo == PACIFIC

    def test_is_recent(self):
        """Returned time should be within a few seconds of now."""
        now = get_current_time()
        utc_now = datetime.now(ZoneInfo("UTC"))
        diff = abs((utc_now - now).total_seconds())
        assert diff < 5


class TestGetPacificOffsetStr:
    def test_format(self):
        offset = get_pacific_offset_str()
        # Should be either -08:00 (PST) or -07:00 (PDT)
        assert offset in ("-08:00", "-07:00")

    def test_colon_in_offset(self):
        offset = get_pacific_offset_str()
        assert ":" in offset
