"""Sync HSBC, DBS, Citi, UOB and OCBC card alert emails from Fastmail into Lunch Money.

Only cards listed under `card_alerts` in config.json are synced, each from
its own start date, so alerts never overlap transactions already uploaded
from statement exports:

    "card_alerts": {"HSBC Revolution": "2026-11-03"}
"""

import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

from lunchsync_sg.card_alerts import (
    SOURCES,
    CardAlert,
    CardAlertError,
    pair_reversals,
    parse_card_alert,
    to_transaction,
)
from lunchsync_sg.config import get_lunchmoney_account_mapping, get_lunchmoney_api_key
from lunchsync_sg.fastmail import FastmailClient
from lunchsync_sg.lunchmoney import LunchMoneyClient, generate_external_id
from lunchsync_sg.models import Transaction

DEFAULT_LOOKBACK_DAYS = 45


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def card_alert_starts(config: dict[str, Any] | None) -> dict[str, date]:
    """Account name → first transaction date to take from alerts."""
    raw = (config or {}).get("card_alerts", {})
    return {account: date.fromisoformat(start) for account, start in raw.items()}


def accounts_by_last4(config: dict[str, Any] | None) -> dict[str, str]:
    """Last four card digits → account name, from config.json `accounts`."""
    digits = (
        ("".join(c for c in a.get("card_number", "") if c.isdigit()), a.get("name"))
        for a in (config or {}).get("accounts", [])
    )
    return {number[-4:]: name for number, name in digits if len(number) >= 4 and name}


def run_card_alert_sync(
    config: dict[str, Any] | None,
    since: date | None = None,
    dry_run: bool = False,
    lm_api_key: str | None = None,
) -> int:
    """Fetch card alerts since `since`, upload the ones Lunch Money lacks.

    Returns 1 if any alert failed to parse or upload, so a scheduler alerts.
    """
    token = os.environ.get("FASTMAIL_API_TOKEN")
    if not token:
        _err("Error: FASTMAIL_API_TOKEN is not set")
        return 1
    api_key = get_lunchmoney_api_key(config, lm_api_key)
    if not api_key:
        _err("Error: Lunch Money API key required (config.json or --lm-api-key)")
        return 1
    starts = card_alert_starts(config)
    if not starts:
        _err("Error: no cards listed under card_alerts in config.json")
        return 1
    asset_ids = get_lunchmoney_account_mapping(config)
    unmapped = [account for account in starts if account not in asset_ids]
    if unmapped:
        _err(f"Error: no Lunch Money asset mapped for {', '.join(unmapped)} in config.json")
        return 1
    by_last4 = accounts_by_last4(config)

    since = since or date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    # Emails are filtered in UTC; start a day early so SGT-morning alerts are kept.
    fetch_from = datetime.combine(since - timedelta(days=1), datetime.min.time(), UTC)
    fastmail = FastmailClient(token)

    failures: list[str] = []
    charges: dict[str, list[Transaction]] = {account: [] for account in starts}
    voided: dict[str, list[tuple[Transaction, Transaction]]] = {account: [] for account in starts}
    skipped = unmatched = 0
    for source in SOURCES:
        alerts: list[CardAlert] = []
        for email in fastmail.fetch_from(source.sender, fetch_from):
            try:
                alert = parse_card_alert(source, email.subject, email.html, email.message_id)
            except CardAlertError as e:
                failures.append(f"{email.received_at}: {e}")
                continue
            if alert:
                alerts.append(alert)
        batch = pair_reversals(alerts)
        unmatched += len(batch.unmatched_reversals)
        for alert, reversal in [(c, None) for c in batch.charges] + list(batch.voided):
            account = by_last4.get(alert.last4)
            if account is None:
                failures.append(f"{source.bank} card ending {alert.last4} is not in accounts")
            elif account not in starts:
                skipped += 1
            elif alert.when.date() >= max(since, starts[account]):
                charge = to_transaction(alert, account)
                if reversal is None:
                    charges[account].append(charge)
                else:
                    voided[account].append((charge, to_transaction(reversal, account)))

    lm = LunchMoneyClient(api_key)
    errors = list(failures)
    for account in starts:
        asset_id = asset_ids[account]
        first = max(since, starts[account])
        existing = lm.get_external_ids(
            asset_id, first.isoformat(), (date.today() + timedelta(days=1)).isoformat()
        )
        new = [tx for tx in charges[account] if generate_external_id(tx) not in existing]
        # A reversed charge already in Lunch Money is offset; one that never
        # went up is dropped along with its reversal.
        new += [
            reversal for charge, reversal in voided[account]
            if generate_external_id(charge) in existing
            and generate_external_id(reversal) not in existing
        ]
        new.sort(key=lambda tx: tx.date)
        _err(
            f"{account}: {len(charges[account])} charges since {first}, "
            f"{len(voided[account])} reversed, {len(new)} new"
        )
        _print_table(new)
        if new and not dry_run:
            result = lm.upload_transactions(
                new, {account: asset_id}, skip_duplicates=False, apply_rules=True
            )
            _err(f"  uploaded {result.uploaded} to asset {asset_id}")
            if result.uploaded != len(new):
                errors.append(
                    f"{account}: expected {len(new)} uploads, Lunch Money created {result.uploaded}"
                )
            errors.extend(result.errors)

    if skipped:
        _err(f"{skipped} alerts for cards not listed under card_alerts were ignored")
    if unmatched:
        _err(f"{unmatched} reversals of holds that sent no charge alert were ignored")
    for error in errors:
        _err(f"Error: {error}")
    return 1 if errors else 0


def _print_table(transactions: list[Transaction]) -> None:
    for tx in transactions:
        _err(f"  {tx.date}  {tx.original_currency} {tx.amount:>9}  {tx.description}")
