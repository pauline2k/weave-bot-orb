"""Discord bot for parsing event links."""
import discord
from discord.ext import commands
import aiohttp
import logging
from typing import Optional

from .config import Config
from .database import Database, ParseStatus
from .utils import is_link_message, extract_url

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
        Send URL to agent API for parsing.

        Returns the agent request ID if successful, None otherwise.
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "url": url,
                    "discord_message_id": message_id
                }

                async with session.post(
                    self.agent_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Expecting response like: {"request_id": "abc-123"}
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
        result_url: Optional[str] = None
    ):
        """
        Handle completion callback from the agent.

        This is called by the webhook when the agent finishes parsing.
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
            if parse_status == ParseStatus.COMPLETED and result_url:
                await original_message.reply(
                    f"All set! I've added your event: {result_url}"
                )
            else:
                await original_message.reply(
                    "I couldn't parse that link. Could you double-check it's an event link and try again?"
                )

            logger.info(f'Completed processing for agent request {agent_request_id}')

        except discord.NotFound:
            logger.error(f'Message {request.discord_response_id} not found')
        except discord.Forbidden:
            logger.error(f'No permission to access message {request.discord_response_id}')
        except Exception as e:
            logger.error(f'Error handling parse completion: {e}')
