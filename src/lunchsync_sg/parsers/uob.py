"""UOB bank parsers."""

import csv
import io
import re
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, DetectedAccount, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class UOBCreditParser(BankParser):
    """Parser for UOB Credit Card exports (XLS format converted to CSV)."""

    bank_name: ClassVar[str] = "UOB"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["United Overseas Bank"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is UOB credit card format."""
        content_upper = content.upper()
        return (
            "UNITED OVERSEAS BANK" in content_upper
            and "TRANSACTION DATE" in content_upper
            and "POSTING DATE" in content_upper
        )

    @classmethod
    def _extract_card_type(cls, content: str) -> str:
        """Extract card type from Account Type field in header."""
        for line in content.split("\n")[:15]:
            match = re.search(r"Account Type:,(.+?)(?:,|$)", line)
            if match:
                return match.group(1).strip()
        return ""

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect UOB credit card account from content."""
        card_type = cls._extract_card_type(content)
        display_hint = f"UOB {card_type}" if card_type else "UOB Credit Card"

        # Try to find account number
        for line in content.split("\n")[:15]:
            match = re.search(r"Account Number:,(\d+)", line)
            if match:
                return DetectedAccount(
                    card_number=match.group(1),
                    bank=cls.bank_name,
                    account_type=cls.account_type,
                    display_hint=display_hint,
                )

        return DetectedAccount(
            card_number="",
            bank=cls.bank_name,
            account_type=cls.account_type,
            display_hint=display_hint,
        )

    def parse(self, content: str) -> list[Transaction]:
        """Parse UOB credit card transactions."""
        transactions: list[Transaction] = []
        self.pending_skipped = 0  # Track skipped pending transactions

        # Derive account name from card type or account number
        card_type = self._extract_card_type(content)
        account_name = f"UOB {card_type}" if card_type else "UOB Card"

        # Try to get mapped account name from account number in header
        for line in content.split("\n")[:15]:
            match = re.search(r"Account Number:,(\d+)", line)
            if match:
                account_name = self.get_account_name(match.group(1))
                break

        # Use CSV reader to properly handle quoted multiline fields
        reader = csv.reader(io.StringIO(content))
        in_transactions = False

        for row in reader:
            if not row:
                continue

            # Check for header row
            if len(row) >= 3 and "Transaction Date" in row[0] and "Posting Date" in row[1]:
                in_transactions = True
                continue

            if not in_transactions:
                continue

            # Skip rows that don't have enough columns
            if len(row) < 7:
                continue

            # Skip "Previous Balance" rows
            if any("Previous Balance" in cell for cell in row):
                continue

            # Skip PENDING transactions - only include settled ones
            posting_date = row[1].strip()
            if posting_date.upper() == "PENDING":
                self.pending_skipped += 1
                continue

            # Use Posting Date (row[1]), not Transaction Date (row[0])
            date_val = parse_date(posting_date)
            if not date_val:
                continue

            desc = clean_description(row[2])

            # Amount is in the last column (Transaction Amount Local)
            amount_str = row[-1].strip()
            if not amount_str:
                amount_str = row[-2].strip() if len(row) >= 2 else ""

            amount = parse_amount(amount_str)
            if amount is None:
                continue

            # UOB: negative = payment/credit, positive = expense
            # So we flip the sign
            transactions.append(
                Transaction(
                    date=date_val,
                    description=desc,
                    amount=-amount,
                    account=account_name,
                    raw_data={"row": row},
                )
            )

        return transactions
