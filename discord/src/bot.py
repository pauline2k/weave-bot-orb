"""Discord bot for parsing event links."""
import discord
from discord.ext import commands
import aiohttp
import logging
from typing import Optional

from src.config import Config
from src.database import Database, ParseStatus
from src.utils import is_link_message, extract_url
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

        # Check if message contains a link
        if not is_link_message(message.content):
            return

        logger.info(f'Processing message {message.id} with link: {message.content}')

        # Extract the URL
        url = extract_url(message.content)
        if not url:
            return

        # Send initial response
        response = await message.reply("⏳ Parsing event...")

        # Store in database
        await self.db.create_request(
            discord_message_id=message.id,
            discord_response_id=response.id
        )

        # Send to agent API
        try:
            agent_id = await self._send_to_agent(url, message.id)

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

    async def _send_to_agent(self, url: str, message_id: int) -> Optional[str]:
        """
        Send URL to agent API for async parsing.

        The agent will:
        1. Return a request_id immediately
        2. Process the URL in the background
        3. POST results to our callback_url when done

        Returns the agent request ID if successful, None otherwise.
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "url": url,
                    "callback_url": self.callback_url,
                    "discord_message_id": message_id
                }

                logger.info(f'Sending to agent: {payload}')

                async with session.post(
                    self.agent_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
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
        result_url: Optional[str] = None
    ):
        """
        Handle completion callback from the agent.

        This is called by the webhook when the agent finishes parsing.

        Args:
            agent_request_id: Unique ID from the agent
            status: "completed" or "failed"
            event: Extracted event data (if successful)
            error: Error message (if failed)
            result_url: URL to saved record (future: Grist link)
        """
        # Update database
        parse_status = ParseStatus.COMPLETED if status == "completed" else ParseStatus.FAILED
        request = await self.db.update_status(
            agent_request_id,
            parse_status,
            result_url
        )

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

            # Send completion message
            if parse_status == ParseStatus.COMPLETED and event:
                # Format event data for Discord
                reply_content = self._format_event_reply(event, result_url)
                await original_message.reply(reply_content)
            elif parse_status == ParseStatus.COMPLETED and result_url:
                # Future: Grist link without event details
                await original_message.reply(
                    f"All set! I've added your event: {result_url}"
                )
            else:
                # Failed
                error_msg = error or "Unknown error"
                await original_message.reply(
                    f"I couldn't parse that link. {error_msg}\n"
                    "Could you double-check it's an event link and try again?"
                )

            logger.info(f'Completed processing for agent request {agent_request_id}')

        except discord.NotFound:
            logger.error(f'Message {request.discord_response_id} not found')
        except discord.Forbidden:
            logger.error(f'No permission to access message {request.discord_response_id}')
        except Exception as e:
            logger.error(f'Error handling parse completion: {e}')

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
