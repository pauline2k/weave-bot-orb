"""Calendar export functionality - fetch events from Grist and format for ORB."""
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from src.config import Config

logger = logging.getLogger(__name__)


def get_orb_week_range() -> tuple[datetime, datetime]:
    """
    Get the date range for the ORB calendar week.

    ORB skips Monday, so the week runs Tuesday through Sunday.
    Returns the upcoming Tuesday through the following Sunday.

    Returns:
        Tuple of (start_date, end_date) as datetime objects
        start_date is midnight on Tuesday, end_date is 23:59:59 on Sunday
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_weekday = today.weekday()  # Monday=0, Tuesday=1, ..., Sunday=6

    # Find the next Tuesday (weekday=1)
    # If today is Monday (0), next Tuesday is in 1 day
    # If today is Tuesday (1), we include this Tuesday
    # If today is Wednesday-Sunday (2-6), we go to next week's Tuesday
    if current_weekday == 0:  # Monday
        days_until_tuesday = 1
    elif current_weekday == 1:  # Tuesday
        days_until_tuesday = 0  # Include today
    else:  # Wednesday through Sunday
        days_until_tuesday = (8 - current_weekday)  # Days until next Tuesday

    start_date = today + timedelta(days=days_until_tuesday)

    # End date is the Sunday after that Tuesday (5 days later)
    end_date = start_date + timedelta(days=5)
    # Set end_date to end of day
    end_date = end_date.replace(hour=23, minute=59, second=59)

    return start_date, end_date

# Grist API configuration
GRIST_API_BASE = "https://docs.getgrist.com/api"


async def fetch_events_from_grist(
    api_key: str,
    doc_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> list[dict]:
    """
    Fetch events from Grist, optionally filtered by date range.

    Args:
        api_key: Grist API key
        doc_id: Grist document ID
        start_date: Optional start of date range (inclusive)
        end_date: Optional end of date range (inclusive)

    Returns:
        List of event dictionaries within the date range
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

                    # Convert timestamps for filtering
                    start_ts = start_date.timestamp() if start_date else None
                    end_ts = end_date.timestamp() if end_date else None

                    # Convert to simpler format and filter by date range
                    events = []
                    for record in records:
                        fields = record.get("fields", {})
                        event_ts = fields.get("StartDatetime")

                        # Skip events without a valid date (TBD events)
                        if not event_ts:
                            continue

                        # Apply date filter if specified
                        if start_ts and end_ts:
                            if not (start_ts <= event_ts <= end_ts):
                                continue
                        elif start_ts:
                            if event_ts < start_ts:
                                continue
                        elif end_ts:
                            if event_ts > end_ts:
                                continue

                        events.append({
                            "id": record.get("id"),
                            "title": fields.get("Title"),
                            "start_datetime": event_ts,
                            "venue": fields.get("Venue"),
                            "address": fields.get("Address"),
                            "city": fields.get("City"),
                            "description": fields.get("Description"),
                            "source_url": fields.get("SourceURL"),
                            "price": fields.get("Price"),
                            "editorial": fields.get("Editorial"),
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


def generate_orb_calendar_markdown(
    events: list[dict],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> str:
    """
    Generate ORB-style calendar markdown from events.

    Format:
    ## Tuesday, Nov 18

    **6:30pm, Books Inc. Alameda (The Island)**. Description. [[tickets](url)]

    Args:
        events: List of event dictionaries
        start_date: Start of date range (for display in header)
        end_date: End of date range (for display in header)

    Returns:
        Markdown string ready for copy-paste
    """
    if not events:
        if start_date and end_date:
            return (
                f"No events found for {start_date.strftime('%b %d')} - "
                f"{end_date.strftime('%b %d')}."
            )
        return "No events found."

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
            title = event.get("title") or "Untitled Event"
            time_str = event["time_str"]
            venue = event.get("venue") or "Location TBD"

            # Build event line: **Title**, time, venue. Editorial. [[link]]
            event_line = f"**{title}**, {time_str}, {venue}."

            # Only show editorial text (human-written commentary)
            editorial = event.get("editorial")
            if editorial:
                event_line += f" {editorial}"

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

    For ORB, this returns events for the upcoming week (Tuesday through Sunday).

    Args:
        grist_api_key: Grist API key
        grist_doc_id: Grist document ID

    Returns:
        Formatted markdown string
    """
    # Get the ORB week range (Tuesday through Sunday)
    start_date, end_date = get_orb_week_range()

    logger.info(
        f"Fetching events for ORB week: {start_date.strftime('%Y-%m-%d')} "
        f"to {end_date.strftime('%Y-%m-%d')}"
    )

    events = await fetch_events_from_grist(
        grist_api_key, grist_doc_id,
        start_date=start_date,
        end_date=end_date
    )
    return generate_orb_calendar_markdown(events, start_date, end_date)
