"""Post-upload transaction categorization workflow."""

from dataclasses import dataclass, field
from typing import Any

import requests

from lunchsync_sg.jev import JevClient
from lunchsync_sg.lunchmoney import LunchMoneyClient


@dataclass
class CategorizationResult:
    """Result of categorizing newly-created Lunch Money transactions."""

    categorized: int = 0
    already_categorized: int = 0
    unmatched: int = 0
    errors: list[str] = field(default_factory=list)


def _assignable_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique, active categories that may be assigned to transactions."""
    by_id: dict[int, dict[str, Any]] = {}
    for category in categories:
        if category.get("is_group") or category.get("archived"):
            continue
        by_id[int(category["id"])] = category
    return list(by_id.values())


def categorize_created_transactions(
    lunch_money: LunchMoneyClient,
    jev: JevClient,
    transaction_ids: list[int],
) -> CategorizationResult:
    """Use JEV for every newly-created transaction left uncategorized by LM rules."""
    result = CategorizationResult()

    try:
        categories = _assignable_categories(lunch_money.get_categories())
    except requests.RequestException as exc:
        result.errors.append(f"Unable to fetch Lunch Money categories: {exc}")
        return result

    if not categories:
        result.errors.append("No active assignable Lunch Money categories were found")
        return result

    for transaction_id in transaction_ids:
        try:
            transaction = lunch_money.get_transaction(transaction_id)
            if transaction.get("category_id") is not None:
                result.already_categorized += 1
                continue

            decision = jev.categorize(transaction, categories)
            if decision.category_id is None:
                result.unmatched += 1
                continue

            lunch_money.update_transaction_category(transaction_id, decision.category_id)
            result.categorized += 1
        except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
            result.errors.append(f"Transaction {transaction_id}: {exc}")

    return result
