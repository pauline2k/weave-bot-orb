"""FastAPI route definitions."""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from agent.core.schemas import (
    Event,
    ScrapeRequest,
    ScrapeResponse,
    ParseRequest,
    ParseResponse,
    UpdateResponse
)
from agent.core.tasks import task_runner, ParseTask
from agent.integrations.grist import fetch_events_from_grist, update_grist_event
from agent.scraper.orchestrator import ScrapingOrchestrator

router = APIRouter()


@router.get("/calendar", response_model=list[Event])
async def get_calendar(start_date: str) -> list[Event]:
    """
    Return calendar events for the requested week as a JSON array.

    Args:
        start_date: Monday to start the week.

    Returns:
        List of events
    """

    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = start + timedelta(days=7)

        response = await fetch_events_from_grist(
            start=start,
            end=end,
        )
        return response.events

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/calendar/update/{event_id}", response_model=UpdateResponse)
async def update_calendar_event(event_id: int, event: Event) -> UpdateResponse:
    """
    Update  events for the requested week as a JSON array.

    Args:
        event_id: Event id to update.
        event: Event to update.

    Returns:
        List of events
    """

    try:
        success = await update_grist_event(
            event_id=event_id,
            event=event,
        )
        return UpdateResponse(success=success)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_event(request: ScrapeRequest) -> ScrapeResponse:
    """
    Scrape event information from a URL.

    This endpoint:
    1. Fetches the webpage using browser automation
    2. Extracts and cleans the content
    3. Uses an LLM to extract structured event data
    4. Returns the event information in a standardized format

    Args:
        request: ScrapeRequest containing URL and options

    Returns:
        ScrapeResponse with extracted event data or error information
    """
    orchestrator = ScrapingOrchestrator()

    try:
        response = await orchestrator.scrape_event(
            url=str(request.url),
            wait_time=request.wait_time,
            include_screenshot=request.include_screenshot
        )
        return response

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/parse", response_model=ParseResponse)
async def parse_event(request: ParseRequest) -> ParseResponse:
    """
    Async parse event from URL and/or image.

    Unlike /scrape, this endpoint:
    1. Returns immediately with a request_id
    2. Processes the URL/image in the background
    3. POSTs results to callback_url when complete

    Supports three parse modes:
    - "url": Parse from webpage (requires url)
    - "image": Parse from uploaded image (requires image_base64)
    - "hybrid": Parse from both URL and image together

    This is designed for Discord bot integration where we need
    to respond quickly and update the user later.

    Args:
        request: ParseRequest with URL/image and callback_url

    Returns:
        ParseResponse with request_id for tracking
    """
    # Validate required fields based on parse_mode
    if request.parse_mode == "url" and not request.url:
        raise HTTPException(
            status_code=400,
            detail="URL is required for 'url' parse mode"
        )
    if request.parse_mode == "image" and not request.image_base64:
        raise HTTPException(
            status_code=400,
            detail="image_base64 is required for 'image' parse mode"
        )
    if request.parse_mode == "hybrid" and (not request.url or not request.image_base64):
        raise HTTPException(
            status_code=400,
            detail="Both URL and image_base64 are required for 'hybrid' parse mode"
        )

    # Create response with generated request_id
    response = ParseResponse()

    # Submit background task
    task = ParseTask(
        request_id=response.request_id,
        url=str(request.url) if request.url else None,
        callback_url=str(request.callback_url),
        discord_message_id=request.discord_message_id,
        parse_mode=request.parse_mode,
        image_base64=request.image_base64,
        include_screenshot=request.include_screenshot,
        wait_time=request.wait_time
    )

    task_runner.submit(task)

    return response


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Simple status message including active task count
    """
    return {
        "status": "healthy",
        "service": "event-scraper",
        "version": "0.1.0",
        "active_tasks": task_runner.get_active_count()
    }
