"""Configuration management for lunchsync-sg."""

import json
import os
from pathlib import Path
from typing import Any

from lunchsync_sg.models import AccountMapping

# Default config filename
CONFIG_FILENAME = "config.json"


def get_config_dir() -> Path:
    """Get the config directory path (XDG compliant)."""
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg_config_home) / "lunchsync-sg"


def get_config_path() -> Path:
    """Get the default config file path."""
    return get_config_dir() / CONFIG_FILENAME


def find_config_file() -> Path | None:
    """Find the config file in standard locations.

    Searches for config in the following order:
    1. config.json in current directory
    2. XDG config: ~/.config/lunchsync-sg/config.json
    """
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))

    config_paths = [
        Path("config.json"),
        Path(xdg_config_home) / "lunchsync-sg" / CONFIG_FILENAME,
    ]

    for path in config_paths:
        if path.exists():
            return path

    return None


def load_json_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from a JSON file."""
    with open(config_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def save_json_config(config: dict[str, Any], config_path: Path | None = None) -> Path:
    """Save configuration to a JSON file.

    Args:
        config: Configuration dictionary to save
        config_path: Path to save to (defaults to XDG config location)

    Returns:
        Path where config was saved
    """
    if config_path is None:
        config_path = get_config_path()

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    return config_path


def load_config(config_path: Path | None = None) -> dict[str, Any] | None:
    """Load configuration from config file.

    Args:
        config_path: Explicit path to config.json file

    Returns:
        Loaded config dict or None if not found
    """
    if config_path:
        return load_json_config(config_path)

    config_file = find_config_file()
    if config_file:
        return load_json_config(config_file)

    return None


def config_exists() -> bool:
    """Check if any config file exists."""
    return find_config_file() is not None


def get_account_mappings(config: dict[str, Any] | None = None) -> list[AccountMapping]:
    """Get account mappings from config.

    Args:
        config: Loaded JSON config

    Returns:
        List of AccountMapping objects
    """
    if not config or "accounts" not in config:
        return []

    mappings = []
    for acc in config["accounts"]:
        mappings.append(
            AccountMapping(
                identifier=acc["card_number"],
                name=acc["name"],
                bank=acc["bank"],
                account_type=acc.get("type", "credit_card"),
            )
        )
    return mappings


def get_lunchmoney_api_key(
    config: dict[str, Any] | None = None,
    override: str | None = None,
) -> str | None:
    """Get Lunch Money API key.

    Args:
        config: Loaded JSON config
        override: Optional API key to use instead of config

    Returns:
        API key string or None if not configured
    """
    if override:
        return override

    if config:
        lm_config = config.get("lunch_money", {})
        if api_key := lm_config.get("api_key"):
            return api_key  # type: ignore[no-any-return]

    return None


def get_lunchmoney_account_mapping(
    config: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Get Lunch Money account to asset ID mapping.

    Args:
        config: Loaded JSON config

    Returns:
        Dictionary mapping account names to Lunch Money asset IDs
    """
    if not config:
        return {}

    lm_config = config.get("lunch_money", {})
    account_map = lm_config.get("account_mapping", {})
    # Convert string keys to int values if needed
    return {k: int(v) for k, v in account_map.items()}


def get_account_name(
    identifier: str,
    mappings: list[AccountMapping] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Get friendly account name from identifier.

    Args:
        identifier: Account/card number from bank export
        mappings: Pre-loaded mappings (optional)
        config: Loaded JSON config (optional)

    Returns:
        Friendly account name or "Unknown (last4)" if not found
    """
    if mappings is None:
        mappings = get_account_mappings(config)

    for mapping in mappings:
        if mapping.matches(identifier):
            return mapping.name

    # Return last 4 digits if no match
    clean_id = identifier.replace("-", "").replace(" ", "")
    if len(clean_id) >= 4:
        return f"Unknown ({clean_id[-4:]})"
    return identifier


def create_default_config() -> dict[str, Any]:
    """Create a default empty configuration."""
    return {
        "accounts": [],
        "lunch_money": {
            "api_key": None,
            "account_mapping": {},
        },
    }
