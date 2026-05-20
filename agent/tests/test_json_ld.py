"""Tests for JSON-LD override logic (dates, venue, address, organizer)."""
from datetime import datetime
from agent.core.schemas import Event, EventLocation, EventOrganizer
from agent.scraper.orchestrator import ScrapingOrchestrator


class TestApplyJsonLdOverrides:
    def setup_method(self):
        # Access the method directly — it's a pure function on self
        self.orchestrator = ScrapingOrchestrator.__new__(ScrapingOrchestrator)

    # --- Date overrides (existing) ---

    def test_overrides_start_date(self, sample_event):
        json_ld = {"startDate": "2026-06-01T20:00:00-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert str(result.start_datetime) == "2026-06-01 20:00:00-07:00"

    def test_overrides_end_date(self, sample_event):
        json_ld = {"endDate": "2026-06-01T23:00:00-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert str(result.end_datetime) == "2026-06-01 23:00:00-07:00"

    def test_overrides_both_dates(self, sample_event):
        json_ld = {
            "startDate": "2026-06-01T20:00:00-07:00",
            "endDate": "2026-06-01T23:00:00-07:00",
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert str(result.start_datetime) == "2026-06-01 20:00:00-07:00"
        assert str(result.end_datetime) == "2026-06-01 23:00:00-07:00"

    def test_cleans_milliseconds(self, sample_event):
        json_ld = {"startDate": "2026-06-01T20:00:00.000-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert str(result.start_datetime) == "2026-06-01 20:00:00-07:00"

    def test_adds_extraction_note_for_dates(self, sample_event):
        json_ld = {"startDate": "2026-06-01T20:00:00-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert "JSON-LD overrides: dates" in result.extraction_notes

    def test_preserves_existing_notes(self):
        event = Event(
            title="Test",
            extraction_notes="Existing note.",
        )
        json_ld = {"startDate": "2026-06-01T20:00:00-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(event, json_ld)
        assert "Existing note." in result.extraction_notes
        assert "JSON-LD" in result.extraction_notes

    def test_no_override_without_json_ld_fields(self, sample_event):
        json_ld = {"name": "Some Event"}  # No overrideable fields
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.start_datetime == sample_event.start_datetime
        assert result.end_datetime == sample_event.end_datetime
        assert result.extraction_notes is None  # No override note added

    # --- Venue overrides ---

    def test_overrides_venue_from_location_name(self, sample_event):
        json_ld = {
            "location": {"@type": "Place", "name": "Berkeley Art Museum"},
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.venue == "Berkeley Art Museum"
        assert "venue" in result.extraction_notes

    def test_skips_empty_venue_name(self, sample_event):
        json_ld = {
            "location": {"@type": "Place", "name": ""},
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.venue == sample_event.location.venue

    def test_skips_single_char_venue(self, sample_event):
        json_ld = {
            "location": {"@type": "Place", "name": "-"},
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.venue == sample_event.location.venue

    # --- Address overrides ---

    def test_overrides_address_from_postal_address(self, sample_event):
        json_ld = {
            "location": {
                "@type": "Place",
                "name": "BAMPFA",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "2155 Center St",
                    "addressLocality": "Berkeley",
                    "addressRegion": "CA",
                },
            },
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.address == "2155 Center St, Berkeley, CA"
        assert "address" in result.extraction_notes

    def test_overrides_address_from_plain_string(self, sample_event):
        json_ld = {
            "location": {
                "@type": "Place",
                "address": "2155 Center St, Berkeley, CA",
            },
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.address == "2155 Center St, Berkeley, CA"

    def test_handles_partial_postal_address(self, sample_event):
        json_ld = {
            "location": {
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Oakland",
                },
            },
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.address == "Oakland"

    # --- Organizer overrides ---

    def test_overrides_organizer_name(self, sample_event):
        json_ld = {
            "organizer": {"@type": "Organization", "name": "BAMPFA"},
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.organizer.name == "BAMPFA"
        assert "organizer" in result.extraction_notes

    def test_skips_empty_organizer(self, sample_event):
        json_ld = {
            "organizer": {"@type": "Organization", "name": ""},
        }
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.organizer.name == sample_event.organizer.name

    # --- Combined overrides ---

    def test_full_eventbrite_json_ld(self, sample_json_ld):
        """Simulate a full Eventbrite-style JSON-LD with all fields."""
        event = Event(title="LLM Title", confidence_score=0.8)
        result = self.orchestrator._apply_json_ld_overrides(event, sample_json_ld)
        assert str(result.start_datetime) == "2026-04-10 18:30:00-07:00"
        assert result.location.venue == "Berkeley Art Museum"
        assert result.location.address == "2155 Center St, Berkeley, CA"
        assert result.organizer.name == "BAMPFA"
        assert "dates" in result.extraction_notes
        assert "venue" in result.extraction_notes
        assert "address" in result.extraction_notes
        assert "organizer" in result.extraction_notes

    def test_creates_location_when_none(self):
        """Events without location get one created from JSON-LD."""
        event = Event(title="No Location Event", confidence_score=0.8)
        json_ld = {
            "location": {
                "@type": "Place",
                "name": "The Grand",
                "address": "100 Broadway, Oakland, CA",
            },
        }
        result = self.orchestrator._apply_json_ld_overrides(event, json_ld)
        assert result.location.venue == "The Grand"
        assert result.location.address == "100 Broadway, Oakland, CA"

    def test_creates_organizer_when_none(self):
        """Events without organizer get one created from JSON-LD."""
        event = Event(title="No Org Event", confidence_score=0.8)
        json_ld = {
            "organizer": {"@type": "Organization", "name": "ORB"},
        }
        result = self.orchestrator._apply_json_ld_overrides(event, json_ld)
        assert result.organizer.name == "ORB"

    def test_no_json_ld_location_leaves_event_unchanged(self, sample_event):
        """Sites without JSON-LD location don't affect existing data."""
        json_ld = {"startDate": "2026-06-01T20:00:00-07:00"}
        result = self.orchestrator._apply_json_ld_overrides(sample_event, json_ld)
        assert result.location.venue == sample_event.location.venue
        assert result.location.address == sample_event.location.address
