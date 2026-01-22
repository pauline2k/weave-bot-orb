"""Grist integration for saving events to the ORB Events database."""
import aiohttp
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass

from agent.core.schemas import Event
from agent.core.config import settings

logger = logging.getLogger(__name__)

# Grist configuration
GRIST_API_BASE = "https://docs.getgrist.com/api"
GRIST_DOC_ID = getattr(settings, 'grist_doc_id', None) or "b2r9qYM2Lr9xJ2epHVV1K2"
GRIST_TABLE = "Events"
# Short doc ID and page name for UI URLs (different from API doc ID)
GRIST_UI_DOC_ID = "b2r9qYM2Lr9x"
GRIST_UI_PAGE_NAME = "ORB-Events"


@dataclass
class GristResult:
    """Result of a Grist operation."""
    success: bool
    record_id: Optional[int] = None
    record_url: Optional[str] = None
    error: Optional[str] = None


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Format datetime for Grist API.

    We strip timezone info and send naive datetime to prevent Grist
    from converting to UTC. All events are assumed to be Pacific Time.
    """
    if dt is None:
        return None
    # Strip timezone to prevent Grist from converting to UTC
    # The datetime is already in the correct local time (Pacific)
    naive_dt = dt.replace(tzinfo=None)
    return naive_dt.isoformat()


def _event_to_grist_fields(event: Event) -> dict:
    """
    Convert an Event object to Grist record fields.

    Maps our Event schema to the Grist Events table columns.
    """
    fields = {
        "Title": event.title or "Unknown Event",
        "StartDatetime": _format_datetime(event.start_datetime),
        "EndDatetime": _format_datetime(event.end_datetime),
        "Description": event.description,
        "SourceURL": event.source_url,
        "Price": event.price,
        "Tags": ", ".join(event.tags) if event.tags else None,
        "ImageURL": event.image_url,
        "ConfidenceScore": event.confidence_score,
        # Use Pacific Time for CreatedAt (naive datetime, no tz conversion by Grist)
        "CreatedAt": datetime.now(timezone(timedelta(hours=-8))).replace(tzinfo=None).isoformat(),
    }

    # Location fields
    if event.location:
        fields["Venue"] = event.location.venue
        fields["Address"] = event.location.address
        fields["City"] = event.location.city
        fields["LocationType"] = event.location.type

    # Organizer
    if event.organizer:
        fields["OrganizerName"] = event.organizer.name

    # Remove None values (Grist doesn't like them)
    return {k: v for k, v in fields.items() if v is not None}


async def save_event_to_grist(
    event: Event,
    api_key: Optional[str] = None,
    doc_id: Optional[str] = None,
    timeout: float = 15.0
) -> GristResult:
    """
    Save an event to the Grist Events table.

    Args:
        event: Event object to save
        api_key: Grist API key (defaults to settings)
        doc_id: Grist document ID (defaults to ORB Events doc)
        timeout: Request timeout in seconds

    Returns:
        GristResult with success status and record URL if successful
    """
    api_key = api_key or getattr(settings, 'grist_api_key', None)
    doc_id = doc_id or GRIST_DOC_ID

    if not api_key:
        logger.error("No Grist API key configured")
        return GristResult(
            success=False,
            error="Grist API key not configured"
        )

    url = f"{GRIST_API_BASE}/docs/{doc_id}/tables/{GRIST_TABLE}/records"

    fields = _event_to_grist_fields(event)
    payload = {
        "records": [{"fields": fields}]
    }

    logger.info(f"Saving event to Grist: {event.title}")
    logger.debug(f"Grist payload: {payload}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    records = data.get("records", [])

                    if records:
                        record_id = records[0].get("id")
                        # Build URL to the record in Grist
                        # Format: https://oaklog.getgrist.com/DOC_ID/PAGE_NAME#a1.s4.rROW_ID.c0
                        # The anchor format is: a=area, s=section/widget, r=row, c=column
                        # s4 is the Events table widget on the ORB-Events page
                        record_url = f"https://oaklog.getgrist.com/{GRIST_UI_DOC_ID}/{GRIST_UI_PAGE_NAME}#a1.s4.r{record_id}.c0"

                        logger.info(
                            f"Event saved to Grist: record_id={record_id}, "
                            f"url={record_url}"
                        )

                        return GristResult(
                            success=True,
                            record_id=record_id,
                            record_url=record_url
                        )
                    else:
                        return GristResult(
                            success=False,
                            error="No record ID returned from Grist"
                        )
                else:
                    body = await response.text()
                    logger.error(
                        f"Grist API error: status={response.status}, body={body}"
                    )
                    return GristResult(
                        success=False,
                        error=f"Grist API returned {response.status}: {body}"
                    )

    except aiohttp.ClientError as e:
        logger.error(f"Grist connection error: {e}")
        return GristResult(success=False, error=f"Connection error: {e}")
    except Exception as e:
        logger.error(f"Unexpected Grist error: {e}")
        return GristResult(success=False, error=f"Unexpected error: {e}")
