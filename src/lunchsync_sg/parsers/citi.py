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
    """Parser for Citibank Credit Card CSV exports."""

    bank_name: ClassVar[str] = "Citi"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["5425123456780005", "5425987654321098"]

    # Card number to name mapping
    CARD_NAMES = {
        "5425123456780005": "Citi Rewards",
        "5425987654321098": "Citi Prestige",
    }

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is Citibank format."""
        # Citi has no header, just data rows with card number at the end
        return "'5425123456780005'" in content or "'5425987654321098'" in content

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect Citibank account from content."""
        # Look for card numbers in the content
        match = re.search(r"'(\d{16})'", content)
        if match:
            card_number = match.group(1)
            display_hint = cls.CARD_NAMES.get(card_number, "Citi Credit Card")
            return DetectedAccount(
                card_number=card_number,
                bank=cls.bank_name,
                account_type=cls.account_type,
                display_hint=display_hint,
            )
        return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse Citibank transactions."""
        transactions: list[Transaction] = []

        reader = csv.reader(StringIO(content))

        for row in reader:
            if len(row) < 4:
                continue

            date_val = parse_date(row[0])
            if not date_val:
                continue

            desc = clean_description(row[1])
            amount = parse_amount(row[2])

            # Get card number from last column
            card_num = row[-1].strip().strip("'")
            account_name = self.CARD_NAMES.get(card_num, self.get_account_name(card_num))

            if amount is None:
                continue

            # Citi: negative in file = expense
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
