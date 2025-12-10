"""Data schemas for events and API requests/responses."""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, HttpUrl, Field
import uuid


class EventLocation(BaseModel):
    """Location information for an event."""
    type: Literal["physical", "virtual", "hybrid"] = "physical"
    venue: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    url: Optional[str] = None


class EventOrganizer(BaseModel):
    """Organizer information for an event."""
    name: Optional[str] = None
    contact: Optional[str] = None
    url: Optional[str] = None


class Event(BaseModel):
    """Structured event data extracted from a webpage or image."""
    title: str = "Unknown Event"  # Default fallback if LLM returns null
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    timezone: Optional[str] = None
    location: Optional[EventLocation] = None
    organizer: Optional[EventOrganizer] = None
    registration_url: Optional[str] = None
    price: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    source_url: Optional[str] = None  # The URL we scraped from (optional for image-only)
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="LLM's confidence in the extraction quality"
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Any issues, warnings, or notes about the extraction"
    )


class ScrapeRequest(BaseModel):
    """Request to scrape an event from a URL."""
    url: HttpUrl
    include_screenshot: bool = True
    wait_time: int = Field(
        default=3000,
        ge=0,
        le=30000,
        description="Time to wait for page load in milliseconds"
    )


class ScrapeResponse(BaseModel):
    """Response from scraping operation."""
    success: bool
    event: Optional[Event] = None
    error: Optional[str] = None
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata about the scraping process"
    )


# --- Async parsing schemas (for Discord integration) ---

class ParseRequest(BaseModel):
    """
    Async request to parse an event from a URL and/or image.

    Unlike ScrapeRequest, this returns immediately with a request_id
    and sends results via callback when complete.

    Supports three modes:
    - "url": Parse event from a webpage (default, existing behavior)
    - "image": Parse event from an uploaded image (flyer, poster, screenshot)
    - "hybrid": Parse from both URL and image together
    """
    url: Optional[HttpUrl] = Field(
        default=None,
        description="URL to scrape (required for 'url' and 'hybrid' modes)"
    )
    callback_url: HttpUrl = Field(
        description="URL to POST results when parsing completes"
    )
    discord_message_id: Optional[int] = Field(
        default=None,
        description="Discord message ID for tracking (passed through to callback)"
    )
    parse_mode: Literal["url", "image", "hybrid"] = Field(
        default="url",
        description="Parsing mode: 'url' for webpage, 'image' for uploaded image, 'hybrid' for both"
    )
    image_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded image data (required for 'image' and 'hybrid' modes)"
    )
    include_screenshot: bool = True
    wait_time: int = Field(
        default=3000,
        ge=0,
        le=30000,
        description="Time to wait for page load in milliseconds"
    )


class ParseResponse(BaseModel):
    """
    Immediate response from async parse request.

    The actual parsing happens in background; results sent via callback.
    """
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this parse request"
    )
    status: Literal["accepted", "rejected"] = "accepted"
    message: str = "Request accepted, processing in background"


class CallbackPayload(BaseModel):
    """
    Payload sent to callback_url when parsing completes.

    For now, result_url is None (event data returned directly).
    Future: result_url will point to Grist record after integration.
    """
    request_id: str
    discord_message_id: Optional[int] = None
    status: Literal["completed", "failed"]
    event: Optional[Event] = None
    error: Optional[str] = None
    result_url: Optional[str] = Field(
        default=None,
        description="URL to saved event record (Grist)"
    )
    grist_record_id: Optional[int] = Field(
        default=None,
        description="Grist row ID for the saved event (for editorial updates)"
    )
