"""Configuration for the Slack bot."""
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Slack settings
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")  # for Socket Mode
    SLACK_CHANNELS: List[str] = [
        ch.strip()
        for ch in os.getenv("SLACK_CHANNELS", "").split(",")
        if ch.strip()
    ]

    # Org identity — which org this Slack bot represents
    ORG_ID: str = os.getenv("ORG_ID", "default")

    # Agent API
    AGENT_API_URL: str = os.getenv("AGENT_API_URL", "http://localhost:8000/parse")

    # Webhook settings (for agent callbacks)
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "3001"))
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    CALLBACK_URL: str = os.getenv("CALLBACK_URL", "")

    # Grist settings (for editorial updates)
    GRIST_API_KEY: str = os.getenv("GRIST_API_KEY", "")
    GRIST_DOC_ID: str = os.getenv("GRIST_DOC_ID", "")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.SLACK_BOT_TOKEN:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not cls.SLACK_APP_TOKEN:
            raise ValueError("SLACK_APP_TOKEN is required (for Socket Mode)")
        if not cls.SLACK_CHANNELS:
            raise ValueError("SLACK_CHANNELS is required")
        if not cls.AGENT_API_URL:
            raise ValueError("AGENT_API_URL is required")
