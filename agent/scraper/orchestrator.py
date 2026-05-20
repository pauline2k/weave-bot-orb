"""Orchestrates the complete scraping pipeline."""
from typing import Dict, Any, Optional
from agent.scraper.browser import BrowserManager
from agent.scraper.processor import ContentProcessor
from agent.llm.base import LLMExtractor
from agent.llm.gemini import GeminiExtractor
from agent.core.schemas import Event, ScrapeResponse
from agent.core.validation import validate_event


class ScrapingOrchestrator:
    """Orchestrates the complete event scraping pipeline."""

    def __init__(self, llm_extractor: Optional[LLMExtractor] = None):
        """Initialize the orchestrator with optional LLM extractor."""
        self.llm_extractor = llm_extractor or GeminiExtractor()
        self.content_processor = ContentProcessor()

    def _apply_json_ld_overrides(self, event: Event, json_ld_data: Dict[str, Any]) -> Event:
        """
        Override event fields with authoritative JSON-LD structured data.

        JSON-LD is more reliable than LLM extraction for dates, venue,
        address, and organizer — especially on Eventbrite and Luma.
        """
        event_dict = event.model_dump()
        overrides = []

        # Override dates
        if 'startDate' in json_ld_data:
            start_date = json_ld_data['startDate']
            if '.000' in start_date:
                start_date = start_date.replace('.000', '')
            event_dict['start_datetime'] = start_date
            overrides.append("dates")

        if 'endDate' in json_ld_data:
            end_date = json_ld_data['endDate']
            if '.000' in end_date:
                end_date = end_date.replace('.000', '')
            event_dict['end_datetime'] = end_date
            if "dates" not in overrides:
                overrides.append("dates")

        # Override venue and address from location
        location = json_ld_data.get('location')
        if isinstance(location, dict):
            venue_name = location.get('name', '').strip()
            if venue_name and len(venue_name) > 1:
                if event_dict.get('location') is None:
                    event_dict['location'] = {}
                event_dict['location']['venue'] = venue_name
                overrides.append("venue")

            address = location.get('address')
            if address:
                address_str = self._parse_json_ld_address(address)
                if address_str:
                    if event_dict.get('location') is None:
                        event_dict['location'] = {}
                    event_dict['location']['address'] = address_str
                    overrides.append("address")

        # Override organizer
        organizer = json_ld_data.get('organizer')
        if isinstance(organizer, dict):
            org_name = organizer.get('name', '').strip()
            if org_name and len(org_name) > 1:
                if event_dict.get('organizer') is None:
                    event_dict['organizer'] = {}
                event_dict['organizer']['name'] = org_name
                overrides.append("organizer")

        # Add note about what was overridden
        if overrides:
            notes = event_dict.get('extraction_notes') or ''
            override_note = f"JSON-LD overrides: {', '.join(overrides)}."
            notes = f"{override_note} {notes}".strip()
            event_dict['extraction_notes'] = notes

        return Event(**event_dict)

    @staticmethod
    def _parse_json_ld_address(address) -> Optional[str]:
        """Parse JSON-LD address — handles both string and PostalAddress object."""
        if isinstance(address, str):
            return address.strip() or None
        if isinstance(address, dict):
            parts = [
                address.get('streetAddress', ''),
                address.get('addressLocality', ''),
                address.get('addressRegion', ''),
            ]
            result = ', '.join(p.strip() for p in parts if p and p.strip())
            return result or None
        return None

    async def scrape_event(
        self,
        url: str,
        wait_time: int = 3000,
        include_screenshot: bool = True
    ) -> ScrapeResponse:
        """
        Execute the complete scraping pipeline.

        Steps:
        1. Use Playwright to fetch page content
        2. Clean and process the content
        3. Send to LLM for structured extraction
        4. Return formatted response

        Args:
            url: The URL to scrape
            wait_time: Time to wait for page load in milliseconds
            include_screenshot: Whether to capture a screenshot

        Returns:
            ScrapeResponse with event data or error information
        """
        metadata = {
            "url": url,
            "wait_time": wait_time,
            "screenshot_included": include_screenshot
        }

        try:
            # Step 1: Browser fetch
            async with BrowserManager() as browser:
                page_data = await browser.scrape_page(
                    url=url,
                    wait_time=wait_time,
                    include_screenshot=include_screenshot
                )

            if not page_data["success"]:
                return ScrapeResponse(
                    success=False,
                    event=None,
                    error=page_data["error"],
                    metadata={**metadata, "stage": "browser_fetch"}
                )

            metadata["page_title"] = page_data["title"]

            # Step 2: Content processing (uses trafilatura + markdown conversion)
            combined_content = self.content_processor.process(
                html=page_data["html"],
                text=page_data["text"]
            )

            metadata["content_length"] = len(combined_content)

            # Step 3: LLM extraction
            event = await self.llm_extractor.extract_event(
                url=url,
                content=combined_content,
                screenshot_b64=page_data["screenshot"]
            )

            # Step 4: Post-process - override with authoritative JSON-LD dates
            json_ld_data = self.content_processor.get_json_ld_event_data()
            if json_ld_data:
                event = self._apply_json_ld_overrides(event, json_ld_data)

            # Step 5: Validate extracted data (warns but never rejects)
            event = validate_event(event)

            metadata["confidence_score"] = event.confidence_score

            # Check if extraction was successful
            if event.title == "Extraction Failed":
                return ScrapeResponse(
                    success=False,
                    event=event,
                    error="LLM extraction failed",
                    metadata={**metadata, "stage": "llm_extraction"}
                )

            # Partial success check
            # If we got a title but confidence is very low, mark as partial success
            if event.confidence_score and event.confidence_score < 0.3:
                return ScrapeResponse(
                    success=True,  # Still return the data
                    event=event,
                    error="Low confidence extraction - data may be incomplete",
                    metadata={**metadata, "stage": "completed", "warning": "low_confidence"}
                )

            # Full success
            return ScrapeResponse(
                success=True,
                event=event,
                error=None,
                metadata={**metadata, "stage": "completed"}
            )

        except Exception as e:
            return ScrapeResponse(
                success=False,
                event=None,
                error=f"Unexpected error in scraping pipeline: {str(e)}",
                metadata={**metadata, "stage": "unknown", "exception": str(e)}
            )

    async def analyze_image(
        self,
        image_b64: str,
        source_description: Optional[str] = None
    ) -> ScrapeResponse:
        """
        Extract event information from an image.

        This is for parsing event posters, flyers, screenshots, etc.
        No browser/HTML processing is needed - goes straight to LLM.

        Args:
            image_b64: Base64-encoded image data
            source_description: Optional description of where the image came from

        Returns:
            ScrapeResponse with event data or error information
        """
        metadata = {
            "parse_mode": "image",
            "source_description": source_description,
            "image_size_b64": len(image_b64) if image_b64 else 0
        }

        try:
            # Direct LLM extraction from image - no browser step needed
            event = await self.llm_extractor.extract_event_from_image(
                image_b64=image_b64,
                source_description=source_description
            )

            # Validate extracted data (warns but never rejects)
            event = validate_event(event)

            metadata["confidence_score"] = event.confidence_score

            # Check if extraction was successful
            if event.title == "Extraction Failed":
                return ScrapeResponse(
                    success=False,
                    event=event,
                    error="Image extraction failed",
                    metadata={**metadata, "stage": "image_extraction"}
                )

            # Low confidence check
            if event.confidence_score and event.confidence_score < 0.3:
                return ScrapeResponse(
                    success=True,
                    event=event,
                    error="Low confidence extraction - image may be unclear",
                    metadata={**metadata, "stage": "completed", "warning": "low_confidence"}
                )

            # Full success
            return ScrapeResponse(
                success=True,
                event=event,
                error=None,
                metadata={**metadata, "stage": "completed"}
            )

        except Exception as e:
            return ScrapeResponse(
                success=False,
                event=None,
                error=f"Unexpected error in image analysis: {str(e)}",
                metadata={**metadata, "stage": "unknown", "exception": str(e)}
            )
