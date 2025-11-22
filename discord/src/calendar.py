"""Calendar export functionality - fetch events from Grist and format for ORB."""
import aiohttp
import logging
from datetime import datetime
from typing import Optional
from collections import defaultdict

from src.config import Config

logger = logging.getLogger(__name__)

# Grist API configuration
GRIST_API_BASE = "https://docs.getgrist.com/api"


async def fetch_events_from_grist(
    api_key: str,
    doc_id: str,
    days_ahead: int = 7
) -> list[dict]:
    """
    Fetch upcoming events from Grist.

    Args:
        api_key: Grist API key
        doc_id: Grist document ID
        days_ahead: Number of days to look ahead (not yet implemented as filter)

    Returns:
        List of event dictionaries
    """
    url = f"{GRIST_API_BASE}/docs/{doc_id}/tables/Events/records"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    records = data.get("records", [])

                    # Convert to simpler format
                    events = []
                    for record in records:
                        fields = record.get("fields", {})
                        events.append({
                            "id": record.get("id"),
                            "title": fields.get("Title"),
                            "start_datetime": fields.get("StartDatetime"),
                            "venue": fields.get("Venue"),
                            "address": fields.get("Address"),
                            "city": fields.get("City"),
                            "description": fields.get("Description"),
                            "source_url": fields.get("SourceURL"),
                            "price": fields.get("Price"),
                        })

                    return events
                else:
                    logger.error(f"Grist API error: {response.status}")
                    return []

    except Exception as e:
        logger.error(f"Error fetching from Grist: {e}")
        return []


def format_datetime_for_orb(timestamp: Optional[float]) -> tuple[str, str]:
    """
    Format a Grist timestamp for ORB calendar.

    Args:
        timestamp: Unix timestamp from Grist

    Returns:
        Tuple of (day_header, time_string)
        e.g., ("Tuesday, Nov 18", "6:30pm")
    """
    if not timestamp:
        return ("TBD", "Time TBD")

    try:
        dt = datetime.fromtimestamp(timestamp)
        day_header = dt.strftime("%A, %b %d")  # "Tuesday, Nov 18"
        time_str = dt.strftime("%-I:%M%p").lower()  # "6:30pm"
        return (day_header, time_str)
    except Exception:
        return ("TBD", "Time TBD")


def format_location_for_orb(venue: str, city: str = None) -> str:
    """
    Format location for ORB calendar style.

    Args:
        venue: Venue name
        city: City/neighborhood

    Returns:
        Formatted string like "Books Inc. Alameda (The Island)"
    """
    if not venue:
        return "Location TBD"

    if city:
        return f"{venue} ({city})"
    return venue


def generate_orb_calendar_markdown(events: list[dict]) -> str:
    """
    Generate ORB-style calendar markdown from events.

    Format:
    ## Tuesday, Nov 18

    **6:30pm, Books Inc. Alameda (The Island)**. Description. [[tickets](url)]

    Args:
        events: List of event dictionaries

    Returns:
        Markdown string ready for copy-paste
    """
    if not events:
        return "No events found in the database."

    # Group events by day
    events_by_day = defaultdict(list)

    for event in events:
        day_header, time_str = format_datetime_for_orb(event.get("start_datetime"))
        events_by_day[day_header].append({
            **event,
            "time_str": time_str,
            "day_sort": event.get("start_datetime") or 0
        })

    # Sort days chronologically
    sorted_days = sorted(
        events_by_day.keys(),
        key=lambda d: min(e["day_sort"] for e in events_by_day[d]) if events_by_day[d] else 0
    )

    # Build markdown
    lines = []

    for day in sorted_days:
        lines.append(f"## {day}")
        lines.append("")

        # Sort events within day by time
        day_events = sorted(events_by_day[day], key=lambda e: e["day_sort"])

        for event in day_events:
            time_str = event["time_str"]
            location = format_location_for_orb(
                event.get("venue"),
                event.get("city")
            )

            # Build event line
            event_line = f"**{time_str}, {location}**."

            # Add description if available
            description = event.get("description")
            if description:
                # Truncate if too long
                if len(description) > 200:
                    description = description[:197] + "..."
                event_line += f" {description}"

            # Add source link if available
            source_url = event.get("source_url")
            if source_url:
                event_line += f" [[link]({source_url})]"

            lines.append(event_line)
            lines.append("")

        lines.append("")

    return "\n".join(lines)


async def get_calendar_export(grist_api_key: str, grist_doc_id: str) -> str:
    """
    Main function to fetch events and generate calendar markdown.

    Args:
        grist_api_key: Grist API key
        grist_doc_id: Grist document ID

    Returns:
        Formatted markdown string
    """
    events = await fetch_events_from_grist(grist_api_key, grist_doc_id)
    return generate_orb_calendar_markdown(events)
