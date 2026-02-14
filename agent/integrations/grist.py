"""Grist integration for saving events to the ORB Events database."""
import aiohttp
import json
import logging
import urllib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

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
    events: Optional[list] = field(default_factory=list)
    error: Optional[str] = None

def _format_datetime_input(dt: Optional[datetime]) -> Optional[str]:
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

def _format_datetime_output(timestamp: Optional[str]) -> Optional[str]:
    """
    Reverse the transformation above, from Unix timestamp to Pacific time. Note that at present Grist is
    internally storing the event time incorrectly (as a Unix timestamp, parsing the naive portion of Pacific
    time as if it were UTC), but as long as we reverse the incorrect operation on the way out it should be
    consistent.
    """
    if timestamp is None:
        return None

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.replace(tzinfo=ZoneInfo('America/Los_Angeles')).isoformat()

def _event_to_grist_fields(event: Event) -> dict:
    """
    Convert an Event object to Grist record fields.

    Maps our Event schema to the Grist Events table columns.
    """
    fields = {
        "Title": event.title or "Unknown Event",
        "StartDatetime": _format_datetime_input(event.start_datetime),
        "EndDatetime": _format_datetime_input(event.end_datetime),
        "Description": event.description,
        "SourceURL": event.source_url,
        "Source_URL_Provider": event.source_url_provider,
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
        fields["Neighborhood"] = event.location.neighborhood
        fields["City"] = event.location.city
        fields["LocationType"] = event.location.type

    # Organizer
    if event.organizer:
        fields["OrganizerName"] = event.organizer.name

    # Calendar metadata
    if event.calendar_metadata:
        fields["Deleted"] = event.calendar_metadata.deleted
        fields["Incoming"] = event.calendar_metadata.incoming
        fields["Supplemental"] = event.calendar_metadata.supplemental

    # Remove None values (Grist doesn't like them)
    return {k: v for k, v in fields.items() if v is not None}


def _grist_record_to_event(record: dict) -> Event:
    """
    Convert Grist record to Event object.

    Maps Grist Events table columns to our Event schema.
    """
    event = record.get('fields', {})

    location = {
        'venue': event.get('Venue'),
        'address': event.get('Address'),
        'neighborhood': event.get('Neighborhood'),
        'city': event.get('City'),
    }

    if event.get('LocationType'):
        location['type'] = event['LocationType']

    properties = {
        'title': event.get('Title') or 'Untitled Event',
        'description': event.get('Description') or '',
        'start_datetime': _format_datetime_output(event.get('StartDatetime')),
        'end_datetime': _format_datetime_output(event.get('StartDatetime')),
        'timezone': 'America/Los_Angeles',
        'location': location,
        'source_url': event.get('SourceURL'),
        'source_url_provider': event.get('Source_URL_Provider'),
        'price': event.get('Price'),
        'tags': list(filter(None, event.get('Tags', '').split(', '))),
        'image_url': event.get('ImageURL'),
        'confidence_score': event.get('ConfidenceScore'),
        'grist_record_id': event.get('id'),
    }

    if event.get('OrganizerName'):
        properties['organizer'] = {
            'name': event['OrganizerName'],
        }

    return Event(**properties)


async def fetch_events_from_grist(
    start: datetime,
    end: datetime,
    api_key: Optional[str] = None,
    doc_id: Optional[str] = None,
    timeout: float = 15.0,
) -> GristResult:
    """
    Read events from the Grist Events table.

    Args:
        start: Lower limit for event start time
        end: Upper limit for event start time
        api_key: Grist API key (defaults to settings)
        doc_id: Grist document ID (defaults to ORB Events doc)
        timeout: Request timeout in seconds

    Returns:
        GristResult with an array of Event objects
    """
    api_key = api_key or getattr(settings, 'grist_api_key', None)
    doc_id = doc_id or GRIST_DOC_ID

    if not api_key:
        logger.error("No Grist API key configured")
        return GristResult(
            success=False,
            error="Grist API key not configured"
        )

    url = f"{GRIST_API_BASE}/docs/{doc_id}/sql"
    sql = f"select * from Events where StartDatetime >= ? and StartDatetime <= ? order by StartDatetime"
    payload = {
        'sql': sql,
        'args': [start.timestamp(), end.timestamp()],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    records = data.get("records", [])
                    return GristResult(
                        success=True,
                        events=[_grist_record_to_event(record) for record in records],
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


async def update_grist_event(
    event_id: int,
    event: Event,
    api_key: Optional[str] = None,
    doc_id: Optional[str] = None,
    timeout: float = 15.0
) -> bool:
    """
    Update a specific record in grist.

    Args:
        event: update event fields

    Returns:
        True if successful, False otherwise
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
        "records": [
            {
                "id": event_id,
                "fields": fields
            }
        ]
    }

    logger.info(f"Updating Grist event id {event_id}: {event.title}")
    logger.debug(f"Grist payload: {payload}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    return True
                else:
                    body = await response.text()
                    logger.error(
                        f"Grist API error updating event: "
                        f"status={response.status}, body={body}"
                    )
                    return False

    except aiohttp.ClientError as e:
        logger.error(f"Grist connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating Grist: {e}")
        return False
