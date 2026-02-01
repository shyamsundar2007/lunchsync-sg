"""Data models for bank transactions."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Transaction:
    """Represents a normalized bank transaction."""

    date: date
    description: str
    amount: Decimal
    account: str
    original_currency: str = "SGD"
    original_amount: Decimal | None = None
    category: str | None = None
    reference: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Validate transaction data."""
        if not self.description.strip():
            object.__setattr__(self, "description", "(No description)")

    @property
    def is_expense(self) -> bool:
        """Return True if this is an expense (negative amount)."""
        return self.amount < 0

    @property
    def is_income(self) -> bool:
        """Return True if this is income (positive amount)."""
        return self.amount > 0

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for CSV output."""
        return {
            "date": self.date.isoformat(),
            "description": self.description,
            "amount": str(self.amount),
            "account": self.account,
            "original_currency": self.original_currency,
            "original_amount": str(self.original_amount) if self.original_amount else "",
            "category": self.category or "",
            "reference": self.reference or "",
        }


@dataclass
class AccountMapping:
    """Maps account identifiers to friendly names."""

    identifier: str
    name: str
    bank: str
    account_type: str = "credit_card"  # credit_card, savings, checking

    def matches(self, value: str) -> bool:
        """Check if value matches this account."""
        clean_value = value.replace("-", "").replace(" ", "")
        clean_id = self.identifier.replace("-", "").replace(" ", "")

        # Exact match
        if clean_value == clean_id:
            return True

        # Last 4 digits match
        return len(clean_value) >= 4 and clean_value[-4:] == clean_id[-4:]
