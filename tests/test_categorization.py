"""Tests for post-upload categorization."""

from unittest.mock import MagicMock

from lunchsync_sg.categorization import categorize_created_transactions
from lunchsync_sg.jev import CategorizationDecision


def test_categorizes_only_transactions_unmatched_by_rules() -> None:
    """Test read-back skips transactions already categorized by Lunch Money."""
    lunch_money = MagicMock()
    lunch_money.get_categories.return_value = [
        {"id": 10, "name": "Food", "is_group": True},
        {"id": 11, "name": "Restaurants", "is_group": False, "archived": False},
        {"id": 12, "name": "Old", "is_group": False, "archived": True},
    ]
    lunch_money.get_transaction.side_effect = [
        {"id": 1, "category_id": 11},
        {"id": 2, "category_id": None, "payee": "Cafe", "amount": "-5.00"},
    ]
    jev = MagicMock()
    jev.categorize.return_value = CategorizationDecision(category_id=11, confidence=0.5)

    result = categorize_created_transactions(lunch_money, jev, [1, 2])

    assert result.already_categorized == 1
    assert result.categorized == 1
    assert result.unmatched == 0
    jev.categorize.assert_called_once()
    lunch_money.update_transaction_category.assert_called_once_with(2, 11)


def test_leaves_jev_unmatched_transaction_uncategorized() -> None:
    """Test an unmatched JEV decision does not update Lunch Money."""
    lunch_money = MagicMock()
    lunch_money.get_categories.return_value = [
        {"id": 11, "name": "Restaurants", "is_group": False, "archived": False}
    ]
    lunch_money.get_transaction.return_value = {"id": 2, "category_id": None}
    jev = MagicMock()
    jev.categorize.return_value = CategorizationDecision(category_id=None, confidence=0.7)

    result = categorize_created_transactions(lunch_money, jev, [2])

    assert result.unmatched == 1
    assert result.categorized == 0
    lunch_money.update_transaction_category.assert_not_called()
