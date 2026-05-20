"""Post-extraction validation for scraped events.

Validates event data after LLM extraction and JSON-LD overrides.
Validation WARNS (lowers confidence, adds notes) but never rejects.
"""
import logging
from datetime import timedelta

from agent.core.schemas import Event
from agent.core.time_utils import get_current_time, PACIFIC

logger = logging.getLogger(__name__)


def validate_event(event: Event) -> Event:
    """Validate an extracted event, adjusting confidence and adding notes.

    Rules:
    - start_datetime not more than 1 year in the past
    - start_datetime not more than 2 years in the future
    - end_datetime > start_datetime (if both present)
    - If end < start: null out end_datetime and add note
    - If title is empty or "Extraction Failed": lower confidence

    Returns a new Event with adjusted confidence_score and extraction_notes.
    """
    issues = []
    confidence_penalty = 0.0
    event_dict = event.model_dump()
    now = get_current_time()

    # Validate title
    title = event_dict.get("title") or ""
    if not title or title == "Extraction Failed":
        issues.append("Missing or failed title")
        confidence_penalty += 0.3

    # Validate start_datetime
    start = event.start_datetime
    if start is not None:
        # Make start offset-aware if naive (assume Pacific)
        if start.tzinfo is None:
            start = start.replace(tzinfo=PACIFIC)

        one_year_ago = now - timedelta(days=365)
        two_years_ahead = now + timedelta(days=730)

        if start < one_year_ago:
            issues.append(f"Start date {start.date()} is more than 1 year in the past")
            confidence_penalty += 0.2

        if start > two_years_ahead:
            issues.append(f"Start date {start.date()} is more than 2 years in the future")
            confidence_penalty += 0.2

    # Validate end_datetime vs start_datetime
    end = event.end_datetime
    if start is not None and end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=PACIFIC)

        if end < start:
            issues.append(f"End datetime ({end}) is before start datetime ({start}), removing end time")
            event_dict["end_datetime"] = None
            confidence_penalty += 0.1

    # Apply confidence penalty
    current_score = event_dict.get("confidence_score")
    if current_score is None:
        current_score = 0.5
    adjusted_score = max(0.0, current_score - confidence_penalty)
    if confidence_penalty > 0:
        event_dict["confidence_score"] = round(adjusted_score, 2)

    # Append validation notes
    if issues:
        existing_notes = event_dict.get("extraction_notes") or ""
        validation_notes = "Validation: " + "; ".join(issues) + "."
        if existing_notes:
            event_dict["extraction_notes"] = f"{existing_notes} {validation_notes}"
        else:
            event_dict["extraction_notes"] = validation_notes
        logger.info(f"Validation issues for '{title}': {issues}")

    return Event(**event_dict)
