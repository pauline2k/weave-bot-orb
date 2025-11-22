"""Webhook server for receiving agent callbacks."""
import asyncio
import logging
from aiohttp import web
from typing import Optional

from src.bot import WeaveBotClient

logger = logging.getLogger(__name__)


class WebhookServer:
    def __init__(self, bot: WeaveBotClient, host: str, port: int):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None

    def _setup_routes(self):
        """Set up webhook routes."""
        self.app.router.add_get('/', self.home)
        self.app.router.add_post('/callback', self.handle_callback)
        self.app.router.add_get('/health', self.health_check)

    async def handle_callback(self, request: web.Request) -> web.Response:
        """
        Handle callback from agent when parsing is complete.

        Expected payload:
        {
            "request_id": "agent-request-id",
            "discord_message_id": 123456789 (optional),
            "status": "completed" | "failed",
            "event": { ... event data ... } (if successful),
            "error": "error message" (if failed),
            "result_url": "https://grist.example.com/..." (future: Grist link)
        }
        """
        try:
            data = await request.json()

            request_id = data.get('request_id')
            status = data.get('status')
            event = data.get('event')
            error = data.get('error')
            result_url = data.get('result_url')
            grist_record_id = data.get('grist_record_id')

            if not request_id or not status:
                logger.error(f'Invalid callback payload: {data}')
                return web.json_response(
                    {'error': 'Missing required fields'},
                    status=400
                )

            logger.info(
                f'Received callback for request {request_id} '
                f'with status {status}, grist_record_id={grist_record_id}'
            )

            # Handle the completion in the bot
            await self.bot.handle_parse_complete(
                request_id,
                status,
                event=event,
                error=error,
                result_url=result_url,
                grist_record_id=grist_record_id
            )

            return web.json_response({'success': True})

        except Exception as e:
            logger.error(f'Error handling callback: {e}')
            return web.json_response(
                {'error': 'Internal server error'},
                status=500
            )

    async def home(self, request: web.Request) -> web.Response:
        """Welcome page."""
        text = "You found Weave Bot!\nSay hi at https://oaklog.org"
        return web.Response(text=text, content_type='text/plain')

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({'status': 'ok'})

    async def start(self):
        """Start the webhook server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        logger.info(f'Webhook server started on {self.host}:{self.port}')

    async def stop(self):
        """Stop the webhook server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info('Webhook server stopped')
