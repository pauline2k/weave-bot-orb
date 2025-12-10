"""Gemini-based event extraction implementation."""
import json
import base64
import re
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import io

from agent.llm.base import LLMExtractor
from agent.core.schemas import Event, EventLocation, EventOrganizer
from agent.core.config import settings

logger = logging.getLogger(__name__)


class GeminiExtractor(LLMExtractor):
    """Gemini-based event information extractor."""

    def __init__(self, model_name: str = "gemini-2.5-flash-lite"):
        """Initialize Gemini API client."""
        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)

        # Retry configuration
        self.max_retries = 3
        self.base_delay = 2  # seconds

    def _build_extraction_prompt(self, url: str, content: str) -> str:
        """Build the prompt for event extraction."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year

        return f"""You are an expert at extracting structured event information from web pages.

Today's date is: {current_date}

I will provide you with content from a webpage at: {url}

Your task is to extract event information and return it as valid JSON matching this exact schema:

{{
  "title": "string (required - the event name/title)",
  "description": "string or null (event description/details)",
  "start_datetime": "ISO 8601 datetime string or null (e.g., '2025-11-20T18:30:00')",
  "end_datetime": "ISO 8601 datetime string or null",
  "timezone": "string or null (e.g., 'America/Los_Angeles', 'PST', 'UTC-8')",
  "location": {{
    "type": "physical" | "virtual" | "hybrid",
    "venue": "string or null (venue name)",
    "address": "string or null (full address)",
    "city": "string or null",
    "url": "string or null (for virtual events)"
  }} or null,
  "organizer": {{
    "name": "string or null",
    "contact": "string or null (email or phone)",
    "url": "string or null"
  }} or null,
  "registration_url": "string or null (link to register/buy tickets)",
  "price": "string or null (e.g., 'Free', '$20', '$10-$25')",
  "tags": ["array", "of", "strings"],
  "image_url": "string or null (main event image URL)",
  "confidence_score": number between 0 and 1 (your confidence in this extraction),
  "extraction_notes": "string or null (any issues, ambiguities, or important notes)"
}}

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no markdown code blocks or other text
2. Use null for any fields you cannot determine
3. For dates/times:
   - PREFER dates found in "STRUCTURED EVENT DATA" section if available - these are authoritative
   - Otherwise, use {current_year} as the year unless a different year is explicitly shown
   - If no year is specified and the month/day has passed, use {current_year + 1}
   - NEVER guess past years - trust explicit dates in the content or default to {current_year}
4. If the page contains MULTIPLE events, extract the PRIMARY or FIRST event
5. For timezone: try to infer from location or context if not explicit
6. Set confidence_score based on how complete and certain the information is
7. Use extraction_notes to explain any assumptions, missing data, or ambiguities

WEBPAGE CONTENT:
{content}

