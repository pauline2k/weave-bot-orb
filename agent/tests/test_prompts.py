"""Tests for shared prompt builder."""
from agent.llm.prompts import build_extraction_prompt, build_image_extraction_prompt


class TestBuildExtractionPrompt:
    """Test webpage extraction prompt generation."""

    def test_contains_url_and_content(self):
        prompt = build_extraction_prompt("https://example.com", "Event content here")
        assert "https://example.com" in prompt
        assert "Event content here" in prompt

    def test_contains_json_schema(self):
        prompt = build_extraction_prompt("https://x.com", "content")
        assert '"title"' in prompt
        assert '"start_datetime"' in prompt
        assert '"confidence_score"' in prompt

    def test_default_pacific_timezone(self):
        prompt = build_extraction_prompt("https://x.com", "content")
        assert "America/Los_Angeles" in prompt

    def test_custom_timezone(self):
        prompt = build_extraction_prompt("https://x.com", "content", timezone="America/New_York")
        assert "America/New_York" in prompt

    def test_contains_current_year(self):
        from datetime import datetime
        year = str(datetime.now().year)
        prompt = build_extraction_prompt("https://x.com", "content")
        assert year in prompt

    def test_timezone_offset_in_prompt(self):
        prompt = build_extraction_prompt("https://x.com", "content", timezone="America/Los_Angeles")
        # Should contain either -08:00 or -07:00 depending on DST
        assert "-08:00" in prompt or "-07:00" in prompt


class TestBuildImageExtractionPrompt:
    """Test image extraction prompt generation."""

    def test_contains_json_schema(self):
        prompt = build_image_extraction_prompt()
        assert '"title"' in prompt
        assert '"confidence_score"' in prompt

    def test_default_pacific_timezone(self):
        prompt = build_image_extraction_prompt()
        assert "America/Los_Angeles" in prompt

    def test_custom_timezone(self):
        prompt = build_image_extraction_prompt(timezone="Europe/London")
        assert "Europe/London" in prompt

    def test_mentions_image_analysis(self):
        prompt = build_image_extraction_prompt()
        assert "image" in prompt.lower()
        assert "poster" in prompt.lower() or "flyer" in prompt.lower()
