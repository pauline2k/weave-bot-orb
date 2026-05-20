"""LLM extractor factory — creates the right extractor for an org's config."""
import logging

from agent.llm.base import LLMExtractor
from agent.core.org_config import OrgConfig

logger = logging.getLogger(__name__)


def create_extractor(org_config: OrgConfig) -> LLMExtractor:
    """Create an LLM extractor based on org configuration.

    Supported providers:
      - "gemini": Google Gemini (default for ORB)
      - "openai_compatible": Any OpenAI-compatible endpoint (HuggingFace, vLLM, etc.)
    """
    llm = org_config.llm
    tz = org_config.timezone

    if llm.provider == "gemini":
        from agent.llm.gemini import GeminiExtractor
        return GeminiExtractor(
            model_name=llm.model or "gemini-2.5-flash-lite",
            api_key=llm.api_key,
            timezone=tz,
        )

    if llm.provider == "openai_compatible":
        from agent.llm.openai_compat import OpenAICompatExtractor
        if not llm.endpoint_url:
            raise ValueError("openai_compatible provider requires endpoint_url")
        return OpenAICompatExtractor(
            api_key=llm.api_key,
            model=llm.model,
            endpoint_url=llm.endpoint_url,
            timezone=tz,
        )

    raise ValueError(f"Unknown LLM provider: {llm.provider!r}. Supported: gemini, openai_compatible")
