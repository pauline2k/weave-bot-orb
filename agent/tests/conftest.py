"""Test fixtures for agent tests."""
import os
import pytest

from agent.core.schemas import Event, EventLocation, EventOrganizer


# Ensure test env vars are set before Settings is imported
os.environ.setdefault("GEMINI_API_KEY", "test-key")


@pytest.fixture
def sample_event():
    """A fully-populated Event for testing."""
    return Event(
        title="Test Event",
        description="A test event for unit testing",
        start_datetime="2026-03-15T19:00:00-07:00",
        end_datetime="2026-03-15T21:00:00-07:00",
        timezone="America/Los_Angeles",
        location=EventLocation(
            type="physical",
            venue="The Grand Theater",
            address="123 Main St",
            city="Oakland",
        ),
        organizer=EventOrganizer(
            name="Test Org",
        ),
        price="$15",
        tags=["music", "community"],
        image_url="https://example.com/image.jpg",
        source_url="https://example.com/event",
        confidence_score=0.9,
        extraction_notes=None,
    )


@pytest.fixture
def sample_json_ld():
    """Sample JSON-LD event data as extracted from a webpage."""
    return {
        "@type": "Event",
        "name": "JSON-LD Event",
        "startDate": "2026-04-10T18:30:00-07:00",
        "endDate": "2026-04-10T21:00:00-07:00",
        "location": {
            "@type": "Place",
            "name": "Berkeley Art Museum",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "2155 Center St",
                "addressLocality": "Berkeley",
                "addressRegion": "CA",
            }
        },
        "organizer": {
            "@type": "Organization",
            "name": "BAMPFA",
        },
    }


