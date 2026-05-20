"""Webhook server for receiving agent callbacks."""
import logging
from typing import Optional

from aiohttp import web

from src.bot import SlackEventBot

logger = logging.getLogger(__name__)


class WebhookServer:
    """HTTP server that receives agent callbacks and routes to the Slack bot."""

    def __init__(self, bot: SlackEventBot, host: str, port: int):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None

    def _setup_routes(self):
        self.app.router.add_post("/callback", self.handle_callback)
        self.app.router.add_get("/health", self.health_check)

    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle callback from agent when parsing is complete."""
        try:
            data = await request.json()

            request_id = data.get("request_id")
            client_reference_id = data.get("client_reference_id")
            status = data.get("status")
            event = data.get("event")
            error = data.get("error")
            result_url = data.get("result_url")
            grist_record_id = data.get("grist_record_id")

            if not request_id or not status:
                return web.json_response({"error": "Missing required fields"}, status=400)

            if not client_reference_id:
                logger.warning(f"Callback {request_id} has no client_reference_id, skipping")
                return web.json_response({"success": True})

            logger.info(f"Received callback for {request_id}: status={status}")

            await self.bot.handle_parse_complete(
                client_reference_id=client_reference_id,
                status=status,
                event=event,
                error=error,
                result_url=result_url,
                grist_record_id=grist_record_id,
            )

            return web.json_response({"success": True})

        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def health_check(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "slack-bot"})

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"Webhook server started on {self.host}:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            logger.info("Webhook server stopped")
