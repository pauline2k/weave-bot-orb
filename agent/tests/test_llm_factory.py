"""Tests for LLM factory — creates correct extractor per org config."""
import pytest
from unittest.mock import patch

from agent.core.org_config import OrgConfig, LLMConfig
from agent.llm.factory import create_extractor
from agent.llm.gemini import GeminiExtractor
from agent.llm.openai_compat import OpenAICompatExtractor


class TestCreateExtractor:
    """Test that factory returns the correct extractor type."""

    def test_gemini_provider(self):
        config = OrgConfig(
            llm=LLMConfig(provider="gemini", api_key="test-key", model="gemini-2.5-flash-lite"),
            timezone="America/Los_Angeles",
        )
        extractor = create_extractor(config)
        assert isinstance(extractor, GeminiExtractor)
        assert extractor.timezone == "America/Los_Angeles"

    def test_openai_compatible_provider(self):
        config = OrgConfig(
            llm=LLMConfig(
                provider="openai_compatible",
                api_key="hf-key",
                model="PleIAs/pleias-large",
                endpoint_url="https://api-inference.huggingface.co/v1",
            ),
            timezone="America/New_York",
        )
        extractor = create_extractor(config)
        assert isinstance(extractor, OpenAICompatExtractor)
        assert extractor.timezone == "America/New_York"
        assert extractor.model == "PleIAs/pleias-large"

    def test_openai_compatible_requires_endpoint(self):
        config = OrgConfig(
            llm=LLMConfig(
                provider="openai_compatible",
                api_key="key",
                model="test",
            ),
        )
        with pytest.raises(ValueError, match="endpoint_url"):
            create_extractor(config)

    def test_unknown_provider_raises(self):
        config = OrgConfig(
            llm=LLMConfig(provider="unknown_llm", api_key="key"),
        )
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_extractor(config)

    def test_timezone_passed_to_gemini(self):
        config = OrgConfig(
            llm=LLMConfig(provider="gemini", api_key="key"),
            timezone="Europe/London",
        )
        extractor = create_extractor(config)
        assert extractor.timezone == "Europe/London"
