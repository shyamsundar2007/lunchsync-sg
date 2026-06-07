"""American Express parsers."""

import csv
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, DetectedAccount, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount


@ParserRegistry.register
class AmexParser(BankParser):
    """Parser for American Express CSV activity exports (e.g. KrisFlyer Ascend).

    Handles headered CSV exports with columns:
    Date,Description,Amount,Extended Details,Appears On Your Statement As,
    Address,City/State,Zip Code,Country,Reference

    Notes:
    - Dates are US-style MM/DD/YYYY
    - Charges are positive in the export, payments/credits negative
    - The export contains no card number, so a fixed "AMEX" identifier
      is used for account name lookup
    """

    bank_name: ClassVar[str] = "AMEX"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["activity*.csv"]

    # "Extended Details" column is unique to AMEX exports among supported banks
    HEADER_MARKER = "Extended Details"

    # AMEX exports carry no card number; use a fixed identifier for mapping lookup
    ACCOUNT_IDENTIFIER = "AMEX"

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is AMEX activity export format.

        Detects the distinctive "Extended Details" column in the header row.
        """
        content = content.lstrip("\ufeff")
        first_line = content.split("\n", 1)[0]
        return cls.HEADER_MARKER in first_line

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect AMEX account from content.

        The export has no card number, so a fixed identifier is returned.
        """
        if not cls.can_parse(content):
            return None
        return DetectedAccount(
            card_number=cls.ACCOUNT_IDENTIFIER,
            bank=cls.bank_name,
            account_type=cls.account_type,
            display_hint="AMEX Credit Card",
        )

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        """Parse AMEX MM/DD/YYYY date format."""
        try:
            return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
        except ValueError:
            return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse AMEX transactions."""
        transactions: list[Transaction] = []

        content = content.lstrip("\ufeff")
        reader = csv.DictReader(StringIO(content))
        account_name = self.get_account_name(self.ACCOUNT_IDENTIFIER)

        for row in reader:
            date_val = self._parse_date(row.get("Date") or "")
            if not date_val:
                continue

            desc = clean_description(row.get("Description") or "")
            amount = parse_amount(row.get("Amount") or "")

            if amount is None:
                continue

            reference = (row.get("Reference") or "").strip().strip("'") or None

            transactions.append(
                Transaction(
                    date=date_val,
                    description=desc,
                    amount=-amount,  # AMEX: charges positive, credits negative
                    account=account_name,
                    reference=reference,
                    raw_data={"row": row},
                )
            )

        return transactions
