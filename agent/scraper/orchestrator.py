"""Orchestrates the complete scraping pipeline."""
from typing import Dict, Any, Optional
from agent.scraper.browser import BrowserManager
from agent.scraper.processor import ContentProcessor
from agent.llm.gemini import GeminiExtractor
from agent.core.schemas import Event, ScrapeResponse


class ScrapingOrchestrator:
    """Orchestrates the complete event scraping pipeline."""

    def __init__(self):
        """Initialize the orchestrator with LLM extractor."""
        self.llm_extractor = GeminiExtractor()
        self.content_processor = ContentProcessor()

    def _apply_json_ld_dates(self, event: Event, json_ld_data: Dict[str, Any]) -> Event:
        """
        Override event dates with authoritative JSON-LD data.

        LLMs often get dates wrong, but JSON-LD structured data is authoritative.
        """
        event_dict = event.model_dump()

        # Override start_datetime if available in JSON-LD
        if 'startDate' in json_ld_data:
            start_date = json_ld_data['startDate']
            # Clean up milliseconds: "2025-11-20T18:30:00.000-08:00" -> "2025-11-20T18:30:00-08:00"
            if '.000' in start_date:
                start_date = start_date.replace('.000', '')
            event_dict['start_datetime'] = start_date

        # Override end_datetime if available
        if 'endDate' in json_ld_data:
            end_date = json_ld_data['endDate']
            if '.000' in end_date:
                end_date = end_date.replace('.000', '')
            event_dict['end_datetime'] = end_date

        # Add note about JSON-LD override
        notes = event_dict.get('extraction_notes') or ''
        if 'startDate' in json_ld_data:
            notes = f"Dates from JSON-LD structured data. {notes}".strip()
            event_dict['extraction_notes'] = notes

        return Event(**event_dict)

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
                event = self._apply_json_ld_dates(event, json_ld_data)

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
