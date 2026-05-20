"""Timezone-aware time utilities.

Centralizes timezone handling so it's consistent and testable.
All event times are assumed Pacific Time unless explicitly stated otherwise.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


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
