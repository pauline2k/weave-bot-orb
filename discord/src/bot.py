"""Discord bot for parsing event links and images."""
import base64
import discord
from discord.ext import commands
import aiohttp
import logging
from typing import Optional

from src.config import Config
from src.database import Database, ParseStatus
from src.utils import is_link_message, extract_url, has_image_attachments, extract_image_attachments
from src.calendar import get_calendar_export

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeaveBotClient(discord.Client):
    def __init__(self, db: Database):
        # Request MESSAGE_CONTENT intent to see message content
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)
        self.db = db
        self.agent_api_url = Config.AGENT_API_URL
        self.monitored_channels = set(Config.DISCORD_CHANNELS)

        # Callback URL for agent to POST results back
        # Use explicit CALLBACK_URL if set (for Railway), otherwise build from host/port
        if Config.CALLBACK_URL:
            self.callback_url = Config.CALLBACK_URL
        else:
            self.callback_url = f"http://{Config.WEBHOOK_HOST}:{Config.WEBHOOK_PORT}/callback"

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f'Bot logged in as {self.user}')
        logger.info(f'Monitoring channels: {self.monitored_channels}')

    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Only process messages in monitored channels
        if message.channel.id not in self.monitored_channels:
            return

        # Check for !calendar command
        if message.content.strip().lower() == "!calendar":
            await self._handle_calendar_command(message)
            return

        # Check if this is a reply to a bot message (for editorial updates)
        if message.reference and message.reference.message_id:
            await self._handle_potential_editorial_reply(message)
            # Don't return - it might also contain a link or image to parse

        # Check for parseable content: URL or images
        url = extract_url(message.content) if is_link_message(message.content) else None
        images = extract_image_attachments(message)

        # Nothing to parse
        if not url and not images:
            return

        # Determine parse mode and what we're processing
        if url and images:
            parse_mode = "hybrid"
            target_desc = f"link + {len(images)} image(s)"
        elif images:
            parse_mode = "image"
            target_desc = f"{len(images)} image(s)"
        else:
            parse_mode = "url"
            target_desc = "event link"

        logger.info(f'Processing message {message.id} ({parse_mode}): url={url}, images={len(images)}')

        # Send initial response
        response = await message.reply(f"⏳ Parsing {target_desc}...")

        # Store in database
        await self.db.create_request(
            discord_message_id=message.id,
            discord_response_id=response.id
        )

        # Download image if present (use first image for now)
        image_b64 = None
        if images:
            image_b64 = await self._download_image(images[0]['url'])
            if not image_b64:
                logger.warning(f'Failed to download image for message {message.id}')
                if parse_mode == "image":
                    # Image-only mode but download failed
                    await response.edit(content="Sorry, I couldn't download that image. Could you try uploading it again?")
                    return
                # For hybrid mode, continue with URL only
                parse_mode = "url"

        # Send to agent API
        try:
            agent_id = await self._send_to_agent(
                url=url,
                message_id=message.id,
                parse_mode=parse_mode,
                image_b64=image_b64
            )

            if agent_id:
                # Update database with agent ID
                await self.db.update_agent_id(message.id, agent_id)
                logger.info(f'Message {message.id} sent to agent with ID {agent_id}')
            else:
                # Update response to show error
                await response.edit(content="Hmm, I'm having trouble connecting right now. Mind trying again in a moment?")
                await self.db.update_status(
                    agent_request_id=str(message.id),
                    status=ParseStatus.FAILED
                )

        except Exception as e:
            logger.error(f'Error processing message {message.id}: {e}')
            await response.edit(content="Hmm, I'm having trouble connecting right now. Mind trying again in a moment?")

    async def _download_image(self, image_url: str) -> Optional[str]:
        """
        Download an image from a URL and return it as base64.

        Args:
            image_url: URL to download the image from (Discord CDN)

        Returns:
            Base64-encoded image data, or None if download failed.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    image_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        # Check size - limit to 10MB for safety
                        if len(image_bytes) > 10 * 1024 * 1024:
                            logger.warning(f'Image too large: {len(image_bytes)} bytes')
                            return None
                        return base64.b64encode(image_bytes).decode('utf-8')
                    else:
                        logger.error(f'Failed to download image: status {response.status}')
                        return None
        except aiohttp.ClientError as e:
            logger.error(f'Error downloading image: {e}')
            return None
        except Exception as e:
            logger.error(f'Unexpected error downloading image: {e}')
            return None

    async def _send_to_agent(
        self,
        url: Optional[str],
        message_id: int,
        parse_mode: str = "url",
        image_b64: Optional[str] = None
    ) -> Optional[str]:
        """
        Send parse request to agent API.

        The agent will:
        1. Return a request_id immediately
        2. Process the URL/image in the background
        3. POST results to our callback_url when done

        Args:
            url: URL to parse (optional for image-only mode)
            message_id: Discord message ID for tracking
            parse_mode: "url", "image", or "hybrid"
            image_b64: Base64-encoded image data (for image/hybrid modes)

        Returns the agent request ID if successful, None otherwise.
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "callback_url": self.callback_url,
                    "discord_message_id": message_id,
                    "parse_mode": parse_mode
                }

                if url:
                    payload["url"] = url
                if image_b64:
                    payload["image_base64"] = image_b64

                # Log payload without the full base64 data
                log_payload = {**payload}
                if image_b64:
                    log_payload["image_base64"] = f"<{len(image_b64)} chars>"
                logger.info(f'Sending to agent: {log_payload}')

                async with session.post(
                    self.agent_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)  # Longer timeout for image uploads
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Expecting response like: {"request_id": "abc-123", "status": "accepted"}
                        return data.get("request_id")
                    else:
                        logger.error(
                            f'Agent API returned status {response.status}: '
                            f'{await response.text()}'
                        )
                        return None

        except aiohttp.ClientError as e:
            logger.error(f'Error calling agent API: {e}')
            return None
        except Exception as e:
            logger.error(f'Unexpected error calling agent API: {e}')
            return None

    async def handle_parse_complete(
        self,
        agent_request_id: str,
        status: str,
        event: Optional[dict] = None,
        error: Optional[str] = None,
        result_url: Optional[str] = None,
        grist_record_id: Optional[int] = None
    ):
        """
        Handle completion callback from the agent.

        This is called by the webhook when the agent finishes parsing.

        Args:
            agent_request_id: Unique ID from the agent
            status: "completed" or "failed"
            event: Extracted event data (if successful)
            error: Error message (if failed)
            result_url: URL to saved record (Grist link)
            grist_record_id: Grist row ID for editorial updates
        """
        # Update database
        parse_status = ParseStatus.COMPLETED if status == "completed" else ParseStatus.FAILED
        request = await self.db.update_status(
            agent_request_id,
            parse_status,
            result_url
        )

        # Store grist_record_id if provided
        if grist_record_id:
            await self.db.update_grist_record_id(agent_request_id, grist_record_id)

        if not request:
            logger.error(f'No request found for agent ID {agent_request_id}')
            return

        # Get the original Discord response message
        try:
            # Find channel (assuming we can access it from any monitored channel)
            channel = None
            response_message = None
            for channel_id in self.monitored_channels:
                try:
                    channel = await self.fetch_channel(channel_id)
                    # Try to fetch the message from this channel
                    response_message = await channel.fetch_message(request.discord_response_id)
                    break
                except (discord.NotFound, discord.Forbidden):
                    continue

            if not channel or not response_message:
                logger.error(
                    f'Could not find response message {request.discord_response_id}'
                )
                return

            # Delete the old "Parsing..." message
            await response_message.delete()

            # Get original message to reply to
            original_message = await channel.fetch_message(request.discord_message_id)

            # Send completion message and track the new message ID for reply detection
            final_reply = None
            if parse_status == ParseStatus.COMPLETED and event:
                # Format event data for Discord
                reply_content = self._format_event_reply(event, result_url)
                final_reply = await original_message.reply(reply_content)
            elif parse_status == ParseStatus.COMPLETED and result_url:
                # Grist link without event details
                final_reply = await original_message.reply(
                    f"All set! I've added your event: {result_url}"
                )
            else:
                # Failed
                error_msg = error or "Unknown error"
                final_reply = await original_message.reply(
                    f"I couldn't parse that link. {error_msg}\n"
                    "Could you double-check it's an event link and try again?"
                )

            # Update database with the new reply message ID for editorial reply detection
            if final_reply:
                await self.db.update_response_id(agent_request_id, final_reply.id)

            logger.info(f'Completed processing for agent request {agent_request_id}')

        except discord.NotFound:
            logger.error(f'Message {request.discord_response_id} not found')
        except discord.Forbidden:
            logger.error(f'No permission to access message {request.discord_response_id}')
        except Exception as e:
            logger.error(f'Error handling parse completion: {e}')

    async def _handle_potential_editorial_reply(self, message: discord.Message):
        """
        Check if this message is a reply to a parsed event and update editorial text.

        When a user replies to the bot's event confirmation message, their reply
        text becomes the editorial commentary in Grist.
        """
        try:
            # Get the message being replied to
            replied_to_id = message.reference.message_id

            # Check if the replied-to message is one of our event responses
            request = await self.db.get_by_response_id(replied_to_id)

            if not request:
                # Not a reply to an event we parsed
                return

            if not request.grist_record_id:
                logger.warning(
                    f"Reply to event message {replied_to_id} but no grist_record_id stored"
                )
                return

            # Get the editorial text (the user's reply content)
            editorial_text = message.content.strip()

            if not editorial_text:
                return

            logger.info(
                f"Updating editorial for grist_record_id={request.grist_record_id}: "
                f"{editorial_text[:50]}..."
            )

            # Update Grist
            success = await self._update_grist_editorial(
                request.grist_record_id,
                editorial_text
            )

            if success:
                # React to confirm the update
                await message.add_reaction("✅")
                logger.info(f"Editorial updated for record {request.grist_record_id}")
            else:
                await message.add_reaction("❌")
                await message.reply(
                    "Sorry, I couldn't update the editorial text. Please try again.",
                    delete_after=10
                )

        except Exception as e:
            logger.error(f"Error handling editorial reply: {e}")

    async def _update_grist_editorial(
        self,
        record_id: int,
        editorial_text: str
    ) -> bool:
        """
        Update the Editorial field in Grist for a specific record.

        Args:
            record_id: Grist row ID
            editorial_text: Text to set as editorial

        Returns:
            True if successful, False otherwise
        """
        grist_api_key = Config.GRIST_API_KEY
        grist_doc_id = Config.GRIST_DOC_ID

        if not grist_api_key or not grist_doc_id:
            logger.error("Grist not configured for editorial update")
            return False

        url = f"https://docs.getgrist.com/api/docs/{grist_doc_id}/tables/Events/records"

        payload = {
            "records": [
                {
                    "id": record_id,
                    "fields": {
                        "Editorial": editorial_text
                    }
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {grist_api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return True
                    else:
                        body = await response.text()
                        logger.error(
                            f"Grist API error updating editorial: "
                            f"status={response.status}, body={body}"
                        )
                        return False

        except aiohttp.ClientError as e:
            logger.error(f"Grist connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating Grist: {e}")
            return False

    async def _handle_calendar_command(self, message: discord.Message):
        """
        Handle the !calendar command - export events from Grist as ORB markdown.
        """
        logger.info(f"Calendar export requested by {message.author}")

        # Check if Grist is configured
        grist_api_key = Config.GRIST_API_KEY
        grist_doc_id = Config.GRIST_DOC_ID

        if not grist_api_key or not grist_doc_id:
            await message.reply("Grist is not configured. Set GRIST_API_KEY and GRIST_DOC_ID.")
            return

        # Send initial response
        response = await message.reply("📅 Generating calendar export...")

        try:
            # Fetch and format events
            markdown = await get_calendar_export(grist_api_key, grist_doc_id)

            # Discord has a 2000 char limit, so we may need to split
            if len(markdown) <= 1900:
                await response.edit(content=f"```markdown\n{markdown}\n```")
            else:
                # Split into chunks
                await response.edit(content="Calendar export (split due to length):")

                # Split by day sections
                chunks = []
                current_chunk = ""
                for line in markdown.split("\n"):
                    if len(current_chunk) + len(line) + 1 > 1800:
                        chunks.append(current_chunk)
                        current_chunk = line
                    else:
                        current_chunk += "\n" + line if current_chunk else line
                if current_chunk:
                    chunks.append(current_chunk)

                for chunk in chunks:
                    await message.channel.send(f"```markdown\n{chunk}\n```")

            logger.info(f"Calendar export completed, {len(markdown)} chars")

        except Exception as e:
            logger.error(f"Error generating calendar: {e}")
            await response.edit(content="Sorry, there was an error generating the calendar export.")

    def _format_event_reply(self, event: dict, result_url: Optional[str] = None) -> str:
        """
        Format event data into a nice Discord message.

        Args:
            event: Event data dict from agent
            result_url: Optional link to saved record (future: Grist)

        Returns:
            Formatted string for Discord reply
        """
        lines = []

        # Title
        title = event.get('title', 'Unknown Event')
        lines.append(f"**{title}**")

        # Date/time
        start = event.get('start_datetime')
        if start:
            # Format datetime nicely
            lines.append(f"When: {start}")

        # Location
        location = event.get('location')
        if location:
            venue = location.get('venue')
            address = location.get('address')
            if venue and address:
                lines.append(f"Where: {venue}, {address}")
            elif venue:
                lines.append(f"Where: {venue}")
            elif address:
                lines.append(f"Where: {address}")

        # Description (truncated)
        description = event.get('description')
        if description:
            # Truncate long descriptions
            if len(description) > 200:
                description = description[:197] + "..."
            lines.append(f"\n{description}")

        # Price
        price = event.get('price')
        if price:
            lines.append(f"Price: {price}")

        # Result URL (future: Grist link)
        if result_url:
            lines.append(f"\nSaved to: {result_url}")

        # Confidence indicator
        confidence = event.get('confidence_score')
        if confidence and confidence < 0.7:
            lines.append("\n_Note: Some details may be incomplete_")

        return "\n".join(lines)
