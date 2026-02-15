"""Application configuration using pydantic-settings."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Get the agent directory path
AGENT_DIR = Path(__file__).parent.parent
ENV_FILE = AGENT_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Gemini API
    gemini_api_key: str

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Authentication
    auth_user: str = ""
    auth_password: str = ""
    session_secret: str = ""
    cookie_https_only: bool = False

    # Browser
    headless: bool = True
    browser_timeout: int = 30000  # milliseconds
    screenshot_enabled: bool = True

    # Grist integration
    grist_api_key: str = ""
    grist_doc_id: str = "b2r9qYM2Lr9xJ2epHVV1K2"  # ORB Events document

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance
settings = Settings()
