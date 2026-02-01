"""Interactive setup wizard for lunchsync-sg."""

from typing import Any

from lunchsync_sg.config import (
    create_default_config,
    get_config_path,
    load_config,
    save_json_config,
)

# Supported banks and their common account types
SUPPORTED_BANKS = {
    "OCBC": ["credit_card", "savings"],
    "DBS": ["credit_card", "savings"],
    "UOB": ["credit_card", "savings"],
    "HSBC": ["credit_card"],
    "Citi": ["credit_card"],
}


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        response = input(question + suffix).strip().lower()
        if response == "":
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("  Please enter 'y' or 'n'")


def prompt_choice(question: str, choices: list[str], allow_skip: bool = False) -> str | None:
    """Prompt user to choose from a list of options."""
    print(f"\n{question}")
    for i, choice in enumerate(choices, 1):
        print(f"  [{i}] {choice}")
    if allow_skip:
        print("  [s] Skip")

    while True:
        response = input("Enter choice: ").strip().lower()
        if allow_skip and response == "s":
            return None
        try:
            idx = int(response) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
            print(f"  Please enter a number between 1 and {len(choices)}")
        except ValueError:
            if allow_skip:
                print("  Invalid input. Enter a number or 's' to skip.")
            else:
                print(f"  Invalid input. Enter a number between 1 and {len(choices)}.")


def prompt_account() -> dict[str, str] | None:
    """Prompt user to enter account details."""
    print("\n--- Add Account ---")

    # Get card/account number
    card_number = input("Card/Account number (as shown in bank exports): ").strip()
    if not card_number:
        return None

    # Get friendly name
    name = input("Friendly name (e.g., 'OCBC Rewards Card'): ").strip()
    if not name:
        print("  Name is required.")
        return None

    # Select bank
    bank = prompt_choice("Select bank:", list(SUPPORTED_BANKS.keys()))
    if not bank:
        return None

    # Select account type
    account_types = SUPPORTED_BANKS[bank]
    if len(account_types) == 1:
        account_type = account_types[0]
        print(f"  Account type: {account_type}")
    else:
        selected_type = prompt_choice("Select account type:", account_types)
        account_type = selected_type if selected_type else "credit_card"

    return {
        "card_number": card_number,
        "name": name,
        "bank": bank,
        "type": account_type,
    }


def edit_account(account: dict[str, str]) -> dict[str, str]:
    """Edit an existing account."""
    print(f"\n--- Edit Account: {account['name']} ---")
    print("(Press Enter to keep current value)\n")

    # Card number
    current = account["card_number"]
    new_value = input(f"Card number [{current}]: ").strip()
    if new_value:
        account["card_number"] = new_value

    # Name
    current = account["name"]
    new_value = input(f"Name [{current}]: ").strip()
    if new_value:
        account["name"] = new_value

    # Bank
    current = account["bank"]
    print(f"\nCurrent bank: {current}")
    if prompt_yes_no("Change bank?", default=False):
        bank = prompt_choice("Select bank:", list(SUPPORTED_BANKS.keys()))
        if bank:
            account["bank"] = bank

    # Type
    current_type = account.get("type", "credit_card")
    print(f"\nCurrent type: {current_type}")
    if prompt_yes_no("Change type?", default=False):
        bank = account["bank"]
        account_types = SUPPORTED_BANKS.get(bank, ["credit_card", "savings"])
        new_type = prompt_choice("Select account type:", account_types)
        if new_type:
            account["type"] = new_type

    return account


def list_accounts(accounts: list[dict[str, str]]) -> None:
    """Display list of accounts."""
    if not accounts:
        print("\n  No accounts configured.")
        return

    print("\nConfigured accounts:")
    for i, acc in enumerate(accounts, 1):
        acc_type = acc.get("type", "credit_card")
        print(f"  [{i}] {acc['name']}")
        print(f"      Card: {acc['card_number']}")
        print(f"      Bank: {acc['bank']}, Type: {acc_type}")


def manage_accounts(config: dict[str, Any]) -> None:
    """Interactive account management menu."""
    while True:
        accounts = config.get("accounts", [])
        list_accounts(accounts)

        print("\n--- Account Management ---")
        print("  [a] Add new account")
        if accounts:
            print("  [e] Edit account")
            print("  [d] Delete account")
        print("  [q] Done / Back to main menu")

        choice = input("\nChoice: ").strip().lower()

        if choice == "a":
            account = prompt_account()
            if account:
                config.setdefault("accounts", []).append(account)
                print(f"\n  Added: {account['name']}")

        elif choice == "e" and accounts:
            list_accounts(accounts)
            try:
                idx = int(input("\nEnter account number to edit: ").strip()) - 1
                if 0 <= idx < len(accounts):
                    config["accounts"][idx] = edit_account(accounts[idx].copy())
                    print("\n  Account updated.")
                else:
                    print(f"  Invalid number. Enter 1-{len(accounts)}.")
            except ValueError:
                print("  Invalid input.")

        elif choice == "d" and accounts:
            list_accounts(accounts)
            try:
                idx = int(input("\nEnter account number to delete: ").strip()) - 1
                if 0 <= idx < len(accounts):
                    removed = config["accounts"].pop(idx)
                    print(f"\n  Deleted: {removed['name']}")
                else:
                    print(f"  Invalid number. Enter 1-{len(accounts)}.")
            except ValueError:
                print("  Invalid input.")

        elif choice == "q":
            break

        else:
            print("  Invalid choice.")


