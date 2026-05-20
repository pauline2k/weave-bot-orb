"""OpenAI-compatible LLM extractor.

Works with any OpenAI-compatible API endpoint (HuggingFace Inference,
Replicate, vLLM, etc.) via the openai Python SDK's base_url parameter.
"""
import json
import asyncio
import logging
from typing import Optional, Dict, Any

from openai import AsyncOpenAI

from agent.llm.base import LLMExtractor
from agent.llm.prompts import build_extraction_prompt, build_image_extraction_prompt
from agent.core.schemas import Event

logger = logging.getLogger(__name__)


class OpenAICompatExtractor(LLMExtractor):
    """Event extractor using any OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str, endpoint_url: str,
                 timezone: str = "America/Los_Angeles"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=endpoint_url)
        self.model = model
        self.timezone = timezone

        # Retry configuration
        self.max_retries = 3
        self.base_delay = 2  # seconds

    def _clean_response_text(self, text: str) -> str:
        """Clean LLM response text, removing markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return text

    def _repair_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Attempt to repair malformed JSON."""
        try:
            last_brace = text.rfind("}")
            if last_brace != -1:
                return json.loads(text[:last_brace + 1])
        except json.JSONDecodeError:
            pass

        try:
            open_braces = text.count("{")
            close_braces = text.count("}")
            if open_braces > close_braces:
                return json.loads(text + ("}" * (open_braces - close_braces)))
        except json.JSONDecodeError:
            pass

        return None

    async def _call_llm(self, prompt: str, error_context: str = "extraction") -> tuple[Optional[Dict[str, Any]], str]:
        """Call the OpenAI-compatible API with retry and JSON repair.

        Returns (parsed_dict, last_response_text). parsed_dict is None on failure.
        """
        last_error = None
        response_text = ""

        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                response_text = self._clean_response_text(
                    response.choices[0].message.content or ""
                )

                try:
                    event_data = json.loads(response_text)
                except json.JSONDecodeError as json_error:
                    logger.warning(f"JSON parse failed, attempting repair: {json_error}")
                    event_data = self._repair_json(response_text)
                    if event_data is None:
                        raise json_error
                    existing_notes = event_data.get("extraction_notes", "") or ""
                    event_data["extraction_notes"] = f"JSON parsing required repair. {existing_notes}".strip()

                return event_data, response_text

            except Exception as e:
                last_error = e
                error_str = str(e)

                if attempt < self.max_retries - 1:
                    # HuggingFace returns 503 when model is loading
                    if "503" in error_str or "loading" in error_str.lower():
                        sleep_time = self.base_delay * (2 ** attempt) * 2  # longer waits for cold starts
                        logger.warning(f"Model loading (503), retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                        await asyncio.sleep(sleep_time)
                    elif "429" in error_str or "rate" in error_str.lower():
                        sleep_time = self.base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited, retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.warning(f"{error_context} error, retrying: {error_str[:100]}")
                        await asyncio.sleep(1)
                    continue
                break

        error_msg = f"Failed after {self.max_retries} attempts: {str(last_error)}"
        logger.error(f"{error_context} failed: {error_msg}")
        return None, response_text

    async def extract_event(
        self,
        url: str,
        content: str,
        screenshot_b64: Optional[str] = None,
    ) -> Event:
        """Extract event information from webpage content.

        Note: screenshot_b64 is ignored — most OpenAI-compatible endpoints
        don't support multimodal input. The text content is used instead.
        """
        if screenshot_b64:
            logger.info("Screenshot provided but ignored — provider may not support multimodal")

        prompt = build_extraction_prompt(url, content, timezone=self.timezone)
        event_data, response_text = await self._call_llm(
            prompt, error_context=f"Extraction for {url}"
        )

        if event_data is not None:
            event_data["source_url"] = url
            if event_data.get("title") is None:
                event_data["title"] = "Unknown Event"
            return Event(**event_data)

        return Event(
            title="Extraction Failed",
            source_url=url,
            confidence_score=0.0,
            extraction_notes=f"Failed after {self.max_retries} attempts"
            + (f"\nLast response: {response_text[:300]}" if response_text else ""),
        )

    async def extract_event_from_image(
        self,
        image_b64: str,
        source_description: Optional[str] = None,
    ) -> Event:
        """Extract event info from an image.

        Most OpenAI-compatible endpoints don't support vision. Returns a
        low-confidence placeholder directing the user to use text content.
        """
        logger.warning("Image extraction not supported for this provider")
        return Event(
            title="Extraction Failed",
            source_url=None,
            confidence_score=0.0,
            extraction_notes="Image extraction not supported for this LLM provider. "
            "Please submit a URL with text content instead."
            + (f" Source: {source_description}" if source_description else ""),
        )
