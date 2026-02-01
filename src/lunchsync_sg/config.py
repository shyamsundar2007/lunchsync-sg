"""Configuration management for lunchsync-sg."""

import os
from pathlib import Path

from dotenv import load_dotenv

from lunchsync_sg.models import AccountMapping


def load_config(env_path: Path | None = None) -> None:
    """Load configuration from .env file.

    Searches for config in the following order:
    1. Explicit path if provided
    2. .env in current directory
    3. XDG config: ~/.config/lunchsync-sg/.env
    4. Legacy: ~/.lunchsync-sg/.env
    """
    if env_path:
        load_dotenv(env_path)
        return

    xdg_config_home = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))

    config_paths = [
        Path(".env"),
        Path(xdg_config_home) / "lunchsync-sg" / ".env",
        Path.home() / ".lunchsync-sg" / ".env",
    ]

    for path in config_paths:
        if path.exists():
            load_dotenv(path)
            return


def get_account_mappings() -> list[AccountMapping]:
    """
    Get account mappings from environment.

    Returns empty list if no mappings configured - the tool will use
    "Unknown (last4)" naming for unrecognized accounts.

    Format in .env:
    ACCOUNT_MAPPINGS=identifier1:name1:bank1:type1,identifier2:name2:bank2:type2
    """
    mappings_str = os.getenv("ACCOUNT_MAPPINGS", "")

    if not mappings_str:
        return []

    mappings = []
    for entry in mappings_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3:
            mappings.append(
                AccountMapping(
                    identifier=parts[0],
                    name=parts[1],
                    bank=parts[2],
                    account_type=parts[3] if len(parts) > 3 else "credit_card",
                )
            )
    return mappings


def get_lunchmoney_api_key(override: str | None = None) -> str | None:
    """Get Lunch Money API key from arg or LUNCHMONEY_API_KEY env var.

    Args:
        override: Optional API key to use instead of env var

    Returns:
        API key string or None if not configured
    """
    if override:
        return override
    return os.getenv("LUNCHMONEY_API_KEY")


def get_lunchmoney_account_mapping() -> dict[str, int]:
    """Parse LUNCHMONEY_ACCOUNT_MAP env var.

    Format: 'Account Name=asset_id|Another Account=asset_id'
    (Uses | and = separators to avoid issues with special characters in names)

    Returns:
        Dictionary mapping account names to Lunch Money asset IDs
    """
    mapping_str = os.getenv("LUNCHMONEY_ACCOUNT_MAP", "")

    if not mapping_str:
        return {}

    mapping: dict[str, int] = {}
    for entry in mapping_str.split("|"):
        entry = entry.strip()
        if "=" not in entry:
            continue

        # Split on last = to handle account names with =
        parts = entry.rsplit("=", 1)
        if len(parts) == 2:
            name = parts[0].strip()
            try:
                asset_id = int(parts[1].strip())
                mapping[name] = asset_id
            except ValueError:
                continue

    return mapping


def get_account_name(identifier: str, mappings: list[AccountMapping] | None = None) -> str:
    """Get friendly account name from identifier."""
    if mappings is None:
        mappings = get_account_mappings()

    for mapping in mappings:
        if mapping.matches(identifier):
            return mapping.name

    # Return last 4 digits if no match
    clean_id = identifier.replace("-", "").replace(" ", "")
    if len(clean_id) >= 4:
        return f"Unknown ({clean_id[-4:]})"
    return identifier
