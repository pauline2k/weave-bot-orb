"""Content processing and cleaning for LLM consumption."""
import re
import json
from typing import Optional, Dict, Any, Tuple

import trafilatura
import html2text


class ContentProcessor:
    """Processes and cleans scraped content for LLM extraction."""

    def __init__(self):
        """Initialize the content processor with html2text converter."""
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_emphasis = False
        self.html_converter.body_width = 0  # No wrapping
        self._last_event_data = None  # Store JSON-LD event data for post-processing

    def get_json_ld_event_data(self) -> Optional[Dict[str, Any]]:
        """Return the last extracted JSON-LD event data."""
        return self._last_event_data

    def extract_json_ld(self, html: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Extract JSON-LD structured data from HTML.

        Returns both the raw JSON-LD string and parsed event data if found.

        Args:
            html: Raw HTML content

        Returns:
            Tuple of (json_ld_string, parsed_event_data or None)
        """
        json_ld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        matches = re.findall(json_ld_pattern, html, flags=re.DOTALL | re.IGNORECASE)

        json_ld_str = ""
        event_data = None

        for match in matches:
            try:
                data = json.loads(match.strip())
                # Check if this is event data (has startDate or @type Event)
                if isinstance(data, dict):
                    if data.get('@type') == 'Event' or 'startDate' in data:
                        event_data = data
                    # Also check for nested event in @graph
                    if '@graph' in data:
                        for item in data['@graph']:
                            if isinstance(item, dict) and (item.get('@type') == 'Event' or 'startDate' in item):
                                event_data = item
                                break
                # Remove any falsey values that will break validation.
                if event_data:
                    event_data = dict((k, v) for k, v in event_data.items() if v)
            except json.JSONDecodeError:
                pass

        if matches:
            json_ld_str = "\n".join(matches)

        return json_ld_str, event_data

    def extract_main_content(self, html: str) -> str:
        """
        Extract main content from HTML using trafilatura.

        This removes boilerplate (nav, footer, ads) and returns just the article content.

        Args:
            html: Raw HTML content

        Returns:
            Extracted main content as text
        """
        # Use trafilatura to extract main content
        # It's designed to extract article/main content and ignore boilerplate
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,  # We want more content for event pages
            output_format='txt'
        )

        return extracted or ""

    def html_to_markdown(self, html: str) -> str:
        """
        Convert HTML to clean Markdown for LLM consumption.

        Args:
            html: HTML content

        Returns:
            Markdown formatted text
        """
        # First try trafilatura for clean extraction
        markdown = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            output_format='markdown'
        )

        if markdown:
            return markdown

        # Fallback to html2text
        return self.html_converter.handle(html)

    def process(self, html: str, text: str = "") -> str:
        """
        Process HTML content into LLM-ready format.

        This is the main entry point that:
        1. Extracts JSON-LD structured data (most reliable for dates)
        2. Extracts main content using trafilatura
        3. Converts to clean markdown format

        Args:
            html: Raw HTML from the page
            text: Optional pre-extracted text (fallback)

        Returns:
            Clean, LLM-ready content string
        """
        if not html:
            return text or ""

        # Step 1: Extract JSON-LD (contains authoritative date/time info)
        json_ld_str, event_data = self.extract_json_ld(html)
        self._last_event_data = event_data  # Store for post-processing

        # Step 2: Extract main content as markdown
        main_content = self.html_to_markdown(html)

        # If trafilatura failed, use the provided text
        if not main_content and text:
            main_content = text

        # Step 3: Build the final content with JSON-LD prominently at top
        parts = []

        # JSON-LD first - this has the authoritative dates
        if event_data:
            parts.append("## STRUCTURED EVENT DATA (use these dates!):")
            # Format key event fields clearly
            if 'name' in event_data:
                parts.append(f"Event Name: {event_data['name']}")
            if 'startDate' in event_data:
                parts.append(f"Start Date: {event_data['startDate']}")
            if 'endDate' in event_data:
                parts.append(f"End Date: {event_data['endDate']}")
            if 'location' in event_data:
                loc = event_data['location']
                if isinstance(loc, dict):
                    if 'name' in loc:
                        parts.append(f"Venue: {loc['name']}")
                    if 'address' in loc:
                        addr = loc['address']
                        if isinstance(addr, dict):
                            addr_parts = [addr.get('streetAddress', ''), addr.get('addressLocality', ''), addr.get('addressRegion', '')]
                            parts.append(f"Address: {', '.join(p for p in addr_parts if p)}")
                        else:
                            parts.append(f"Address: {addr}")
            if 'description' in event_data:
                parts.append(f"Description: {event_data['description'][:500]}")
            parts.append("")
        elif json_ld_str:
            # Include raw JSON-LD if we couldn't parse it as event
            parts.append("## STRUCTURED DATA (JSON-LD):")
            parts.append(json_ld_str[:2000])  # Limit size
            parts.append("")

        # Main page content
        parts.append("## PAGE CONTENT:")
        parts.append(main_content)

        combined = "\n".join(parts)

        # Truncate if too long (target ~40k chars = ~10k tokens)
        if len(combined) > 40000:
            combined = combined[:40000] + "\n\n[Content truncated...]"

        return combined

    # Keep legacy methods for backward compatibility
    @staticmethod
    def clean_html(html: str, max_length: int = 50000) -> str:
        """Legacy method - use process() instead."""
        processor = ContentProcessor()
        return processor.html_to_markdown(html)[:max_length]

    @staticmethod
    def clean_text(text: str, max_length: int = 30000) -> str:
        """Clean extracted text content."""
        if not text:
            return ""
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        if len(text) > max_length:
            text = text[:max_length] + "..."
        return text.strip()

    @staticmethod
    def extract_relevant_content(html: str, text: str, raw_html: str = "") -> str:
        """Legacy method - use process() instead."""
        processor = ContentProcessor()
        return processor.process(raw_html or html, text)
