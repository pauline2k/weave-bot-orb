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
  "start_datetime": "ISO 8601 datetime WITH timezone offset, or null if not confidently known (e.g., '2026-01-20T18:30:00{offset_str}')",
  "end_datetime": "ISO 8601 datetime WITH timezone offset, or null if not stated/not confidently known (e.g., '2026-01-20T21:00:00{offset_str}')",
  "timezone": "string or null (e.g., '{timezone_name}', 'PST') - also include offset in datetimes above",
  "location": {{
    "type": "physical" | "virtual" | "hybrid",
    "venue": "string or null (venue name)",
    "address": "string or null (full address)",
    "city": "string or null",
    "neighborhood": "string or null (include only if the city is Oakland)",
    "url": "string or null (for virtual events)"
  }} or null,
  "organizer": {{
    "name": "string or null",
    "contact": "string or null (email or phone)",
    "url": "string or null"
  }} or null,
  "registration_url": "string or null (link to register/buy tickets)",
  "source_url_provider": "string or null",
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
   - If the page states an explicit date (e.g. "Saturday, September 12, 2026"), use that exact date - do NOT recompute it yourself
   - Only compute a date from a recurrence description (e.g. "second Saturday of each month") if no explicit date is stated anywhere in the content. Calendar math like this is easy to get wrong, so double-check your answer actually falls on the stated weekday
   - Use {ctx["current_year"]} as the year unless a different year is explicitly shown
   - Exception: In Nov/Dec, if the event is for Jan/Feb without a year, use {ctx["current_year"] + 1}
   - When in doubt, assume the current year ({ctx["current_year"]})
   - Do NOT invent or guess a date or time that isn't clearly stated, or reliably computable from explicit information on the page. If you are not genuinely confident, leave start_datetime and/or end_datetime null rather than guessing - a missing value is far better than a wrong one. Lower confidence_score and explain what's missing/uncertain in extraction_notes instead
   - "Today's date" above is given ONLY to help interpret relative or partial dates that actually appear in the content (e.g. "this Friday", a day-of-month with no year stated). It is NEVER itself a valid guess for the event's date. If the content gives you no real date to interpret, do not default to today's date, a date near it, or any other plausible-sounding placeholder
   - If the content below is not a real event page - e.g. a bot/security-check interstitial (Cloudflare "verifying you are not a bot", a CAPTCHA, a login wall, an error page) - do NOT fall back on general knowledge of the venue or URL to invent a "typical" date, time, or other details. Return null for every field you cannot verify from actual page content, with a low confidence_score, and say in extraction_notes that the page could not be accessed
4. For timezone:
   - ALWAYS include timezone offset in the datetime string
   - Default to {ctx["timezone_name"]}: {ctx["offset_str"]} (current offset, accounts for DST)
   - Only use a different timezone if explicitly stated in the content
   - If a raw JSON-LD/structured-data block gives a datetime with a DIFFERENT offset than {ctx["offset_str"]} (e.g. "...T19:00:00+00:00", which is UTC), you MUST actually convert the wall-clock time to {ctx["timezone_name"]} - do NOT just copy the digits and relabel the offset. Cross-check your converted time against any plain-language time on the page (e.g. "Noon - 1 p.m."); if they don't match, you converted wrong
5. For neighborhood:
   - If the city is not Oakland, leave this value null.
   - If the city is Oakland, use the Oakland neighborhood that corresponds most closely to the address (examples: Downtown, Temescal, Grand Lake, Adams Point).
6. For source_url_provider:
   - Return the name of the organization indicated by the hostname of the url {url}.
   - For Instagram, use the lowercase shorthand "insta."
7. If the page contains MULTIPLE events, extract the PRIMARY or FIRST event
8. Set confidence_score based on how complete and certain the information is
9. Use extraction_notes to explain any assumptions, missing data, or ambiguities
10. If an image is attached, it may be a poster/flyer (common on social media posts) where the
    text content above has little or no date/time/venue info - that image is often the ONLY
    source of truth in that case. Read ALL text in it carefully, including small print, before
    falling back to guessing. Lower confidence_score if that text is blurry or hard to read.

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
   - If a date is shown but no time is given anywhere in the image, do NOT invent a plausible-sounding time (e.g. don't default to "7pm" just because the event sounds like an evening thing) - leave start_datetime/end_datetime null instead, note in extraction_notes that no time was found, and lower confidence_score accordingly
   - More generally: do NOT guess a date or time that isn't visible or reliably determinable from the image itself. A missing value is far better than a wrong one
   - Use {ctx["current_year"]} as the year unless a different year is explicitly shown
   - Exception: In Nov/Dec, if the event is for Jan/Feb without a year, use {ctx["current_year"] + 1}
   - When in doubt, assume the current year ({ctx["current_year"]})
4. For timezone:
   - ALWAYS include timezone offset in datetime (e.g., '2026-01-20T19:00:00{ctx["offset_str"]}')
   - Default to {ctx["timezone_name"]}: {ctx["offset_str"]} (current offset, accounts for DST)
   - Only use a different timezone if explicitly stated in the image
5. For neighborhood:
   - If the city is not Oakland, leave this value null.
   - If the city is Oakland, use the Oakland neighborhood that corresponds most closely to the address (examples: Downtown, Temescal, Grand Lake, Adams Point).
6. For source_url_provider, return null.
7. Read ALL text in the image carefully - event details are often in smaller text
8. Set confidence_score LOWER if:
   - Text is blurry, small, or hard to read
   - Information appears cut off or partially visible
   - Image quality is poor
   - You had to make assumptions about unclear text
9. Use extraction_notes to document:
   - Any text you couldn't read clearly
   - Assumptions you made
   - Parts of the image that seem cut off

Return your JSON response now:"""
