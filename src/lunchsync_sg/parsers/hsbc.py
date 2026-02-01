"""HSBC bank parsers."""

import csv
import io
import re
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, DetectedAccount, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class HSBCRevolutionParser(BankParser):
    """Parser for HSBC Revolution Card CSV exports."""

    bank_name: ClassVar[str] = "HSBC"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["3363", "HSBC"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is HSBC Revolution format."""
        # HSBC has a simple format without headers
        # Look for masked card number pattern and AXS payment pattern
        return (
            "•••• •••• •••• 3363" in content
            or ("PYMT @ AXS" in content.upper() and "3363" in content)
        )

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect HSBC Revolution account from content."""
        # HSBC shows masked card numbers, try to find last 4 digits
        match = re.search(r"•••• •••• •••• (\d{4})", content)
        if match:
            return DetectedAccount(
                card_number=match.group(1),
                bank=cls.bank_name,
                account_type=cls.account_type,
                display_hint="HSBC Revolution",
            )
        # Fallback - look for 4-digit numbers that might be card endings
        if "3363" in content:
            return DetectedAccount(
                card_number="3363",
                bank=cls.bank_name,
                account_type=cls.account_type,
                display_hint="HSBC Revolution",
            )
        return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse HSBC Revolution transactions."""
        transactions: list[Transaction] = []
        account_name = "HSBC Revolution"

        # Use CSV reader to properly handle quoted fields with commas
        reader = csv.reader(io.StringIO(content))

        for row in reader:
            if len(row) < 3:
                continue

            date_val = parse_date(row[0])
            if not date_val:
                continue

            desc = clean_description(row[1])

            # Amount is in the last column
            amount_str = row[-1].strip()
            amount = parse_amount(amount_str)

            if amount is None:
                continue

            # HSBC: negative in file = expense, positive = payment
            transactions.append(
                Transaction(
                    date=date_val,
                    description=desc,
                    amount=amount,  # Sign is already correct
                    account=account_name,
                    raw_data={"row": row},
                )
            )

        return transactions
