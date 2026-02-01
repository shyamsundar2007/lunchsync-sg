"""OCBC bank parsers."""

import csv
import re
from io import StringIO
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, DetectedAccount, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class OCBCCreditParser(BankParser):
    """Parser for OCBC Credit Card CSV exports."""

    bank_name: ClassVar[str] = "OCBC"
    account_type: ClassVar[str] = "credit_card"
    file_patterns: ClassVar[list[str]] = ["OCBC Rewards Card", "OCBC Credit Card"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is OCBC credit card format."""
        return (
            "OCBC Rewards Card" in content or "OCBC Credit Card" in content
        ) and "Transaction date,Description,Withdrawals" in content

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect OCBC credit card account from content."""
        for line in content.split("\n")[:10]:
            match = re.search(r"(\d{4}-\d{4}-\d{4}-\d{4})", line)
            if match:
                return DetectedAccount(
                    card_number=match.group(1),
                    bank=cls.bank_name,
                    account_type=cls.account_type,
                    display_hint="OCBC Credit Card",
                )
        return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse OCBC credit card transactions."""
        transactions: list[Transaction] = []
        lines = content.strip().split("\n")

        # Extract account identifier
        account_id = "OCBC Card"
        for line in lines[:10]:
            match = re.search(r"(\d{4}-\d{4}-\d{4}-\d{4})", line)
            if match:
                account_id = match.group(1)
                break

        account_name = self.get_account_name(account_id)

        # Find transaction data start
        in_transactions = False
        for line in lines:
            if "Transaction date,Description,Withdrawals" in line:
                in_transactions = True
                continue

            if not in_transactions:
                continue

            parts = line.split(",")
            if len(parts) < 3:
                continue

            date_val = parse_date(parts[0])
            if not date_val:
                continue

            desc = clean_description(parts[1])
            withdrawal = parse_amount(parts[2]) if len(parts) > 2 else None
            deposit = parse_amount(parts[3]) if len(parts) > 3 else None

            if withdrawal:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=-withdrawal,  # Expense is negative
                        account=account_name,
                        raw_data={"line": line},
                    )
                )
            elif deposit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=deposit,  # Credit is positive
                        account=account_name,
                        raw_data={"line": line},
                    )
                )

        return transactions


@ParserRegistry.register
class OCBC360Parser(BankParser):
    """Parser for OCBC 360 Account CSV exports."""

    bank_name: ClassVar[str] = "OCBC"
    account_type: ClassVar[str] = "savings"
    file_patterns: ClassVar[list[str]] = ["360 Account"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is OCBC 360 account format."""
        return "360 Account" in content and "Transaction date,Value date,Description" in content

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """Detect OCBC 360 account from content."""
        for line in content.split("\n")[:10]:
            match = re.search(r"(\d{3}-\d{6}-\d{3})", line)
            if match:
                return DetectedAccount(
                    card_number=match.group(1),
                    bank=cls.bank_name,
                    account_type=cls.account_type,
                    display_hint="OCBC 360 Account",
                )
        return None

    def parse(self, content: str) -> list[Transaction]:
        """Parse OCBC 360 account transactions."""
        transactions: list[Transaction] = []

        # Extract account identifier
        account_id = "OCBC 360"
        for line in content.split("\n")[:10]:
            match = re.search(r"(\d{3}-\d{6}-\d{3})", line)
            if match:
                account_id = match.group(1)
                break

        account_name = self.get_account_name(account_id)

        # Find where transaction data starts
        header_idx = content.find("Transaction date,Value date,Description")
        if header_idx == -1:
            return transactions

        csv_content = content[header_idx:]
        reader = csv.reader(StringIO(csv_content))

        # Skip header
        try:
            next(reader)
        except StopIteration:
            return transactions

        for row in reader:
            if len(row) < 5:
                continue

            date_val = parse_date(row[0])
            if not date_val:
                continue

            desc = clean_description(row[2])
            withdrawal = parse_amount(row[3])
            deposit = parse_amount(row[4])

            if withdrawal:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=-withdrawal,
                        account=account_name,
                        raw_data={"row": row},
                    )
                )
            elif deposit:
                transactions.append(
                    Transaction(
                        date=date_val,
                        description=desc,
                        amount=deposit,
                        account=account_name,
                        raw_data={"row": row},
                    )
                )

        return transactions
