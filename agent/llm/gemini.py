"""Gemini-based event extraction implementation."""
import json
import base64
import asyncio
import logging
from typing import Optional, Dict, Any, Callable
import google.generativeai as genai
from PIL import Image
import io

from agent.llm.base import LLMExtractor
from agent.llm.prompts import build_extraction_prompt, build_image_extraction_prompt
from agent.core.schemas import Event
from agent.core.config import settings

logger = logging.getLogger(__name__)


class GeminiExtractor(LLMExtractor):
    """Gemini-based event information extractor."""

    def __init__(self, model_name: str = "gemini-2.5-flash-lite",
                 api_key: Optional[str] = None,
                 timezone: str = "America/Los_Angeles"):
        """Initialize Gemini API client."""
        genai.configure(api_key=api_key or settings.gemini_api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)
        self.timezone = timezone

        # Retry configuration
        self.max_retries = 3
        self.base_delay = 2  # seconds

    def _build_extraction_prompt(self, url: str, content: str) -> str:
        """Build the prompt for event extraction."""
        return build_extraction_prompt(url, content, timezone=self.timezone)

    def _clean_response_text(self, response_text: str) -> str:
        """Clean the LLM response text, removing markdown code blocks."""
        response_text = response_text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        return response_text

    def _repair_json(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to repair malformed JSON from LLM response.

        Returns parsed dict if successful, None if repair fails.
        """
        # Try to find and close unclosed JSON
        try:
            # Method 1: Find last closing brace and truncate
            last_brace = response_text.rfind("}")
            if last_brace != -1:
                repaired = response_text[:last_brace + 1]
                return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Method 2: Try to balance braces
        try:
            open_braces = response_text.count("{")
            close_braces = response_text.count("}")
            if open_braces > close_braces:
                repaired = response_text + ("}" * (open_braces - close_braces))
                return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        return None

    async def _generate_and_parse(
        self,
        parts: list,
        post_parse: Optional[Callable[[Dict[str, Any]], None]] = None,
        error_context: str = "extraction",
    ) -> tuple[Optional[Dict[str, Any]], str]:
        """Shared retry loop with JSON repair for Gemini calls.

        Returns (event_data_dict, last_response_text). event_data is None on failure.
        """
        last_error = None
        response_text = ""

        for attempt in range(self.max_retries):
            try:
                response = self.model.generate_content(parts)
                response_text = self._clean_response_text(response.text)

                try:
                    event_data = json.loads(response_text)
                except json.JSONDecodeError as json_error:
                    logger.warning(f"JSON parse failed, attempting repair: {json_error}")
                    event_data = self._repair_json(response_text)
                    if event_data is None:
                        raise json_error
                    existing_notes = event_data.get('extraction_notes', '') or ''
                    event_data['extraction_notes'] = f"JSON parsing required repair. {existing_notes}".strip()
                    logger.info("JSON repair successful")

                if post_parse:
                    post_parse(event_data)

                return event_data, response_text

            except Exception as e:
                last_error = e
                error_str = str(e)

                if attempt < self.max_retries - 1:
                    if "429" in error_str:
                        sleep_time = self.base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited (429), retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                        await asyncio.sleep(sleep_time)
                    elif "quota" in error_str.lower():
                        sleep_time = self.base_delay * (2 ** attempt)
                        logger.warning(f"Quota issue, retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
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
        screenshot_b64: Optional[str] = None
    ) -> Event:
        """
        Extract event information using Gemini with retry logic.

        Args:
            url: Source URL
            content: Cleaned webpage content
            screenshot_b64: Optional base64-encoded screenshot

        Returns:
            Extracted Event object
        """
        prompt = self._build_extraction_prompt(url, content)
        parts = [prompt]

        if screenshot_b64:
            try:
                image_bytes = base64.b64decode(screenshot_b64)
                image = Image.open(io.BytesIO(image_bytes))
                parts.append(image)
            except Exception as e:
                logger.warning(f"Could not process screenshot: {e}")

        def _set_source_url(data):
            data['source_url'] = url

        event_data, response_text = await self._generate_and_parse(
            parts, post_parse=_set_source_url, error_context=f"Extraction for {url}"
        )

        if event_data is not None:
            if event_data.get('title') is None:
                event_data['title'] = "Unknown Event"
            return Event(**event_data)

        error_msg = f"Failed after {self.max_retries} attempts"
        return Event(
            title="Extraction Failed",
            source_url=url,
            confidence_score=0.0,
            extraction_notes=error_msg + (f"\nLast response: {response_text[:300]}" if response_text else "")
        )

    def _build_image_extraction_prompt(self) -> str:
        """Build the prompt for extracting event info from an image."""
        return build_image_extraction_prompt(timezone=self.timezone)

    async def extract_event_from_image(
        self,
        image_b64: str,
        source_description: Optional[str] = None
    ) -> Event:
        """
        Extract event information from an image using Gemini.

        Args:
            image_b64: Base64-encoded image data
            source_description: Optional description of where the image came from

        Returns:
            Extracted Event object
        """
        prompt = self._build_image_extraction_prompt()

        try:
            image_bytes = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            logger.error(f"Failed to decode image: {e}")
            return Event(
                title="Extraction Failed",
                source_url=None,
                confidence_score=0.0,
                extraction_notes=f"Failed to decode image: {str(e)}"
            )

        def _set_image_metadata(data):
            data['source_url'] = None
            if source_description:
                existing_notes = data.get('extraction_notes', '') or ''
                data['extraction_notes'] = f"Source: {source_description}. {existing_notes}".strip()

        event_data, response_text = await self._generate_and_parse(
            [prompt, image], post_parse=_set_image_metadata, error_context="Image extraction"
        )

        if event_data is not None:
            if event_data.get('title') is None:
                event_data['title'] = "Unknown Event"
            return Event(**event_data)

        error_msg = f"Failed after {self.max_retries} attempts"
        return Event(
            title="Extraction Failed",
            source_url=None,
            confidence_score=0.0,
            extraction_notes=error_msg + (f"\nLast response: {response_text[:300]}" if response_text else "")
        )