Return your JSON response now:"""

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

        # Prepare content parts for Gemini
        parts = [prompt]

        # Add screenshot if provided
        if screenshot_b64:
            try:
                image_bytes = base64.b64decode(screenshot_b64)
                image = Image.open(io.BytesIO(image_bytes))
                parts.append(image)
            except Exception as e:
                logger.warning(f"Could not process screenshot: {e}")

        # Retry loop with exponential backoff
        last_error = None
        response_text = ""

        for attempt in range(self.max_retries):
            try:
                # Generate response
                response = self.model.generate_content(parts)
                response_text = self._clean_response_text(response.text)

                # Try to parse JSON
                try:
                    event_data = json.loads(response_text)
                except json.JSONDecodeError as json_error:
                    # Attempt JSON repair
                    logger.warning(f"JSON parse failed, attempting repair: {json_error}")
                    event_data = self._repair_json(response_text)

                    if event_data is None:
                        raise json_error

                    # Mark as repaired
                    existing_notes = event_data.get('extraction_notes', '') or ''
                    event_data['extraction_notes'] = f"JSON parsing required repair. {existing_notes}".strip()
                    logger.info("JSON repair successful")

                # Add source URL
                event_data['source_url'] = url

                # Convert to Event object (Pydantic will validate)
                event = Event(**event_data)
                return event

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check for rate limit (429) error
                if "429" in error_str and attempt < self.max_retries - 1:
                    sleep_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Rate limited (429), retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue

                # Check for quota exhausted
                if "quota" in error_str.lower() and attempt < self.max_retries - 1:
                    sleep_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Quota issue, retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue

                # For other errors on non-final attempt, retry with shorter delay
                if attempt < self.max_retries - 1:
                    logger.warning(f"Extraction error, retrying: {error_str[:100]}")
                    await asyncio.sleep(1)
                    continue

                # Final attempt failed
                break

        # All retries exhausted
        error_msg = f"Failed after {self.max_retries} attempts: {str(last_error)}"
        logger.error(f"Extraction failed for {url}: {error_msg}")

        return Event(
            title="Extraction Failed",
            source_url=url,
            confidence_score=0.0,
            extraction_notes=error_msg + (f"\nLast response: {response_text[:300]}" if response_text else "")
        )

    def _build_image_extraction_prompt(self) -> str:
        """Build the prompt for extracting event info from an image."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year

        return f"""You are an expert at extracting event information from images such as event posters, flyers, screenshots, and promotional materials.

Today's date is: {current_date}

Analyze the attached image and extract event information. Return valid JSON matching this exact schema:

{{
  "title": "string (required - the event name/title)",
  "description": "string or null (event description/details visible in the image)",
  "start_datetime": "ISO 8601 datetime string or null (e.g., '2025-11-20T18:30:00')",
  "end_datetime": "ISO 8601 datetime string or null",
  "timezone": "string or null (e.g., 'America/Los_Angeles', 'PST', 'UTC-8')",
  "location": {{
    "type": "physical" | "virtual" | "hybrid",
    "venue": "string or null (venue name)",
    "address": "string or null (full address)",
    "city": "string or null",
    "url": "string or null (for virtual events)"
  }} or null,
  "organizer": {{
    "name": "string or null",
    "contact": "string or null (email or phone)",
    "url": "string or null"
  }} or null,
  "registration_url": "string or null (link visible in image)",
  "price": "string or null (e.g., 'Free', '$20', '$10-$25')",
  "tags": ["array", "of", "strings"],
  "image_url": null,
  "confidence_score": number between 0 and 1 (your confidence in this extraction),
  "extraction_notes": "string or null (note any text that's hard to read, cut off, or unclear)"
}}

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no markdown code blocks or other text
2. Use null for any fields you cannot determine from the image
3. For dates/times:
   - If only a date is shown without time, set a reasonable time based on context (evening events ~19:00)
   - Use {current_year} as the year if no year is shown and the date hasn't passed
   - If the month/day has already passed this year and no year shown, use {current_year + 1}
4. Read ALL text in the image carefully - event details are often in smaller text
5. Set confidence_score LOWER if:
   - Text is blurry, small, or hard to read
   - Information appears cut off or partially visible
   - Image quality is poor
   - You had to make assumptions about unclear text
6. Use extraction_notes to document:
   - Any text you couldn't read clearly
   - Assumptions you made
   - Parts of the image that seem cut off

Return your JSON response now:"""

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

        # Decode image
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

        # Prepare content parts for Gemini: [prompt, image]
        parts = [prompt, image]

        # Retry loop with exponential backoff
        last_error = None
        response_text = ""

        for attempt in range(self.max_retries):
            try:
                # Generate response
                response = self.model.generate_content(parts)
                response_text = self._clean_response_text(response.text)

                # Try to parse JSON
                try:
                    event_data = json.loads(response_text)
                except json.JSONDecodeError as json_error:
                    # Attempt JSON repair
                    logger.warning(f"JSON parse failed, attempting repair: {json_error}")
                    event_data = self._repair_json(response_text)

                    if event_data is None:
                        raise json_error

                    # Mark as repaired
                    existing_notes = event_data.get('extraction_notes', '') or ''
                    event_data['extraction_notes'] = f"JSON parsing required repair. {existing_notes}".strip()
                    logger.info("JSON repair successful")

                # No source URL for image-only extraction
                event_data['source_url'] = None

                # Add source description to notes if provided
                if source_description:
                    existing_notes = event_data.get('extraction_notes', '') or ''
                    event_data['extraction_notes'] = f"Source: {source_description}. {existing_notes}".strip()

                # Convert to Event object (Pydantic will validate)
                event = Event(**event_data)
                return event

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check for rate limit (429) error
                if "429" in error_str and attempt < self.max_retries - 1:
                    sleep_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Rate limited (429), retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue

                # Check for quota exhausted
                if "quota" in error_str.lower() and attempt < self.max_retries - 1:
                    sleep_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Quota issue, retrying in {sleep_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue

                # For other errors on non-final attempt, retry with shorter delay
                if attempt < self.max_retries - 1:
                    logger.warning(f"Image extraction error, retrying: {error_str[:100]}")
                    await asyncio.sleep(1)
                    continue

                # Final attempt failed
                break

        # All retries exhausted
        error_msg = f"Failed after {self.max_retries} attempts: {str(last_error)}"
        logger.error(f"Image extraction failed: {error_msg}")

        return Event(
            title="Extraction Failed",
            source_url=None,
            confidence_score=0.0,
            extraction_notes=error_msg + (f"\nLast response: {response_text[:300]}" if response_text else "")
        )
