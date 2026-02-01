"""Interactive setup wizard for lunchsync-sg."""

from pathlib import Path
from typing import Any

from lunchsync_sg.config import (
    create_default_config,
    get_config_path,
    load_config,
    save_json_config,
)
from lunchsync_sg.parsers.base import DetectedAccount, ParserRegistry
from lunchsync_sg.utils import read_file


def mask_card_number(card_number: str) -> str:
    """Mask card number for display, showing only last 4 digits."""
    clean = card_number.replace("-", "").replace(" ", "")
    if len(clean) > 4:
        return f"****{clean[-4:]}"
    return card_number


def scan_files_for_accounts(paths: list[Path]) -> list[DetectedAccount]:
    """Scan files and detect accounts.

    Args:
        paths: List of files or directories to scan

    Returns:
        List of DetectedAccount objects
    """
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in [".csv", ".xls", ".xlsx"]:
                files.extend(path.glob(f"*{ext}"))
                files.extend(path.glob(f"*{ext.upper()}"))
        elif path.exists():
            files.append(path)

    accounts: list[DetectedAccount] = []
    seen_cards: set[str] = set()

    for filepath in files:
        try:
            content = read_file(filepath)
        except Exception:
            continue

        # Try each parser to detect accounts
        for parser_class in ParserRegistry.get_all_parsers():
            if parser_class.can_parse(content, filepath):
                detected = parser_class.detect_account(content)
                if detected and detected.card_number not in seen_cards:
                    accounts.append(detected)
                    seen_cards.add(detected.card_number)
                break

    return accounts


def fetch_lunchmoney_assets(api_key: str) -> list[dict[str, Any]]:
    """Fetch Lunch Money assets.

    Args:
        api_key: Lunch Money API key

    Returns:
        List of asset dictionaries with 'id' and 'name' keys
    """
    from lunchsync_sg.lunchmoney import LunchMoneyClient

    client = LunchMoneyClient(api_key)
    return client.get_assets()


