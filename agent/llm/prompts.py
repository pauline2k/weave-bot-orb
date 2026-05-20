"""Shared prompt templates for LLM event extraction.

Used by all LLM extractors (Gemini, OpenAI-compatible, etc.) to ensure
consistent extraction behavior regardless of provider.
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def _get_time_context(timezone: str) -> dict:
    """Build time context for prompt templates."""
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    offset = now.strftime("%z")
    offset_str = f"{offset[:3]}:{offset[3:]}"
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_year": now.year,
        "offset_str": offset_str,
        "timezone_name": timezone,
    }


EVENT_JSON_SCHEMA = """\
{{
  "title": "string (required - the event name/title)",
  "description": "string or null (event description/details)",
  "start_datetime": "ISO 8601 datetime WITH timezone offset (e.g., '2026-01-20T18:30:00{offset_str}')",
  "end_datetime": "ISO 8601 datetime WITH timezone offset or null (e.g., '2026-01-20T21:00:00{offset_str}')",
  "timezone": "string or null (e.g., '{timezone_name}', 'PST') - also include offset in datetimes above",
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
}}"""


def build_extraction_prompt(url: str, content: str, timezone: str = "America/Los_Angeles") -> str:
    """Build prompt for extracting event info from webpage content."""
    ctx = _get_time_context(timezone)
    schema = EVENT_JSON_SCHEMA.format(**ctx)

    return f"""You are an expert at extracting structured event information from web pages.

Today's date is: {ctx["current_date"]}

I will provide you with content from a webpage at: {url}

Your task is to extract event information and return it as valid JSON matching this exact schema:

{schema}

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no markdown code blocks or other text
2. Use null for any fields you cannot determine
3. For dates/times:
   - PREFER dates found in "STRUCTURED EVENT DATA" section if available - these are authoritative
   - Use {ctx["current_year"]} as the year unless a different year is explicitly shown
   - Exception: In Nov/Dec, if the event is for Jan/Feb without a year, use {ctx["current_year"] + 1}
   - When in doubt, assume the current year ({ctx["current_year"]})
4. For timezone:
   - ALWAYS include timezone offset in the datetime string
   - Default to {ctx["timezone_name"]}: {ctx["offset_str"]} (current offset, accounts for DST)
   - Only use a different timezone if explicitly stated in the content
5. If the page contains MULTIPLE events, extract the PRIMARY or FIRST event
6. Set confidence_score based on how complete and certain the information is
7. Use extraction_notes to explain any assumptions, missing data, or ambiguities

WEBPAGE CONTENT:
{content}

Return your JSON response now:"""


def build_image_extraction_prompt(timezone: str = "America/Los_Angeles") -> str:
    """Build prompt for extracting event info from an image."""
    ctx = _get_time_context(timezone)
    schema = EVENT_JSON_SCHEMA.format(**ctx)

    return f"""You are an expert at extracting event information from images such as event posters, flyers, screenshots, and promotional materials.

Today's date is: {ctx["current_date"]}

Analyze the attached image and extract event information. Return valid JSON matching this exact schema:

{schema}

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no markdown code blocks or other text
2. Use null for any fields you cannot determine from the image
3. For dates/times:
   - If only a date is shown without time, set a reasonable time based on context (evening events ~19:00)
   - Use {ctx["current_year"]} as the year unless a different year is explicitly shown
   - Exception: In Nov/Dec, if the event is for Jan/Feb without a year, use {ctx["current_year"] + 1}
   - When in doubt, assume the current year ({ctx["current_year"]})
4. For timezone:
   - ALWAYS include timezone offset in datetime (e.g., '2026-01-20T19:00:00{ctx["offset_str"]}')
   - Default to {ctx["timezone_name"]}: {ctx["offset_str"]} (current offset, accounts for DST)
   - Only use a different timezone if explicitly stated in the image
5. Read ALL text in the image carefully - event details are often in smaller text
6. Set confidence_score LOWER if:
   - Text is blurry, small, or hard to read
   - Information appears cut off or partially visible
   - Image quality is poor
   - You had to make assumptions about unclear text
7. Use extraction_notes to document:
   - Any text you couldn't read clearly
   - Assumptions you made
   - Parts of the image that seem cut off

Return your JSON response now:"""
