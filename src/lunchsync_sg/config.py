"""Configuration management for lunchsync-sg."""

import os
from pathlib import Path

from dotenv import load_dotenv

from lunchsync_sg.models import AccountMapping


def load_config(env_path: Path | None = None) -> None:
    """Load configuration from .env file."""
    if env_path:
        load_dotenv(env_path)
    else:
        # Try common locations
        for path in [Path(".env"), Path.home() / ".lunchsync-sg" / ".env"]:
            if path.exists():
                load_dotenv(path)
                break


def get_account_mappings() -> list[AccountMapping]:
    """
    Get account mappings from environment or defaults.

    Format in .env:
    ACCOUNT_MAPPINGS=identifier1:name1:bank1:type1,identifier2:name2:bank2:type2
    """
    mappings_str = os.getenv("ACCOUNT_MAPPINGS", "")

    if mappings_str:
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

    # Default mappings
    return DEFAULT_ACCOUNT_MAPPINGS


# Default account mappings - these are example/fake numbers for testing
# Users should configure their own mappings via ACCOUNT_MAPPINGS env var
# Note: Each card should have unique last 4 digits to avoid matching conflicts
DEFAULT_ACCOUNT_MAPPINGS: list[AccountMapping] = [
    # OCBC
    AccountMapping("5400123456780001", "OCBC Rewards", "OCBC", "credit_card"),
    AccountMapping("695012345001", "OCBC 360", "OCBC", "savings"),
    # DBS
    AccountMapping("0201234567", "DBS Savings", "DBS", "savings"),
    AccountMapping("5420123456780002", "DBS World MC", "DBS", "credit_card"),
    # UOB
    AccountMapping("5522123456780003", "UOB Lady's Solitaire", "UOB", "credit_card"),
    AccountMapping("4265123456780004", "UOB Platinum VISA", "UOB", "credit_card"),
    # HSBC
    AccountMapping("3363", "HSBC Revolution", "HSBC", "credit_card"),
    # Citi
    AccountMapping("5425123456780005", "Citi Rewards", "Citi", "credit_card"),
    AccountMapping("5425987654321098", "Citi Prestige", "Citi", "credit_card"),
]


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
