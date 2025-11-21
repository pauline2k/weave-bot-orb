"""Main entry point for the Discord bot."""
import os
import certifi

# Set SSL certificate path before importing anything that uses SSL
os.environ['SSL_CERT_FILE'] = certifi.where()

import asyncio
import logging
import signal

from .config import Config
from .database import Database
from .bot import WeaveBotClient
from .webhook import WebhookServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run the Discord bot and webhook server."""
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f'Configuration error: {e}')
        return

    # Initialize database
    db = Database(Config.DB_PATH)
    logger.info(f'Database initialized at {Config.DB_PATH}')

    # Create bot and webhook server
    bot = WeaveBotClient(db)
    webhook = WebhookServer(bot, Config.WEBHOOK_HOST, Config.WEBHOOK_PORT)

    # Start webhook server
    await webhook.start()

    # Set up graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info('Received shutdown signal')
        loop.create_task(shutdown(bot, webhook))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Start Discord bot (this blocks until the bot disconnects)
        await bot.start(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info('Received keyboard interrupt')
    finally:
        await shutdown(bot, webhook)


async def shutdown(bot: WeaveBotClient, webhook: WebhookServer):
    """Gracefully shutdown the bot and webhook server."""
    logger.info('Shutting down...')

    # Close Discord connection
    if not bot.is_closed():
        await bot.close()

    # Stop webhook server
    await webhook.stop()

    logger.info('Shutdown complete')


if __name__ == '__main__':
    asyncio.run(main())
