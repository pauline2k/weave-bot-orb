"""Utility functions for the Discord bot."""
import re
from typing import Optional
import discord


URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# Supported image MIME types for event parsing
SUPPORTED_IMAGE_TYPES = {
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/webp',
    'image/heic',
}


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


def has_image_attachments(message: discord.Message) -> bool:
    """
    Check if a Discord message has image attachments.

    Returns True if the message has at least one supported image attachment.
    """
    return any(
        att.content_type and att.content_type.lower() in SUPPORTED_IMAGE_TYPES
        for att in message.attachments
    )


def extract_image_attachments(message: discord.Message) -> list[dict]:
    """
    Extract image attachment info from a Discord message.

    Returns a list of dicts with url, filename, and content_type for each image.
    """
    images = []
    for att in message.attachments:
        if att.content_type and att.content_type.lower() in SUPPORTED_IMAGE_TYPES:
            images.append({
                'url': att.url,
                'filename': att.filename,
                'content_type': att.content_type,
                'size': att.size,
            })
    return images
