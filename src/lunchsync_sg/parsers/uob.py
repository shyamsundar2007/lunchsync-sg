"""UOB bank parsers."""

import csv
import io
import re
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import BankParser, ParserRegistry
from lunchsync_sg.utils import clean_description, parse_amount, parse_date


@ParserRegistry.register
class UOBCreditParser(BankParser):
    """Parser for UOB Credit Card exports (XLS format converted to CSV)."""

    bank_name: ClassVar[str] = "UOB"
    file_patterns: ClassVar[list[str]] = ["United Overseas Bank", "LADY'S SOLITAIRE", "PREFERRED PLATINUM"]

    @classmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """Check if content is UOB credit card format."""
        content_upper = content.upper()
        return (
            "UNITED OVERSEAS BANK" in content_upper
            and ("LADY'S SOLITAIRE" in content_upper or "PREFERRED PLATINUM" in content_upper)
            and "TRANSACTION DATE" in content_upper
        )

    def parse(self, content: str) -> list[Transaction]:
        """Parse UOB credit card transactions."""
        transactions: list[Transaction] = []
        self.pending_skipped = 0  # Track skipped pending transactions

        # Detect card type and get account name
        content_upper = content.upper()
        if "LADY'S SOLITAIRE" in content_upper:
            account_name = "UOB Lady's Solitaire"
        elif "PREFERRED PLATINUM" in content_upper:
            account_name = "UOB Platinum VISA"
        else:
            account_name = "UOB Card"

        # Try to get account name from account number in header
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
