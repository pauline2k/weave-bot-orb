"""Callback sender for async parse results."""
import aiohttp
import logging
from typing import Optional

from agent.core.schemas import CallbackPayload, Event

logger = logging.getLogger(__name__)


async def send_callback(
    callback_url: str,
    request_id: str,
    discord_message_id: Optional[int],
    status: str,
    event: Optional[Event] = None,
    error: Optional[str] = None,
    result_url: Optional[str] = None,
    grist_record_id: Optional[int] = None,
    timeout: float = 10.0
) -> bool:
    """
    Send parsing results to the callback URL.

    Args:
        callback_url: URL to POST results to
        request_id: Unique request identifier
        discord_message_id: Discord message ID (passed through)
        status: "completed" or "failed"
        event: Extracted event data (if successful)
        error: Error message (if failed)
        result_url: URL to saved record (Grist)
        grist_record_id: Grist row ID for editorial updates
        timeout: Request timeout in seconds

    Returns:
        True if callback was sent successfully, False otherwise
    """
    payload = CallbackPayload(
        request_id=request_id,
        discord_message_id=discord_message_id,
        status=status,
        event=event,
        error=error,
        result_url=result_url,
        grist_record_id=grist_record_id
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                callback_url,
                json=payload.model_dump(mode='json'),
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    logger.info(
                        f"Callback sent successfully for request {request_id}"
                    )
                    return True
                else:
                    body = await response.text()
                    logger.error(
                        f"Callback failed for request {request_id}: "
                        f"status={response.status}, body={body}"
                    )
                    return False

    except aiohttp.ClientError as e:
        logger.error(f"Callback connection error for request {request_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected callback error for request {request_id}: {e}")
        return False
