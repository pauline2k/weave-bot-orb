"""Tests for OpenAI-compatible LLM extractor."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.llm.openai_compat import OpenAICompatExtractor
from agent.core.schemas import Event


@pytest.fixture
def extractor():
    """Create an extractor with mocked client."""
    with patch("agent.llm.openai_compat.AsyncOpenAI"):
        ext = OpenAICompatExtractor(
            api_key="test-key",
            model="test-model",
            endpoint_url="https://example.com/v1",
            timezone="America/Los_Angeles",
        )
    return ext


def _mock_completion(content: str):
    """Build a mock ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestExtractEvent:
    """Test webpage content extraction."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self, extractor):
        event_json = json.dumps({
            "title": "Test Event",
            "start_datetime": "2026-03-15T19:00:00-07:00",
            "confidence_score": 0.9,
        })
        extractor.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(event_json)
        )

        event = await extractor.extract_event("https://example.com", "content here")
        assert isinstance(event, Event)
        assert event.title == "Test Event"
        assert event.source_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_null_title_gets_default(self, extractor):
        event_json = json.dumps({
            "title": None,
            "confidence_score": 0.5,
        })
        extractor.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(event_json)
        )

        event = await extractor.extract_event("https://example.com", "content")
        assert event.title == "Unknown Event"

    @pytest.mark.asyncio
    async def test_markdown_code_block_cleaned(self, extractor):
        event_json = '```json\n{"title": "Wrapped Event", "confidence_score": 0.8}\n```'
        extractor.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(event_json)
        )

        event = await extractor.extract_event("https://example.com", "content")
        assert event.title == "Wrapped Event"

    @pytest.mark.asyncio
    async def test_json_repair_on_truncated(self, extractor):
        # Missing closing brace
        broken_json = '{"title": "Truncated Event", "confidence_score": 0.7'
        extractor.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(broken_json)
        )

        event = await extractor.extract_event("https://example.com", "content")
        assert event.title == "Truncated Event"

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, extractor):
        extractor.max_retries = 2
        extractor.base_delay = 0.01
        extractor.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        event = await extractor.extract_event("https://example.com", "content")
        assert event.title == "Extraction Failed"
        assert event.confidence_score == 0.0

    @pytest.mark.asyncio
    async def test_screenshot_ignored_gracefully(self, extractor):
        event_json = json.dumps({"title": "No Image", "confidence_score": 0.8})
        extractor.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(event_json)
        )

        event = await extractor.extract_event(
            "https://example.com", "content", screenshot_b64="base64data"
        )
        assert event.title == "No Image"


class TestExtractEventFromImage:
    """Test image extraction (unsupported for most providers)."""

    @pytest.mark.asyncio
    async def test_returns_not_supported(self, extractor):
        event = await extractor.extract_event_from_image("base64data")
        assert event.title == "Extraction Failed"
        assert "not supported" in event.extraction_notes

    @pytest.mark.asyncio
    async def test_includes_source_description(self, extractor):
        event = await extractor.extract_event_from_image(
            "base64data", source_description="Slack upload"
        )
        assert "Slack upload" in event.extraction_notes