def setup_lunchmoney(config: dict[str, Any]) -> None:
    """Interactive Lunch Money setup."""
    print("\n" + "=" * 50)
    print("LUNCH MONEY SETUP")
    print("=" * 50)

    # Check if already configured
    lm_config = config.get("lunch_money", {})
    current_key = lm_config.get("api_key")
    if current_key:
        masked = current_key[:8] + "..." if len(current_key) > 8 else "***"
        print(f"\nCurrent API key: {masked}")
        if not prompt_yes_no("Reconfigure Lunch Money?", default=False):
            return

    print("\nGet your API key at: https://my.lunchmoney.app/developers")
    api_key = input("Lunch Money API key (or press Enter to skip): ").strip()

    if not api_key:
        print("  Skipping Lunch Money setup.")
        return

    config.setdefault("lunch_money", {})["api_key"] = api_key

    # Try to fetch assets and set up mapping
    accounts = config.get("accounts", [])
    if not accounts:
        print("\n  No bank accounts configured. Add accounts first, then run --lm-setup.")
        return

    print("\nFetching your Lunch Money assets...")

    try:
        from lunchsync_sg.lunchmoney import LunchMoneyClient

        client = LunchMoneyClient(api_key)
        assets = client.get_assets()

        if not assets:
            print("  No assets found in your Lunch Money account.")
            print("  Create assets at https://my.lunchmoney.app/ then run --lm-setup.")
            return

        print("\nAvailable Lunch Money assets:")
        for i, asset in enumerate(assets, 1):
            print(f"  [{i}] {asset['name']} (id: {asset['id']})")

        # Map each configured account to a Lunch Money asset
        print("\nMap each bank account to a Lunch Money asset:")

        account_mapping: dict[str, int] = {}
        for account in accounts:
            account_name = account["name"]
            print(f"\n{account_name}:")
            while True:
                choice = input(f"  Enter asset number (1-{len(assets)}) or 's' to skip: ").strip()
                if choice.lower() == "s":
                    break
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(assets):
                        asset_id: int = assets[idx]["id"]
                        account_mapping[account_name] = asset_id
                        print(f"  Mapped to: {assets[idx]['name']}")
                        break
                    print(f"  Please enter a number between 1 and {len(assets)}")
                except ValueError:
                    print("  Invalid input. Enter a number or 's' to skip.")

        config["lunch_money"]["account_mapping"] = account_mapping

    except Exception as e:
        print(f"  Error connecting to Lunch Money: {e}")
        print("  API key saved. Run --lm-setup later to configure asset mapping.")


def run_setup(existing_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the full interactive setup wizard.

    Args:
        existing_config: Existing config to modify, or None for fresh setup

    Returns:
        The configuration dictionary
    """
    print("\n" + "=" * 50)
    print("  LUNCHSYNC-SG SETUP")
    print("=" * 50)

    if existing_config:
        config = existing_config
        print("\nExisting configuration found.")
    else:
        config = create_default_config()
        print("\nNo existing configuration. Creating new config.")

    while True:
        print("\n--- Main Menu ---")
        print("  [1] Manage accounts (add/edit/delete)")
        print("  [2] Configure Lunch Money")
        print("  [3] View current configuration")
        print("  [4] Save and exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            manage_accounts(config)

        elif choice == "2":
            setup_lunchmoney(config)

        elif choice == "3":
            show_current_config(config)

        elif choice == "4":
            break

        else:
            print("  Invalid choice. Enter 1-4.")

    # Validate - must have at least one account
    if not config.get("accounts"):
        print("\nWarning: No accounts configured. You'll need to add accounts before processing files.")

    # Save configuration
    config_path = get_config_path()
    saved_path = save_json_config(config, config_path)

    print("\n" + "=" * 50)
    print("SETUP COMPLETE")
    print("=" * 50)
    print(f"\nConfiguration saved to: {saved_path}")
    print("\nYou can now run:")
    print("  lunchsync-sg ~/Downloads/  # Process bank exports")
    print("  lunchsync-sg ~/Downloads/ --upload-lunchmoney  # Upload to Lunch Money")
    print("\nTo modify settings later, run: lunchsync-sg --setup")

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
            print(f"  - {acc['name']}")
            print(f"    Card: {acc['card_number']}")
            print(f"    Bank: {acc['bank']}, Type: {acc_type}")
    else:
        print("\nNo accounts configured.")

    lm = config.get("lunch_money", {})
    api_key = lm.get("api_key")
    if api_key:
        # Mask API key for display
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"\nLunch Money API Key: {masked}")

        mapping = lm.get("account_mapping", {})
        if mapping:
            print("Account mappings:")
            for name, asset_id in mapping.items():
                print(f"  - {name} -> asset {asset_id}")
        else:
            print("No Lunch Money account mappings configured.")
    else:
        print("\nLunch Money: Not configured")


def quick_add_account() -> dict[str, Any] | None:
    """Quick add a single account without full setup wizard.

    Returns:
        The updated config or None if cancelled
    """
    config = load_config()
    if config is None:
        config = create_default_config()

    account = prompt_account()
    if account:
        config.setdefault("accounts", []).append(account)
        config_path = get_config_path()
        save_json_config(config, config_path)
        print(f"\nAccount added: {account['name']}")
        print(f"Configuration saved to: {config_path}")
        return config

    return None
