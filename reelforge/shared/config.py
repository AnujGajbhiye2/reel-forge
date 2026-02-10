"""
Helper utilities for configuration and file handling.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional fallback for minimal envs
    def load_dotenv() -> bool:
        return False


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file and environment variables.

    Automatically loads .env file if present and merges with config.yaml.
    Environment variables take precedence over config file values.

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary containing configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    # Load .env file if it exists
    load_dotenv()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Override with environment variables if present
    openai_api_key = os.getenv('OPENAI_API_KEY') or os.getenv('GEMINI_API_KEY')
    if openai_api_key:
        config['openai_api_key'] = openai_api_key

    drive_cfg = config.setdefault("integrations", {}).setdefault("google_drive", {})
    oauth_cfg = drive_cfg.setdefault("oauth", {})
    drive_enabled = os.getenv("GOOGLE_DRIVE_ENABLED")
    if drive_enabled is not None:
        drive_cfg["enabled"] = drive_enabled.strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID"):
        drive_cfg["parent_folder_id"] = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID")
    if os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_PATH"):
        oauth_cfg["client_secret_path"] = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_PATH")
    if os.getenv("GOOGLE_OAUTH_TOKEN_PATH"):
        oauth_cfg["token_path"] = os.getenv("GOOGLE_OAUTH_TOKEN_PATH")

    return config


def ensure_dir(directory: str) -> Path:
    """
    Ensure a directory exists, create if it doesn't.

    Args:
        directory: Path to directory

    Returns:
        Path object for the directory
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_root() -> Path:
    """
    Get the project root directory.

    Returns:
        Path object for project root
    """
    return Path(__file__).parent.parent.parent


def validate_asset_path(asset_path: str) -> bool:
    """
    Validate that an asset file exists.

    Args:
        asset_path: Path to asset file

    Returns:
        True if file exists, False otherwise
    """
    return os.path.isfile(asset_path)
