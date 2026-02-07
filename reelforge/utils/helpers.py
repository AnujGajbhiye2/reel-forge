"""
Helper utilities for configuration and file handling.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


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
    if os.getenv('GEMINI_API_KEY'):
        config['gemini_api_key'] = os.getenv('GEMINI_API_KEY')

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