def run_setup(
    input_paths: list[Path] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run the streamlined setup wizard.

    The flow:
    1. Scan bank export files to auto-detect accounts
    2. Fetch Lunch Money assets (if API key provided)
    3. User maps each account to a Lunch Money asset
    4. Asset name becomes the account's friendly name

    Args:
        input_paths: Bank export files/directories to scan
        api_key: Lunch Money API key (prompts if not provided)

    Returns:
        The configuration dictionary
    """
    print("\n" + "=" * 50)
    print("  LUNCHSYNC-SG SETUP")
    print("=" * 50)

    # Load existing config or create new
    config = load_config()
    if config is None:
        config = create_default_config()

    # Step 1: Detect accounts from files
    if input_paths:
        print("\nScanning bank export files...")
        detected_accounts = scan_files_for_accounts(input_paths)

        if detected_accounts:
            print(f"Found {len(detected_accounts)} account(s):\n")
            for acc in detected_accounts:
                masked = mask_card_number(acc.card_number) if acc.card_number else "(no number)"
                print(f"  {acc.display_hint}: {masked}")
        else:
            print("No accounts found in the provided files.")
            print("Make sure you're providing bank export files (CSV/XLS).")
            return config
    else:
        print("\nNo bank export files provided.")
        print("Usage: lunchsync-sg --setup ~/Downloads/bank-exports/")
        print("\nYou can also set up manually by editing the config file.")
        detected_accounts = []

    # Step 2: Get Lunch Money API key
    if not api_key:
        existing_key = config.get("lunch_money", {}).get("api_key")
        if existing_key:
            masked = existing_key[:8] + "..." if len(existing_key) > 8 else "***"
            print(f"\nExisting Lunch Money API key: {masked}")
            use_existing = input("Use this key? [Y/n]: ").strip().lower()
            if use_existing in ("", "y", "yes"):
                api_key = existing_key

        if not api_key:
            print("\nGet your API key at: https://my.lunchmoney.app/developers")
            api_key = input("Lunch Money API key: ").strip()

    if not api_key:
        print("\nNo API key provided. Cannot complete setup.")
        print("Run setup again with your Lunch Money API key.")
        return config

    # Save API key
    config.setdefault("lunch_money", {})["api_key"] = api_key

    # Step 3: Fetch Lunch Money assets
    print("\nFetching Lunch Money assets...")
    try:
        assets = fetch_lunchmoney_assets(api_key)
    except Exception as e:
        print(f"Error fetching assets: {e}")
        print("Please check your API key and try again.")
        return config

    if not assets:
        print("No assets found in your Lunch Money account.")
        print("Create assets at https://my.lunchmoney.app/ then run setup again.")
        return config

    print(f"Found {len(assets)} asset(s):\n")
    for i, asset in enumerate(assets, 1):
        print(f"  [{i}] {asset['name']}")

    # Step 4: Map accounts to assets
    if detected_accounts:
        print("\n" + "-" * 50)
        print("MAP ACCOUNTS TO LUNCH MONEY ASSETS")
        print("-" * 50)
        print("\nFor each bank account, select the Lunch Money asset it maps to.")
        print("The asset name will be used as the account name.\n")

        accounts_config: list[dict[str, str]] = []
        account_mapping: dict[str, int] = {}

        for acc in detected_accounts:
            masked = mask_card_number(acc.card_number) if acc.card_number else "(no number)"
            print(f"{acc.display_hint} ({masked}):")

            while True:
                choice = input(f"  Select asset [1-{len(assets)}] or 's' to skip: ").strip()

                if choice.lower() == "s":
                    print("  Skipped.\n")
                    break

                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(assets):
                        asset = assets[idx]
                        asset_name: str = asset["name"]
                        asset_id: int = asset["id"]

                        # Add to accounts config
                        accounts_config.append({
                            "card_number": acc.card_number,
                            "name": asset_name,
                            "bank": acc.bank,
                            "type": acc.account_type,
                        })

                        # Add to Lunch Money mapping
                        account_mapping[asset_name] = asset_id

                        print(f"  → {asset_name}\n")
                        break
                    else:
                        print(f"  Invalid. Enter 1-{len(assets)} or 's' to skip.")
                except ValueError:
                    print(f"  Invalid. Enter 1-{len(assets)} or 's' to skip.")

        # Update config
        config["accounts"] = accounts_config
        config["lunch_money"]["account_mapping"] = account_mapping

    # Save config
    config_path = get_config_path()
    saved_path = save_json_config(config, config_path)

    print("\n" + "=" * 50)
    print("SETUP COMPLETE")
    print("=" * 50)
    print(f"\nConfiguration saved to: {saved_path}")

    if config.get("accounts"):
        print(f"\nConfigured {len(config['accounts'])} account(s):")
        for acc in config["accounts"]:
            print(f"  - {acc['name']} ({acc['bank']})")

    print("\nYou can now run:")
    print("  lunchsync-sg ~/Downloads/ --upload-lunchmoney")
    print("  lunchsync-sg ~/Downloads/ --upload-lunchmoney --dry-run")

    return config


def show_current_config(config: dict[str, Any]) -> None:
    """Display the current configuration."""
    print("\n" + "=" * 50)
    print("CURRENT CONFIGURATION")
    print("=" * 50)

    accounts = config.get("accounts", [])
    if accounts:
        print("\nAccounts:")
        for acc in accounts:
            acc_type = acc.get("type", "credit_card")
            masked = mask_card_number(acc.get("card_number", ""))
            print(f"  - {acc['name']}")
            print(f"    Card: {masked}, Bank: {acc['bank']}, Type: {acc_type}")
    else:
        print("\nNo accounts configured.")

    lm = config.get("lunch_money", {})
    api_key = lm.get("api_key")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"\nLunch Money API Key: {masked}")

        mapping = lm.get("account_mapping", {})
        if mapping:
            print("Account → Asset mappings:")
            for name, asset_id in mapping.items():
                print(f"  - {name} → asset {asset_id}")
        else:
            print("No Lunch Money account mappings configured.")
    else:
        print("\nLunch Money: Not configured")
