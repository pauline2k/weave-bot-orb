"""Utility functions for the Discord bot."""
import re
from typing import Optional


URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)


def extract_url(message: str) -> Optional[str]:
    """
    Extract the first URL from a message.

    Returns None if no URL is found.
    """
    match = URL_PATTERN.search(message)
    return match.group(0) if match else None


def is_link_message(message: str) -> bool:
    """
    Check if a message contains or is a link.

    Returns True if the message contains at least one URL.
    """
    return bool(URL_PATTERN.search(message))
