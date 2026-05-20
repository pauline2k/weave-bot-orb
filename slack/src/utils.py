"""Utility functions for the Slack bot."""
import re
from typing import Optional, List


URL_PATTERN = re.compile(
    r'<(http[s]?://[^|>]+)(?:\|[^>]+)?>'  # Slack-formatted URLs: <url|label> or <url>
)

RAW_URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# Supported image MIME types
SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


def extract_urls(text: str) -> List[str]:
    """Extract all URLs from Slack message text.

    Slack wraps URLs in angle brackets: <https://example.com|label>
    """
    # First try Slack-formatted URLs
    urls = URL_PATTERN.findall(text)
    if urls:
        return urls

    # Fallback to raw URLs (e.g. in unfurled content)
    return RAW_URL_PATTERN.findall(text)


def extract_first_url(text: str) -> Optional[str]:
    """Extract the first URL from message text."""
    urls = extract_urls(text)
    return urls[0] if urls else None


def has_urls(text: str) -> bool:
    """Check if message text contains URLs."""
    return bool(URL_PATTERN.search(text) or RAW_URL_PATTERN.search(text))


def get_image_files(files: list) -> List[dict]:
    """Filter Slack file objects to supported images."""
    images = []
    for f in files or []:
        mimetype = f.get("mimetype", "")
        if mimetype in SUPPORTED_IMAGE_TYPES:
            images.append({
                "url": f.get("url_private"),
                "filename": f.get("name"),
                "mimetype": mimetype,
                "size": f.get("size", 0),
            })
    return images
