"""Main entry point for the Slack bot."""
import asyncio
import logging
import signal

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from src.config import Config
from src.bot import SlackEventBot
from src.webhook import WebhookServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run the Slack bot and webhook server."""
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return

    # Create Slack Bolt app
    app = AsyncApp(token=Config.SLACK_BOT_TOKEN)

    # Create bot and register handlers
    bot = SlackEventBot(app)

    # Create webhook server for agent callbacks
    webhook = WebhookServer(bot, Config.WEBHOOK_HOST, Config.WEBHOOK_PORT)

    # Start webhook server
    await webhook.start()

    # Start Socket Mode handler (connects to Slack without a public URL)
    handler = AsyncSocketModeHandler(app, Config.SLACK_APP_TOKEN)

    logger.info(f"Slack bot starting (org_id={Config.ORG_ID})")
    logger.info(f"Monitoring channels: {Config.SLACK_CHANNELS}")
    logger.info(f"Callback URL: {bot.callback_url}")

    # Set up graceful shutdown
    loop = asyncio.get_event_loop()

    async def shutdown():
        logger.info("Shutting down...")
        await handler.close_async()
        await webhook.stop()
        logger.info("Shutdown complete")

    def signal_handler():
        loop.create_task(shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await handler.start_async()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
