"""Reconcile statement exports with what is already in Lunch Money.

Alert emails put each charge in Lunch Money on the transaction date. A
statement export then gives the posting date (and, for foreign charges, the
SGD amount). Reconciling matches each statement line to a row by content,
not by external_id, because exports repeat sections and banks reword
descriptions between exports:

1. A row with the line's own external_id is already in: skip.
2. An alert row (external_id "bank:...") with the same amount, dated 0-7
   days before the line (any amount if the alert was in a foreign
   currency): move it to the posting date, note the transaction date, and
   take the statement's SGD amount.
3. Any other row with the same amount within 3 days (an earlier import with
   a different description): skip.
4. Otherwise the line is missing: insert it.

Alert rows inside the statement's dates that no line matched are reported;
they have usually not posted yet.
"""

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from lunchsync_sg.config import get_lunchmoney_account_mapping, get_lunchmoney_api_key
from lunchsync_sg.lunchmoney import LunchMoneyClient, generate_external_id
from lunchsync_sg.models import Transaction
from lunchsync_sg.normalizer import BankNormalizer

ALERT_PREFIXES = ("trust", "hsbc", "dbs", "citi", "uob", "ocbc")
MAX_POSTING_LAG = timedelta(days=7)
SAME_ROW_WINDOW = timedelta(days=3)

_TOKEN = re.compile(r"[A-Z0-9]{3,}")


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def is_alert_row(row: dict[str, Any]) -> bool:
    """Whether a Lunch Money row was created from an alert email."""
    return str(row.get("external_id") or "").split(":", 1)[0] in ALERT_PREFIXES


def lm_amount(row: dict[str, Any]) -> Decimal:
    """A row's amount with the importer's sign: negative is money out."""
    return -Decimal(row["amount"])


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.upper()))


def merchant_overlap(a: str, b: str) -> int:
    """Number of words (3+ letters or digits) two payee strings share."""
    return len(_tokens(a) & _tokens(b))


@dataclass
class Update:
    """Move an alert row to the statement's posting date and SGD amount."""

    row: dict[str, Any]
    line: Transaction
    fields: dict[str, Any]


@dataclass
class AccountPlan:
    """What reconciling one account's statement lines would change."""

    account: str
    asset_id: int
    lines: int = 0
    already_in: int = 0
    confirmed: int = 0  # alert rows already on the posting date
    updates: list[Update] = field(default_factory=list)
    inserts: list[Transaction] = field(default_factory=list)
    unposted_alerts: list[dict[str, Any]] = field(default_factory=list)


def plan_account(
    account: str, asset_id: int, lines: list[Transaction], rows: list[dict[str, Any]]
) -> AccountPlan:
    """Match one account's statement lines against its Lunch Money rows."""
    plan = AccountPlan(account=account, asset_id=asset_id, lines=len(lines))
    used: set[int] = set()

    def free(row: dict[str, Any]) -> bool:
        return row["id"] not in used

    for line in sorted(lines, key=lambda t: (t.date, t.amount, t.description)):
        ext = generate_external_id(line)
        if same := next((r for r in rows if free(r) and r.get("external_id") == ext), None):
            used.add(same["id"])
            plan.already_in += 1
            continue

        candidates = []
        for row in rows:
            if not free(row) or not is_alert_row(row):
                continue
            lag = line.date - date.fromisoformat(row["date"])
            if not timedelta(0) <= lag <= MAX_POSTING_LAG:
                continue
            foreign = row["currency"].lower() != line.original_currency.lower()
            if foreign:
                # Only the direction can be compared; the SGD amount is new.
                if (lm_amount(row) < 0) != (line.amount < 0):
                    continue
            elif lm_amount(row) != line.amount:
                continue
            overlap = merchant_overlap(row["payee"], line.description)
            if foreign and overlap == 0:
                continue
            candidates.append((lag, -overlap, row))
        if candidates:
            candidates.sort(key=lambda c: (c[0], c[1], c[2]["id"]))
            row = candidates[0][2]
            used.add(row["id"])
            fields: dict[str, Any] = {}
            if row["date"] != line.date.isoformat():
                fields["date"] = line.date.isoformat()
                note = f"txn date {row['date']}"
                fields["notes"] = f"{row['notes']} · {note}" if row.get("notes") else note
            if row["currency"].lower() != line.original_currency.lower():
                fields["amount"] = float(line.amount)
                fields["currency"] = line.original_currency.lower()
            if fields:
                plan.updates.append(Update(row=row, line=line, fields=fields))
            else:
                plan.confirmed += 1
            continue

        if other := next(
            (
                r for r in rows
                if free(r)
                and lm_amount(r) == line.amount
                and abs(date.fromisoformat(r["date"]) - line.date) <= SAME_ROW_WINDOW
            ),
            None,
        ):
            used.add(other["id"])
            plan.already_in += 1
            continue

        plan.inserts.append(line)

    if lines:
        first, last = min(t.date for t in lines), max(t.date for t in lines)
        plan.unposted_alerts = [
            r for r in rows
            if free(r) and is_alert_row(r)
            and first - MAX_POSTING_LAG <= date.fromisoformat(r["date"]) <= last
        ]
    return plan


