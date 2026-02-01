"""Lunch Money API client for uploading transactions."""

import hashlib
from dataclasses import dataclass
from typing import Any

import requests

from lunchsync_sg.models import Transaction


@dataclass
class UploadResult:
    """Result of uploading transactions to Lunch Money."""

    uploaded: int
    skipped: int
    errors: list[str]

    @property
    def total(self) -> int:
        """Total transactions processed."""
        return self.uploaded + self.skipped


def generate_external_id(tx: Transaction) -> str:
    """Generate deterministic external_id from transaction data.

    Uses the transaction reference if available, otherwise creates a hash
    of date+amount+description+account for deduplication.
    """
    if tx.reference:
        return tx.reference[:75]  # API max length

    # Hash of date+amount+description+account
    data = f"{tx.date.isoformat()}|{tx.amount}|{tx.description}|{tx.account}"
    return hashlib.sha256(data.encode()).hexdigest()[:75]


def transaction_to_payload(tx: Transaction, asset_id: int) -> dict[str, Any]:
    """Convert a Transaction to Lunch Money API payload format."""
    return {
        "date": tx.date.isoformat(),
        "amount": float(tx.amount),  # Keep sign, use debit_as_negative
        "payee": tx.description[:140],  # API max
        "currency": tx.original_currency.lower(),
        "asset_id": asset_id,
        "external_id": generate_external_id(tx),
        "status": "uncleared",  # Appears in review queue for categorization
    }


class LunchMoneyClient:
    """Client for interacting with the Lunch Money API."""

    BASE_URL = "https://dev.lunchmoney.app/v1"
    MAX_BATCH_SIZE = 500

    def __init__(self, api_key: str) -> None:
        """Initialize client with API key."""
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self.BASE_URL}/{endpoint}"
        response = self._session.request(method, url, json=json)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def get_assets(self) -> list[dict[str, Any]]:
        """Get all assets (accounts) from Lunch Money."""
        result = self._request("GET", "assets")
        return result.get("assets", [])  # type: ignore[no-any-return]

    def upload_transactions(
        self,
        transactions: list[Transaction],
        account_mapping: dict[str, int],
        skip_duplicates: bool = True,
    ) -> UploadResult:
        """Upload transactions to Lunch Money.

        Args:
            transactions: List of Transaction objects to upload
            account_mapping: Map of account names to Lunch Money asset IDs
            skip_duplicates: Use API's duplicate detection (default True)

        Returns:
            UploadResult with counts of uploaded, skipped, and errors
        """
        uploaded = 0
        skipped = 0
        errors: list[str] = []

        # Filter transactions to those with mapped accounts
        payloads: list[dict[str, Any]] = []
        for tx in transactions:
            asset_id = account_mapping.get(tx.account)
            if asset_id is None:
                skipped += 1
                continue
            payloads.append(transaction_to_payload(tx, asset_id))

        # Upload in batches
        for i in range(0, len(payloads), self.MAX_BATCH_SIZE):
            batch = payloads[i : i + self.MAX_BATCH_SIZE]

            try:
                result = self._request(
                    "POST",
                    "transactions",
                    json={
                        "transactions": batch,
                        "debit_as_negative": True,
                        "skip_duplicates": skip_duplicates,
                    },
                )

                # Parse result - API returns list of IDs for created transactions
                ids = result.get("ids", [])
                uploaded += len(ids)

                # Calculate skipped from this batch (duplicates)
                batch_skipped = len(batch) - len(ids)
                skipped += batch_skipped

            except requests.HTTPError as e:
                errors.append(f"Batch {i // self.MAX_BATCH_SIZE + 1}: {e}")
            except requests.RequestException as e:
                errors.append(f"Batch {i // self.MAX_BATCH_SIZE + 1}: {e}")

        return UploadResult(uploaded=uploaded, skipped=skipped, errors=errors)


def get_known_accounts(config: dict[str, Any] | None = None) -> list[str]:
    """Get list of known account names from configured mappings.

    Args:
        config: Loaded JSON config

    Returns:
        List of account names
    """
    from lunchsync_sg.config import get_account_mappings

    mappings = get_account_mappings(config)
    return [mapping.name for mapping in mappings]


def interactive_lm_setup(
    api_key: str,
    config: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Run interactive Lunch Money account mapping setup.

    Prompts the user to map each known bank account to a Lunch Money asset.

    Args:
        api_key: Lunch Money API key
        config: Existing config to update

    Returns:
        Dictionary mapping account names to asset IDs
    """
    from lunchsync_sg.config import (
        get_config_path,
        load_config,
        save_json_config,
    )

    print("\nLunch Money Setup")
    print("=================\n")

    print("Fetching your Lunch Money assets...")
    client = LunchMoneyClient(api_key)

    try:
        assets = client.get_assets()
    except requests.HTTPError as e:
        print(f"Error fetching assets: {e}")
        raise

    if not assets:
        print("No assets found in your Lunch Money account.")
        print("Please create some assets first at https://my.lunchmoney.app/")
        return {}

    print("\nAvailable assets:")
    for i, asset in enumerate(assets, 1):
        print(f"  [{i}] {asset['name']} (id: {asset['id']})")

    # Load config if not provided
    if config is None:
        config = load_config()

    bank_accounts = get_known_accounts(config)

    if not bank_accounts:
        print("\nNo bank accounts configured.")
        print("Run 'lunchsync-sg --setup' first to add your bank accounts.")
        return {}

    print("\nBank accounts found in config:")
    for account in bank_accounts:
        print(f"  - {account}")

    print("\nMap each bank account to a Lunch Money asset:\n")

    mapping: dict[str, int] = {}
    for account in bank_accounts:
        while True:
            choice = input(f"{account} -> Enter asset number (1-{len(assets)}) or 's' to skip: ")
            choice = choice.strip().lower()

            if choice == "s":
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(assets):
                    asset_id: int = assets[idx]["id"]
                    mapping[account] = asset_id
                    break
                else:
                    print(f"  Please enter a number between 1 and {len(assets)}")
            except ValueError:
                print("  Invalid input. Enter a number or 's' to skip.")

    # Save configuration
    if mapping and config:
        if "lunch_money" not in config:
            config["lunch_money"] = {}
        config["lunch_money"]["api_key"] = api_key
        config["lunch_money"]["account_mapping"] = mapping

        config_path = save_json_config(config, get_config_path())
        print(f"\nConfiguration saved to {config_path}")

    return mapping
