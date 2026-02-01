#!/usr/bin/env python3
"""Command-line interface for lunchsync-sg."""

import argparse
import sys
from pathlib import Path
from typing import Any

from lunchsync_sg.config import (
    config_exists,
    get_lunchmoney_account_mapping,
    get_lunchmoney_api_key,
    load_config,
)
from lunchsync_sg.models import Transaction
from lunchsync_sg.normalizer import BankNormalizer
from lunchsync_sg.parsers import ParserRegistry


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Normalize bank transaction exports from multiple Singapore banks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lunchsync-sg --setup ~/Downloads/bank-exports/
  lunchsync-sg ~/Downloads/bank-exports/ -o transactions.csv
  lunchsync-sg ~/Downloads/ --upload-lunchmoney
  lunchsync-sg ~/Downloads/ --upload-lunchmoney --dry-run
  lunchsync-sg --list-parsers

Supported banks:
  - OCBC (Credit Card, 360 Account)
  - DBS (Savings, Credit Card)
  - UOB (Lady's Solitaire, Platinum VISA)
  - HSBC (Revolution)
  - Citibank (Rewards, Prestige)
        """,
    )

    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input files or directories",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="transactions.csv",
        help="Output CSV file (default: transactions.csv)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "tsv"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include all fields in output (currency, category, etc.)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Don't deduplicate transactions",
    )
    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Don't sort by date",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config.json file",
    )
    parser.add_argument(
        "--list-parsers",
        action="store_true",
        help="List available bank parsers",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # Setup
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard to configure accounts",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration",
    )

    # Lunch Money integration
    parser.add_argument(
        "--upload-lunchmoney",
        action="store_true",
        help="Upload to Lunch Money instead of writing CSV",
    )
    parser.add_argument(
        "--lm-api-key",
        help="Lunch Money API key (or configure in config.json)",
    )
    parser.add_argument(
        "--lm-setup",
        action="store_true",
        help="Interactive setup: map bank accounts to Lunch Money assets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )

    args = parser.parse_args()

    # Handle setup first (before loading config)
    if args.setup:
        from lunchsync_sg.setup import run_setup

        input_paths = [Path(p) for p in args.inputs] if args.inputs else None
        run_setup(input_paths=input_paths, api_key=args.lm_api_key)
        return 0

    # Load configuration
    config: dict[str, Any] | None = load_config(args.config)

    # Handle show-config
    if args.show_config:
        from lunchsync_sg.setup import show_current_config

        if config:
            show_current_config(config)
        else:
            print("No configuration found.")
            print("Run 'lunchsync-sg --setup' to create one.")
        return 0

    # List parsers and exit
    if args.list_parsers:
        print("Available parsers:")
        for parser_cls in ParserRegistry.get_all_parsers():
            print(f"  - {parser_cls.bank_name}: {parser_cls.__name__}")
            if parser_cls.file_patterns:
                print(f"    Patterns: {', '.join(parser_cls.file_patterns)}")
        return 0

    # Handle Lunch Money setup
    if args.lm_setup:
        from lunchsync_sg.lunchmoney import interactive_lm_setup

        api_key = get_lunchmoney_api_key(config, args.lm_api_key)
        if not api_key:
            print("Error: API key required. Use --lm-api-key or configure in config.json",
                  file=sys.stderr)
            return 1

        try:
            interactive_lm_setup(api_key, config)
        except Exception as e:
            print(f"Error during setup: {e}", file=sys.stderr)
            return 1
        return 0

    # Check if first run (no config and no inputs)
    if not config_exists() and not args.inputs:
        print("Welcome to lunchsync-sg!")
        print("\nNo configuration found. To set up, run:")
        print("  lunchsync-sg --setup ~/Downloads/bank-exports/")
        print("\nThis will scan your bank export files and guide you through setup.")
        return 0

    # Check for input files
    if not args.inputs:
        parser.print_help()
        return 1

    # Collect files
    files: list[Path] = []
    for inp in args.inputs:
        path = Path(inp)
        if path.is_dir():
            for ext in [".csv", ".xls", ".xlsx"]:
                files.extend(path.glob(f"*{ext}"))
                files.extend(path.glob(f"*{ext.upper()}"))
        elif path.exists():
            files.append(path)
        else:
            print(f"Warning: {inp} not found", file=sys.stderr)

    if not files:
        print("Error: No valid input files found", file=sys.stderr)
        return 1

    # Process files
    normalizer = BankNormalizer(
        deduplicate=not args.no_dedup,
        sort_descending=not args.no_sort,
        config=config,
    )

    transactions = normalizer.process_files(files)

    # Report results
    if args.verbose:
        for filepath, error in normalizer.errors:
            print(f"Warning: {filepath.name}: {error}", file=sys.stderr)

    print(f"Processed {len(files)} files", file=sys.stderr)
    print(f"Found {len(transactions)} transactions", file=sys.stderr)
    if normalizer.pending_skipped > 0:
        print(f"Skipped {normalizer.pending_skipped} pending transactions", file=sys.stderr)

    if normalizer.errors:
        print(f"Errors: {len(normalizer.errors)} files failed", file=sys.stderr)

    # Handle Lunch Money upload
    if args.upload_lunchmoney:
        from lunchsync_sg.lunchmoney import LunchMoneyClient, generate_external_id

        api_key = get_lunchmoney_api_key(config, args.lm_api_key)
        if not api_key:
            print("Error: API key required. Use --lm-api-key or configure in config.json",
                  file=sys.stderr)
            return 1

        account_mapping = get_lunchmoney_account_mapping(config)
        if not account_mapping:
            print("Error: No account mapping configured.", file=sys.stderr)
            print("Run 'lunchsync-sg --setup' or 'lunchsync-sg --lm-setup' to configure.",
                  file=sys.stderr)
            return 1

        # Show which accounts have mappings
        mapped_accounts = set(account_mapping.keys())
        tx_accounts = {tx.account for tx in transactions}
        unmapped = tx_accounts - mapped_accounts

        if args.verbose or args.dry_run:
            print("\nAccount mappings:", file=sys.stderr)
            for acc in sorted(tx_accounts):
                asset_id = account_mapping.get(acc)
                if asset_id:
                    print(f"  {acc} -> asset {asset_id}", file=sys.stderr)
                else:
                    print(f"  {acc} -> (not mapped, will skip)", file=sys.stderr)

        if unmapped:
            print(f"\nWarning: {len(unmapped)} unmapped accounts: {', '.join(sorted(unmapped))}",
                  file=sys.stderr)

        if args.dry_run:
            # Group transactions by account
            by_account: dict[str, list[Transaction]] = {}
            for tx in transactions:
                by_account.setdefault(tx.account, []).append(tx)

            print("\nDry run - transactions that would be uploaded:\n", file=sys.stderr)

            uploadable = 0
            skipped = 0

            for acc in sorted(by_account.keys()):
                txs = by_account[acc]
                asset_id = account_mapping.get(acc)

                if asset_id:
                    print(f"  {acc} -> asset {asset_id} ({len(txs)} transactions):",
                          file=sys.stderr)
                    for tx in txs:
                        ext_id = generate_external_id(tx)[:16] + "..."
                        print(f"    {tx.date}  {tx.amount:>10}  {tx.description[:40]:<40}  "
                              f"[{ext_id}]", file=sys.stderr)
                    uploadable += len(txs)
                else:
                    print(f"  {acc} (not mapped - {len(txs)} transactions skipped)",
                          file=sys.stderr)
                    skipped += len(txs)
                print(file=sys.stderr)

            print("Summary:", file=sys.stderr)
            print(f"  Would upload: {uploadable} transactions", file=sys.stderr)
            print(f"  Would skip (unmapped): {skipped} transactions", file=sys.stderr)
            if normalizer.pending_skipped > 0:
                print(f"  Skipped (pending): {normalizer.pending_skipped} transactions",
                      file=sys.stderr)
            print("\nNote: Lunch Money will also skip duplicates based on external_id "
                  "and date/payee/amount.", file=sys.stderr)
            return 0

        # Actually upload
        client = LunchMoneyClient(api_key)
        try:
            result = client.upload_transactions(transactions, account_mapping)
        except Exception as e:
            print(f"Error uploading: {e}", file=sys.stderr)
            return 1

        print("\nUpload complete:", file=sys.stderr)
        print(f"  Uploaded: {result.uploaded}", file=sys.stderr)
        print(f"  Skipped (duplicates/unmapped): {result.skipped}", file=sys.stderr)
        if result.errors:
            print(f"  Errors: {len(result.errors)}", file=sys.stderr)
            for error in result.errors:
                print(f"    - {error}", file=sys.stderr)

        return 0 if not result.errors else 1

    # Write output
    output_path = Path(args.output)
    delimiter = "\t" if args.format == "tsv" else ","

    if args.full:
        normalizer.write_full_csv(transactions, output_path, delimiter)
    else:
        normalizer.write_csv(transactions, output_path, delimiter)

    print(f"Wrote {len(transactions)} transactions to {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
