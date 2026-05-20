"""Per-org configuration loaded from YAML with env var substitution."""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# Default config file location
AGENT_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = AGENT_DIR / "orgs.yaml"


class LLMConfig(BaseModel):
    """LLM provider configuration for an org."""
    provider: str  # "gemini" or "openai_compatible"
    api_key: str
    model: str = ""
    endpoint_url: Optional[str] = None  # Required for openai_compatible


class StorageConfig(BaseModel):
    """Storage backend configuration for an org."""
    backend: str = "grist"
    api_key: str = ""
    doc_id: str = ""
    table_name: str = "Events"
    ui_host: str = ""
    ui_doc_id: Optional[str] = None  # Falls back to doc_id if not set
    ui_page_name: str = "Events"


class ChatConfig(BaseModel):
    """Chat platform configuration for an org."""
    platform: str = "discord"  # "discord" or "slack"
    channels: List = []


class OrgConfig(BaseModel):
    """Configuration for a single organization."""
    name: str = ""
    timezone: str = "America/Los_Angeles"
    llm: LLMConfig
    storage: StorageConfig = StorageConfig()
    chat: ChatConfig = ChatConfig()


def _substitute_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with os.environ[VAR_NAME]."""
    def replacer(match):
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            logger.warning(f"Environment variable ${{{var_name}}} not set")
            return ""
        return env_val

    return re.sub(r'\$\{([^}]+)\}', replacer, value)


def _substitute_recursively(data):
    """Walk a data structure and substitute env vars in all strings."""
    if isinstance(data, str):
        return _substitute_env_vars(data)
    elif isinstance(data, dict):
        return {k: _substitute_recursively(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_recursively(item) for item in data]
    return data


# In-memory cache of loaded org configs
_org_configs: Optional[Dict[str, OrgConfig]] = None


def load_org_configs(config_path: Optional[Path] = None) -> Dict[str, OrgConfig]:
    """Load org configurations from YAML file.

    Falls back to building a default 'orb' config from environment variables
    if no YAML file exists (backward compatibility).
    """
    global _org_configs

    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        import yaml
        with open(path) as f:
            raw = yaml.safe_load(f)

        raw = _substitute_recursively(raw)
        orgs_data = raw.get("orgs", {})

        configs = {}
        for org_id, org_data in orgs_data.items():
            try:
                configs[org_id] = OrgConfig(**org_data)
                logger.info(f"Loaded org config: {org_id} ({configs[org_id].name})")
            except Exception as e:
                logger.error(f"Invalid org config for '{org_id}': {e}")
                raise

        _org_configs = configs
        return configs

    # Fallback: build default config from env vars (backward compat)
    logger.info("No orgs.yaml found, using env vars for default 'orb' config")
    _org_configs = {
        "orb": OrgConfig(
            name="ORB (default)",
            timezone="America/Los_Angeles",
            llm=LLMConfig(
                provider="gemini",
                api_key=os.environ.get("GEMINI_API_KEY", ""),
                model="gemini-2.5-flash-lite",
            ),
            storage=StorageConfig(
                backend="grist",
                api_key=os.environ.get("GRIST_API_KEY", ""),
                doc_id=os.environ.get("GRIST_DOC_ID", ""),
                ui_host=os.environ.get("GRIST_UI_HOST", "oaklog.getgrist.com"),
                ui_page_name=os.environ.get("GRIST_UI_PAGE_NAME", "ORB-Events"),
            ),
        )
    }
    return _org_configs


def get_org_config(org_id: str = "default") -> OrgConfig:
    """Look up config for an org. 'default' returns the first configured org."""
    global _org_configs

    if _org_configs is None:
        load_org_configs()

    if org_id == "default":
        # Return first org
        return next(iter(_org_configs.values()))

    config = _org_configs.get(org_id)
    if config is None:
        available = list(_org_configs.keys())
        raise ValueError(f"Unknown org_id '{org_id}'. Available: {available}")

    return config


def get_all_org_configs() -> Dict[str, OrgConfig]:
    """Return all loaded org configs."""
    global _org_configs
    if _org_configs is None:
        load_org_configs()
    return _org_configs


def clear_org_configs():
    """Clear cached configs. Used in tests."""
    global _org_configs
    _org_configs = None
