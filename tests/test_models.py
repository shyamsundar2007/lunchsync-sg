"""Tests for data models."""

from datetime import date
from decimal import Decimal

import pytest

from lunchsync_sg.models import AccountMapping, Transaction


class TestTransaction:
    """Tests for Transaction model."""

    def test_create_transaction(self) -> None:
        """Test creating a basic transaction."""
        tx = Transaction(
            date=date(2026, 1, 30),
            description="SHOPEE SINGAPORE",
            amount=Decimal("-45.56"),
            account="OCBC Rewards",
        )
        assert tx.date == date(2026, 1, 30)
        assert tx.description == "SHOPEE SINGAPORE"
        assert tx.amount == Decimal("-45.56")
        assert tx.account == "OCBC Rewards"

    def test_is_expense(self) -> None:
        """Test is_expense property."""
        expense = Transaction(
            date=date(2026, 1, 30),
            description="Test",
            amount=Decimal("-100"),
            account="Test",
        )
        income = Transaction(
            date=date(2026, 1, 30),
            description="Test",
            amount=Decimal("100"),
            account="Test",
        )
        assert expense.is_expense is True
        assert expense.is_income is False
        assert income.is_expense is False
        assert income.is_income is True

    def test_empty_description_default(self) -> None:
        """Test empty description gets default value."""
        tx = Transaction(
            date=date(2026, 1, 30),
            description="",
            amount=Decimal("100"),
            account="Test",
        )
        assert tx.description == "(No description)"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        tx = Transaction(
            date=date(2026, 1, 30),
            description="SHOPEE",
            amount=Decimal("-45.56"),
            account="OCBC Rewards",
        )
        d = tx.to_dict()
        assert d["date"] == "2026-01-30"
        assert d["description"] == "SHOPEE"
        assert d["amount"] == "-45.56"
        assert d["account"] == "OCBC Rewards"

    def test_transaction_immutable(self) -> None:
        """Test that transactions are immutable (frozen)."""
        tx = Transaction(
            date=date(2026, 1, 30),
            description="Test",
            amount=Decimal("100"),
            account="Test",
        )
        with pytest.raises(AttributeError):
            tx.amount = Decimal("200")  # type: ignore


class TestAccountMapping:
    """Tests for AccountMapping model."""

    def test_exact_match(self) -> None:
        """Test exact identifier match."""
        mapping = AccountMapping(
            identifier="5400126102581483",
            name="OCBC Rewards",
            bank="OCBC",
        )
        assert mapping.matches("5400126102581483") is True

    def test_match_with_dashes(self) -> None:
        """Test match ignoring dashes."""
        mapping = AccountMapping(
            identifier="5400-1261-0258-1483",
            name="OCBC Rewards",
            bank="OCBC",
        )
        assert mapping.matches("5400126102581483") is True
        assert mapping.matches("5400-1261-0258-1483") is True

    def test_last_four_match(self) -> None:
        """Test match on last 4 digits."""
        mapping = AccountMapping(
            identifier="1483",
            name="OCBC Rewards",
            bank="OCBC",
        )
        assert mapping.matches("5400126102581483") is True
        assert mapping.matches("1483") is True

    def test_no_match(self) -> None:
        """Test non-matching identifier."""
        mapping = AccountMapping(
            identifier="5400126102581483",
            name="OCBC Rewards",
            bank="OCBC",
        )
        assert mapping.matches("1234567890123456") is False
