"""Integration test for the /scrape endpoint using a mock LLM extractor."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(sample_event):
    """Create a test client with mocked orchestrator."""
    # Mock the ScrapingOrchestrator so we don't need a browser or LLM
    with patch("agent.api.routes.ScrapingOrchestrator") as MockOrch:
        from agent.core.schemas import ScrapeResponse

        mock_instance = MagicMock()
        mock_instance.scrape_event = AsyncMock(
            return_value=ScrapeResponse(
                success=True,
                event=sample_event,
                metadata={"stage": "completed"},
            )
        )
        MockOrch.return_value = mock_instance

        from agent.main import app
        yield TestClient(app)


class TestScrapeEndpoint:
    def test_scrape_returns_200(self, client):
        response = client.post(
            "/scrape",
            json={"url": "https://example.com/event"},
        )
        assert response.status_code == 200

    def test_scrape_response_structure(self, client):
        response = client.post(
            "/scrape",
            json={"url": "https://example.com/event"},
        )
        data = response.json()
        assert "success" in data
        assert "event" in data
        assert data["success"] is True

    def test_scrape_event_fields(self, client):
        response = client.post(
            "/scrape",
            json={"url": "https://example.com/event"},
        )
        event = response.json()["event"]
        assert event["title"] == "Test Event"
        assert event["location"]["venue"] == "The Grand Theater"
        assert event["confidence_score"] == 0.9

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
