"""DBS bank parsers."""

import csv
import re
from io import StringIO
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class DBSSavingsParser(BankParser):
    """Parser for DBS Savings Account CSV exports."""

    bank_name: ClassVar[str] = "DBS"
    file_patterns: ClassVar[list[str]] = ["DBS Savings Account"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is DBS savings account format."""
        return "DBS Savings Account" in content and "Transaction Code" in content

    def parse(self, content: str) -> list[Transaction]:
        """Parse DBS savings account transactions."""
        transactions: list[Transaction] = []
        lines = content.strip().split("\n")

        # Extract account identifier
        account_id = "DBS Savings"
        for line in lines[:10]:
            match = re.search(r"DBS Savings Account\s+(\d{3}-\d-\d{6})", line)
            if match:
                account_id = match.group(1)
                break

        account_name = self.get_account_name(account_id)

        # Find transaction data
        in_transactions = False
        for line in lines:
            if "Transaction Date" in line and "Transaction Code" in line:
                in_transactions = True
                continue

            if not in_transactions:
                continue

            # Parse CSV properly
            try:
                reader = csv.reader(StringIO(line))
                parts = next(reader)
            except Exception:
                continue

            if len(parts) < 8:
                continue

            date_val = parse_date(parts[0])
            if not date_val:
                continue

            desc = clean_description(parts[2])
            debit = parse_amount(parts[7]) if len(parts) > 7 else None
            credit = parse_amount(parts[8]) if len(parts) > 8 else None

            if debit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=-debit,
                        account=account_name,
                        raw_data={"row": parts},
                    )
                )
            elif credit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=credit,
                        account=account_name,
                        raw_data={"row": parts},
                    )
                )

        return transactions


@ParserRegistry.register
class DBSCreditParser(BankParser):
    """Parser for DBS Credit Card CSV exports."""

    bank_name: ClassVar[str] = "DBS"
    file_patterns: ClassVar[list[str]] = ["DBS MasterCard", "DBS Credit Card"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is DBS credit card format."""
        return (
            "DBS MasterCard" in content or "Card Transaction Details" in content
        ) and "Transaction Posting Date" in content

    def parse(self, content: str) -> list[Transaction]:
        """Parse DBS credit card transactions."""
        transactions: list[Transaction] = []
        self.pending_skipped = 0  # Track skipped pending transactions
        lines = content.strip().split("\n")

        # Extract account identifier
        account_id = "DBS Card"
        for line in lines[:10]:
            match = re.search(r"(\d{4}-\d{4}-\d{4}-\d{4})", line)
            if match:
                account_id = match.group(1)
                break

        account_name = self.get_account_name(account_id)

        # Find transaction data
        in_transactions = False
        for line in lines:
            if "Transaction Date" in line and "Transaction Posting Date" in line:
                in_transactions = True
                continue

            if not in_transactions:
                continue

            try:
                reader = csv.reader(StringIO(line))
                parts = next(reader)
            except Exception:
                continue

            if len(parts) < 7:
                continue

            # Skip pending transactions (Transaction Status is in column 5)
            if len(parts) > 5 and parts[5].strip().lower() == "pending":
                self.pending_skipped += 1
                continue

            date_val = parse_date(parts[0])
            if not date_val:
                continue

            desc = clean_description(parts[2])
            debit = parse_amount(parts[6]) if len(parts) > 6 else None
            credit = parse_amount(parts[7]) if len(parts) > 7 else None

            if debit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=-debit,
                        account=account_name,
                        raw_data={"row": parts},
                    )
                )
            elif credit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=credit,
                        account=account_name,
                        raw_data={"row": parts},
                    )
                )

        return transactions
