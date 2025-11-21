"""Configuration management for the Discord bot."""
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Discord settings
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    DISCORD_CHANNELS: List[int] = [
        int(ch.strip())
        for ch in os.getenv("DISCORD_CHANNELS", "").split(",")
        if ch.strip()
    ]

    # Agent settings
    AGENT_API_URL: str = os.getenv("AGENT_API_URL", "http://localhost:8000/parse")

    # Webhook settings
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "3000"))
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")

    # Database settings
    DB_PATH: str = os.getenv("DB_PATH", "weave_bot.db")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required")

        if not cls.DISCORD_CHANNELS:
            raise ValueError("DISCORD_CHANNELS is required")

        if not cls.AGENT_API_URL:
            raise ValueError("AGENT_API_URL is required")
