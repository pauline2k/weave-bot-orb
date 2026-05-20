"""Slack bot for parsing event links and images."""
import base64
import logging
from typing import Optional

import aiohttp
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from src.config import Config
from src.utils import extract_first_url, has_urls, get_image_files

logger = logging.getLogger(__name__)


class SlackEventBot:
    """Slack bot that monitors channels for event links and images."""

    def __init__(self, app: AsyncApp):
        self.app = app
        self.agent_api_url = Config.AGENT_API_URL
        self.org_id = Config.ORG_ID
        self.monitored_channels = set(Config.SLACK_CHANNELS)

        if Config.CALLBACK_URL:
            self.callback_url = Config.CALLBACK_URL
        else:
            self.callback_url = f"http://{Config.WEBHOOK_HOST}:{Config.WEBHOOK_PORT}/callback"

        # Register message handler
        self.app.event("message")(self._handle_message)

    async def _handle_message(self, event: dict, client: AsyncWebClient, say):
        """Handle incoming Slack messages."""
        # Ignore bot messages and message_changed events
        if event.get("bot_id") or event.get("subtype"):
            return

        channel = event.get("channel", "")
        if channel not in self.monitored_channels:
            return

        text = event.get("text", "")
        files = event.get("files", [])
        message_ts = event.get("ts", "")

        # Check for parseable content
        url = extract_first_url(text) if has_urls(text) else None
        images = get_image_files(files)

        if not url and not images:
            return

        # Determine parse mode
        if url and images:
            parse_mode = "hybrid"
            target_desc = f"link + {len(images)} image(s)"
        elif images:
            parse_mode = "image"
            target_desc = f"{len(images)} image(s)"
        else:
            parse_mode = "url"
            target_desc = "event link"

        logger.info(f"Processing message {message_ts} ({parse_mode}): url={url}, images={len(images)}")

        # Send initial reply in thread
        result = await client.chat_postMessage(
            channel=channel,
            thread_ts=message_ts,
            text=f"Parsing {target_desc}...",
        )
        response_ts = result["ts"]

        # Download image if present
        image_b64 = None
        if images:
            image_b64 = await self._download_image(images[0]["url"], client)
            if not image_b64:
                logger.warning(f"Failed to download image for message {message_ts}")
                if parse_mode == "image":
                    await client.chat_update(
                        channel=channel,
                        ts=response_ts,
                        text="Sorry, I couldn't download that image. Could you try uploading it again?",
                    )
                    return
                parse_mode = "url"

        # Send to agent
        agent_id = await self._send_to_agent(
            url=url,
            reference_id=f"{channel}:{message_ts}:{response_ts}",
            parse_mode=parse_mode,
            image_b64=image_b64,
        )

        if not agent_id:
            await client.chat_update(
                channel=channel,
                ts=response_ts,
                text="Hmm, I'm having trouble connecting right now. Mind trying again in a moment?",
            )

    async def _download_image(self, url: str, client: AsyncWebClient) -> Optional[str]:
        """Download a Slack-hosted image and return as base64."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.read()
                        if len(data) > 10 * 1024 * 1024:
                            logger.warning(f"Image too large: {len(data)} bytes")
                            return None
                        return base64.b64encode(data).decode("utf-8")
                    else:
                        logger.error(f"Failed to download image: status {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def _send_to_agent(
        self,
        url: Optional[str],
        reference_id: str,
        parse_mode: str = "url",
        image_b64: Optional[str] = None,
    ) -> Optional[str]:
        """Send parse request to agent API. Returns agent request_id or None."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "callback_url": self.callback_url,
                    "client_reference_id": reference_id,
                    "org_id": self.org_id,
                    "parse_mode": parse_mode,
                }

                if url:
                    payload["url"] = url
                if image_b64:
                    payload["image_base64"] = image_b64

                log_payload = {**payload}
                if image_b64:
                    log_payload["image_base64"] = f"<{len(image_b64)} chars>"
                logger.info(f"Sending to agent: {log_payload}")

                async with session.post(
                    self.agent_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("request_id")
                    else:
                        logger.error(
                            f"Agent API returned status {response.status}: "
                            f"{await response.text()}"
                        )
                        return None

        except Exception as e:
            logger.error(f"Error calling agent API: {e}")
            return None

    async def handle_parse_complete(
        self,
        client_reference_id: str,
        status: str,
        event: Optional[dict] = None,
        error: Optional[str] = None,
        result_url: Optional[str] = None,
        grist_record_id: Optional[int] = None,
    ):
        """Handle agent callback — update Slack message with results."""
        # Parse reference: "channel:message_ts:response_ts"
        parts = client_reference_id.split(":")
        if len(parts) != 3:
            logger.error(f"Invalid client_reference_id format: {client_reference_id}")
            return

        channel, message_ts, response_ts = parts

        try:
            client = self.app.client

            if status == "completed" and event:
                text = self._format_event_reply(event, result_url)
            elif status == "completed" and result_url:
                text = f"All set! I've added your event: {result_url}"
            else:
                error_msg = error or "Unknown error"
                text = (
                    f"I couldn't parse that link. {error_msg}\n"
                    "Could you double-check it's an event link and try again?"
                )

            await client.chat_update(
                channel=channel,
                ts=response_ts,
                text=text,
            )

            logger.info(f"Updated Slack message for reference {client_reference_id}")

        except Exception as e:
            logger.error(f"Error handling parse completion: {e}")

    def _format_event_reply(self, event: dict, result_url: Optional[str] = None) -> str:
        """Format event data into a Slack message."""
        lines = []

        title = event.get("title", "Unknown Event")
        lines.append(f"*{title}*")

        start = event.get("start_datetime")
        if start:
            lines.append(f"When: {start}")

        location = event.get("location")
        if location:
            venue = location.get("venue")
            address = location.get("address")
            if venue and address:
                lines.append(f"Where: {venue}, {address}")
            elif venue:
                lines.append(f"Where: {venue}")
            elif address:
                lines.append(f"Where: {address}")

        description = event.get("description")
        if description:
            if len(description) > 200:
                description = description[:197] + "..."
            lines.append(f"\n{description}")

        price = event.get("price")
        if price:
            lines.append(f"Price: {price}")

        if result_url:
            lines.append(f"\nSaved to: {result_url}")

        confidence = event.get("confidence_score")
        if confidence and confidence < 0.7:
            lines.append("\n_Note: Some details may be incomplete_")

        return "\n".join(lines)
