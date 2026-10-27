"""Sync Trust card alert emails from Fastmail into Lunch Money."""

import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

from lunchsync_sg.config import get_lunchmoney_account_mapping, get_lunchmoney_api_key
from lunchsync_sg.fastmail import FastmailClient
from lunchsync_sg.lunchmoney import LunchMoneyClient, generate_external_id
from lunchsync_sg.models import Transaction
from lunchsync_sg.trust_email import (
    TRUST_SENDER,
    TrustAlert,
    TrustAlertError,
    build_batch,
    parse_alert,
)

DEFAULT_ACCOUNT = "Trust Freedom"
DEFAULT_LOOKBACK_DAYS = 45


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def run_trust_sync(
    config: dict[str, Any] | None,
    since: date | None = None,
    dry_run: bool = False,
    account: str = DEFAULT_ACCOUNT,
    lm_api_key: str | None = None,
) -> int:
    """Fetch Trust alerts since `since`, upload the ones Lunch Money lacks.

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
    asset_id = get_lunchmoney_account_mapping(config).get(account)
    if asset_id is None:
        _err(f"Error: no Lunch Money asset mapped for {account!r} in config.json")
        return 1

    since = since or date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    # Emails are filtered in UTC; start a day early so SGT-morning alerts are kept.
    fetch_from = datetime.combine(since - timedelta(days=1), datetime.min.time(), UTC)
    emails = FastmailClient(token).fetch_from(TRUST_SENDER, fetch_from)

    alerts: list[TrustAlert] = []
    failures: list[str] = []
    for email in emails:
        try:
            alert = parse_alert(email.subject, email.html, email.message_id)
        except TrustAlertError as e:
            failures.append(f"{email.received_at}: {e}")
            continue
        if alert and alert.when.date() >= since:
            alerts.append(alert)

    batch = build_batch(alerts, account)
    lm = LunchMoneyClient(api_key)
    existing = lm.get_external_ids(
        asset_id, since.isoformat(), (date.today() + timedelta(days=1)).isoformat()
    )

    new = [tx for tx in batch.transactions if generate_external_id(tx) not in existing]
    for purchase, cancellation in batch.voided:
        if (
            generate_external_id(purchase) in existing
            and generate_external_id(cancellation) not in existing
        ):
            new.append(cancellation)

    _err(
        f"Trust: {len(emails)} emails since {since}, {len(alerts)} alerts, "
        f"{len(batch.voided)} cancelled purchases, {len(new)} new transactions"
    )
    _print_table(new)

    errors = list(failures)
    if new and not dry_run:
        result = lm.upload_transactions(new, {account: asset_id}, skip_duplicates=False)
        _err(f"Uploaded {result.uploaded} to asset {asset_id}")
        if result.uploaded != len(new):
            errors.append(f"expected {len(new)} uploads, Lunch Money created {result.uploaded}")
        errors.extend(result.errors)
    elif dry_run:
        _err("Dry run: nothing uploaded")

    for error in errors:
        _err(f"Error: {error}")
    return 1 if errors else 0


def _print_table(transactions: list[Transaction]) -> None:
    for tx in transactions:
        _err(f"  {tx.date}  {tx.original_currency} {tx.amount:>9}  {tx.description}")
