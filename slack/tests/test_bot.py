"""Tests for Slack bot message formatting."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock config before importing bot
with patch.dict("os.environ", {
    "SLACK_BOT_TOKEN": "test-token",
    "SLACK_APP_TOKEN": "test-app-token",
    "SLACK_CHANNELS": "C123",
    "ORG_ID": "test-org",
}):
    from src.bot import SlackEventBot


class TestFormatEventReply:
    """Test Slack message formatting."""

    def setup_method(self):
        mock_app = MagicMock()
        with patch.dict("os.environ", {
            "SLACK_BOT_TOKEN": "test-token",
            "SLACK_APP_TOKEN": "test-app-token",
            "SLACK_CHANNELS": "C123",
            "ORG_ID": "test-org",
        }):
            self.bot = SlackEventBot(mock_app)

    def test_basic_event(self):
        event = {"title": "Test Event", "confidence_score": 0.9}
        result = self.bot._format_event_reply(event)
        assert "*Test Event*" in result

    def test_event_with_location(self):
        event = {
            "title": "Concert",
            "location": {"venue": "The Grand", "address": "123 Main St"},
            "confidence_score": 0.9,
        }
        result = self.bot._format_event_reply(event)
        assert "The Grand" in result
        assert "123 Main St" in result

    def test_event_with_result_url(self):
        event = {"title": "Event", "confidence_score": 0.9}
        result = self.bot._format_event_reply(event, result_url="https://grist.example.com/123")
        assert "https://grist.example.com/123" in result

    def test_low_confidence_note(self):
        event = {"title": "Unclear Event", "confidence_score": 0.5}
        result = self.bot._format_event_reply(event)
        assert "incomplete" in result.lower()

    def test_long_description_truncated(self):
        event = {"title": "Event", "description": "x" * 300, "confidence_score": 0.9}
        result = self.bot._format_event_reply(event)
        assert "..." in result
        assert len(result) < 400

    def test_event_with_datetime(self):
        event = {"title": "Event", "start_datetime": "2026-03-15T19:00:00-07:00"}
        result = self.bot._format_event_reply(event)
        assert "2026-03-15" in result

    def test_event_with_price(self):
        event = {"title": "Event", "price": "$15"}
        result = self.bot._format_event_reply(event)
        assert "$15" in result
