"""HSBC bank parsers."""

import csv
import io
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class HSBCRevolutionParser(BankParser):
    """Parser for HSBC Revolution Card CSV exports."""

    bank_name: ClassVar[str] = "HSBC"
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
