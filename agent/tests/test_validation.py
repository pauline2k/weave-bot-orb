"""Tests for post-extraction event validation."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from agent.core.schemas import Event
from agent.core.validation import validate_event

PACIFIC = ZoneInfo("America/Los_Angeles")


class TestValidateEvent:
    def test_valid_event_unchanged(self, sample_event):
        result = validate_event(sample_event)
        assert result.title == sample_event.title
        assert result.confidence_score == sample_event.confidence_score

    def test_missing_title_lowers_confidence(self):
        event = Event(title="", confidence_score=0.8)
        result = validate_event(event)
        assert result.confidence_score < 0.8
        assert "Missing or failed title" in result.extraction_notes

    def test_extraction_failed_title_lowers_confidence(self):
        event = Event(title="Extraction Failed", confidence_score=0.8)
        result = validate_event(event)
        assert result.confidence_score < 0.8
        assert "failed title" in result.extraction_notes

    def test_start_date_far_in_past(self):
        two_years_ago = datetime.now(PACIFIC) - timedelta(days=400)
        event = Event(
            title="Old Event",
            start_datetime=two_years_ago,
            confidence_score=0.8,
        )
        result = validate_event(event)
        assert result.confidence_score < 0.8
        assert "past" in result.extraction_notes

    def test_start_date_far_in_future(self):
        three_years_ahead = datetime.now(PACIFIC) + timedelta(days=1100)
        event = Event(
            title="Future Event",
            start_datetime=three_years_ahead,
            confidence_score=0.8,
        )
        result = validate_event(event)
        assert result.confidence_score < 0.8
        assert "future" in result.extraction_notes

    def test_end_before_start_nulls_end(self):
        start = datetime(2026, 6, 1, 20, 0, tzinfo=PACIFIC)
        end = datetime(2026, 6, 1, 18, 0, tzinfo=PACIFIC)  # Before start
        event = Event(
            title="Bad End Time",
            start_datetime=start,
            end_datetime=end,
            confidence_score=0.9,
        )
        result = validate_event(event)
        assert result.end_datetime is None
        assert "before start" in result.extraction_notes

    def test_valid_date_range_preserved(self):
        start = datetime(2026, 6, 1, 18, 0, tzinfo=PACIFIC)
        end = datetime(2026, 6, 1, 21, 0, tzinfo=PACIFIC)
        event = Event(
            title="Good Event",
            start_datetime=start,
            end_datetime=end,
            confidence_score=0.9,
        )
        result = validate_event(event)
        assert result.end_datetime == end
        assert result.confidence_score == 0.9

    def test_no_dates_passes_validation(self):
        event = Event(title="No Dates", confidence_score=0.7)
        result = validate_event(event)
        assert result.confidence_score == 0.7

    def test_preserves_existing_extraction_notes(self):
        event = Event(
            title="",
            extraction_notes="Previous note.",
            confidence_score=0.8,
        )
        result = validate_event(event)
        assert "Previous note." in result.extraction_notes
        assert "Validation:" in result.extraction_notes

    def test_confidence_never_below_zero(self):
        event = Event(
            title="Extraction Failed",
            start_datetime=datetime(2020, 1, 1, tzinfo=PACIFIC),
            confidence_score=0.1,
        )
        result = validate_event(event)
        assert result.confidence_score >= 0.0
