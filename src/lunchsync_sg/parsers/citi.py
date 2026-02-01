"""Citibank parsers."""

import csv
import re
from io import StringIO
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, DetectedAccount, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class CitiParser(BankParser):
    """Parser for Citibank Credit Card CSV exports.

    Handles headerless CSV exports with format:
    "Date","Description","Amount","","'CardNumber'"
    """

    bank_name: ClassVar[str] = "Citi"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["ACCT_*.csv"]

    # Pattern for 16-digit card number with apostrophe wrapper
    CARD_PATTERN = re.compile(r"'(\d{16})'")

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is Citibank format.

        Detects headerless CSV with 5 columns: date, description, amount, empty, card_number.
        """
        # Strip BOM if present
        content = content.lstrip("\ufeff")

        lines = content.strip().split("\n")
        if not lines:
            return False

        # Check first data row structure
        try:
            reader = csv.reader(StringIO(lines[0]))
            row = next(reader)
        except (StopIteration, csv.Error):
            return False

        # Expect 5 columns: date, desc, amount, empty, card
        if len(row) != 5:
            return False

        # Check date format DD/MM/YYYY
        if not re.match(r"\d{2}/\d{2}/\d{4}", row[0]):
            return False

        # Check card number with apostrophe in last column
        if not cls.CARD_PATTERN.search(row[4]):
            return False

        return True

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect Citibank account from content."""
        content = content.lstrip("\ufeff")
        match = cls.CARD_PATTERN.search(content)
        if match:
            card_number = match.group(1)
            return DetectedAccount(
                card_number=card_number,
                bank=cls.bank_name,
                account_type=cls.account_type,
                display_hint="Citi Credit Card",
            )
        return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse Citibank transactions."""
        transactions: list[Transaction] = []

        # Strip BOM if present
        content = content.lstrip("\ufeff")

        reader = csv.reader(StringIO(content))

        for row in reader:
            if len(row) < 5:
                continue

            date_val = parse_date(row[0])
            if not date_val:
                continue

            desc = clean_description(row[1])
            amount = parse_amount(row[2])

            if amount is None:
                continue

            # Get card number from last column and look up account name
            match = self.CARD_PATTERN.search(row[4])
            card_num = match.group(1) if match else "Citi Card"
            account_name = self.get_account_name(card_num)

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