def print_plan(plan: AccountPlan) -> None:
    _err(
        f"\n{plan.account}: {plan.lines} statement lines; {plan.already_in} already in, "
        f"{plan.confirmed} alert rows confirmed, {len(plan.updates)} to update, "
        f"{len(plan.inserts)} to add"
    )
    for u in plan.updates:
        moves = []
        if "date" in u.fields:
            moves.append(f"{u.row['date']} -> {u.fields['date']}")
        if "amount" in u.fields:
            moves.append(f"{u.row['currency'].upper()} {u.row['amount']} -> SGD {-u.line.amount}")
        _err(f"  update  {u.row['payee'][:40]:40}  {', '.join(moves)}")
    for tx in plan.inserts:
        _err(f"  add     {tx.date}  {tx.amount:>10}  {tx.description[:60]}")
    for r in plan.unposted_alerts:
        _err(f"  not on statement yet: {r['date']}  {r['amount']:>10}  {r['payee'][:50]}")


def run_reconcile(
    config: dict[str, Any] | None,
    paths: list[Path],
    apply: bool = False,
    lm_api_key: str | None = None,
) -> int:
    """Reconcile statement files with Lunch Money. Changes nothing unless `apply`."""
    api_key = get_lunchmoney_api_key(config, lm_api_key)
    if not api_key:
        _err("Error: Lunch Money API key required (config.json or --lm-api-key)")
        return 1
    asset_ids = get_lunchmoney_account_mapping(config)

    normalizer = BankNormalizer(deduplicate=False, config=config)
    files: list[Path] = []
    for path in paths:
        files.extend(
            sorted(p for p in path.iterdir() if p.suffix.lower() in (".csv", ".xls", ".xlsx"))
            if path.is_dir() else [path]
        )
    by_account: dict[str, list[Transaction]] = defaultdict(list)
    for f in files:
        txs = normalizer.process_file(f)
        accounts = sorted({t.account for t in txs})
        _err(f"{f.name}: {len(txs)} lines ({', '.join(accounts) or 'none'})")
        for tx in txs:
            by_account[tx.account].append(tx)
    errors = [f"{p.name}: {msg}" for p, msg in normalizer.errors]
    if normalizer.pending_skipped:
        _err(f"{normalizer.pending_skipped} unposted lines skipped (they post later)")

    lm = LunchMoneyClient(api_key)
    plans: list[AccountPlan] = []
    for account, lines in sorted(by_account.items()):
        asset_id = asset_ids.get(account)
        if asset_id is None:
            errors.append(f"{account}: no Lunch Money asset mapped in config.json")
            continue
        start = min(t.date for t in lines) - MAX_POSTING_LAG - SAME_ROW_WINDOW
        end = max(t.date for t in lines) + SAME_ROW_WINDOW
        rows = lm.get_transactions(asset_id, start.isoformat(), end.isoformat())
        plan = plan_account(account, asset_id, lines, rows)
        print_plan(plan)
        plans.append(plan)

    if apply:
        for plan in plans:
            for u in plan.updates:
                try:
                    lm.update_transaction(u.row["id"], u.fields)
                except Exception as e:
                    errors.append(f"{plan.account}: update {u.row['id']} failed: {e}")
            if plan.inserts:
                result = lm.upload_transactions(
                    plan.inserts, {plan.account: plan.asset_id},
                    skip_duplicates=False, apply_rules=True,
                )
                if result.uploaded != len(plan.inserts):
                    errors.append(
                        f"{plan.account}: expected {len(plan.inserts)} inserts, "
                        f"Lunch Money created {result.uploaded}"
                    )
                errors.extend(result.errors)
        updates = sum(len(p.updates) for p in plans)
        inserts = sum(len(p.inserts) for p in plans)
        _err(f"\nApplied: {updates} updated, {inserts} added")
    else:
        _err("\nPreview only: nothing changed (add --apply to make these changes)")

    for error in errors:
        _err(f"Error: {error}")
    return 1 if errors else 0
