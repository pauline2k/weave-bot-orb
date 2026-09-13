"""Timezone-aware time utilities.

Centralizes timezone handling so it's consistent and testable.
All event times are assumed Pacific Time unless explicitly stated otherwise.
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PACIFIC = ZoneInfo("America/Los_Angeles")

# Common US timezone abbreviations the LLM may return in the `timezone`
# field (per the schema's own example: "'America/Los_Angeles', 'PST'").
# ZoneInfo can't resolve bare abbreviations directly, so map them to an
# IANA zone name.
_TZ_ABBREVIATIONS = {
    "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PT": "America/Los_Angeles",
    "MST": "America/Denver", "MDT": "America/Denver", "MT": "America/Denver",
    "CST": "America/Chicago", "CDT": "America/Chicago", "CT": "America/Chicago",
    "EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York",
}


def resolve_timezone(timezone_hint: Optional[str]) -> ZoneInfo:
    """Resolve an event's stated timezone (IANA name or common US
    abbreviation) to a ZoneInfo, defaulting to Pacific if unset/unrecognized.
    """
    if timezone_hint:
        hint = timezone_hint.strip()
        try:
            return ZoneInfo(hint)
        except (ZoneInfoNotFoundError, ValueError):
            pass
        mapped = _TZ_ABBREVIATIONS.get(hint.upper())
        if mapped:
            return ZoneInfo(mapped)
    return PACIFIC


def correct_wallclock_offset(dt: Optional[datetime], zone: ZoneInfo = PACIFIC) -> Optional[datetime]:
    """Re-derive the correct UTC offset for a datetime's own wall-clock date.

    The extraction prompt can only hint at "today's" UTC offset (e.g.
    -07:00 during PDT), since it's built before the event's actual date is
    known. That hint is wrong whenever the event falls on the other side of
    a DST transition from today - e.g. scraping in September (PDT, -07:00)
    for a November 15 event, which is Pacific Standard Time (-08:00).

    This keeps the wall-clock date/time the LLM extracted (assumed correct
    - it's what was printed on the page/image) and re-attaches whatever
    offset the IANA tz database says is actually correct for that date,
    rather than trusting the LLM's self-reported offset.

    Only apply this to a raw LLM guess. Do NOT apply it to a datetime whose
    offset is already known-correct for its own absolute instant (e.g. one
    derived from an authoritative JSON-LD/UTC timestamp) - reinterpreting
    its wall-clock digits under a different zone would corrupt it.
    """
    if dt is None:
        return None
    naive = dt.replace(tzinfo=None)
    return naive.replace(tzinfo=zone)


def get_current_time() -> datetime:
    """Return the current time in Pacific Time (DST-aware).

    Uses ZoneInfo for automatic PST/PDT handling:
    - PST (UTC-8): November through March
    - PDT (UTC-7): March through November
    """
    return datetime.now(PACIFIC)


def get_pacific_offset_str() -> str:
    """Return the current Pacific Time UTC offset as a string.

    Returns '-08:00' during PST or '-07:00' during PDT.
    """
    now = get_current_time()
    offset = now.strftime("%z")
    # Format as -08:00 instead of -0800
    return f"{offset[:3]}:{offset[3:]}"
