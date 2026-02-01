"""Main normalizer class that orchestrates parsing."""

import csv
from datetime import date
from pathlib import Path
from typing import Any

from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers.base import ParserRegistry
from lunchsync_sg.utils import read_file


class BankNormalizer:
    """
    Main class for normalizing bank transaction exports.

    Usage:
        normalizer = BankNormalizer()
        transactions = normalizer.process_files([Path("file1.csv"), Path("file2.xls")])
        normalizer.write_csv(transactions, Path("output.csv"))
    """

    def __init__(
        self,
        deduplicate: bool = True,
        sort_descending: bool = True,
        config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize normalizer.

        Args:
            deduplicate: Remove duplicate transactions
            sort_descending: Sort by date descending (newest first)
            config: Loaded JSON config for account mappings
        """
        self.deduplicate = deduplicate
        self.sort_descending = sort_descending
        self.config = config
        self._errors: list[tuple[Path, str]] = []
        self._pending_skipped = 0

    @property
    def errors(self) -> list[tuple[Path, str]]:
        """Get list of (filepath, error_message) for failed files."""
        return self._errors.copy()

    @property
    def pending_skipped(self) -> int:
        """Get count of pending transactions that were skipped."""
        return self._pending_skipped

    def process_file(self, filepath: Path) -> list[Transaction]:
        """
        Process a single file and return transactions.

        Args:
            filepath: Path to the file

        Returns:
            List of Transaction objects
        """
        try:
            content = read_file(filepath)
        except ValueError as e:
            self._errors.append((filepath, str(e)))
            return []

        parser = ParserRegistry.get_parser(content, filepath, config=self.config)
        if parser is None:
            self._errors.append((filepath, "No parser found for this file format"))
            return []

        try:
            transactions = parser.parse(content)
            # Track pending skipped if parser supports it
            if hasattr(parser, "pending_skipped"):
                self._pending_skipped += parser.pending_skipped
            return transactions
        except Exception as e:
            self._errors.append((filepath, f"Parse error: {e}"))
            return []

    def process_files(self, filepaths: list[Path]) -> list[Transaction]:
        """
        Process multiple files and return combined transactions.

        Args:
            filepaths: List of file paths

        Returns:
            List of Transaction objects (deduplicated and sorted if configured)
        """
        self._errors = []
        self._pending_skipped = 0
        all_transactions: list[Transaction] = []

        for filepath in filepaths:
            transactions = self.process_file(filepath)
            all_transactions.extend(transactions)

        if self.deduplicate:
            all_transactions = self._deduplicate(all_transactions)

        if self.sort_descending:
            all_transactions.sort(key=lambda t: t.date, reverse=True)

        return all_transactions

    def process_directory(
        self, directory: Path, extensions: list[str] | None = None
    ) -> list[Transaction]:
        """
        Process all matching files in a directory.

        Args:
            directory: Directory path
            extensions: File extensions to include (default: csv, xls, xlsx)

        Returns:
            List of Transaction objects
        """
        if extensions is None:
            extensions = [".csv", ".xls", ".xlsx"]

        files: list[Path] = []
        for ext in extensions:
            files.extend(directory.glob(f"*{ext}"))
            files.extend(directory.glob(f"*{ext.upper()}"))

        return self.process_files(files)

    def _deduplicate(self, transactions: list[Transaction]) -> list[Transaction]:
        """Remove duplicate transactions."""
        seen: set[tuple[date, str, str, str]] = set()
        unique: list[Transaction] = []

        for tx in transactions:
            # Key on date, description (first 30 chars), amount, account
            key = (
                tx.date,
                tx.description[:30],
                str(tx.amount),
                tx.account,
            )
            if key not in seen:
                seen.add(key)
                unique.append(tx)

        return unique

    @staticmethod
    def write_csv(
        transactions: list[Transaction],
        output_path: Path,
        delimiter: str = ",",
    ) -> None:
        """
        Write transactions to CSV file.

        Args:
            transactions: List of transactions
            output_path: Output file path
            delimiter: CSV delimiter (default comma)
        """
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(["Date", "Description", "Amount", "Account"])
            for tx in transactions:
                writer.writerow([
                    tx.date.isoformat(),
                    tx.description,
                    str(tx.amount),
                    tx.account,
                ])

    @staticmethod
    def write_full_csv(
        transactions: list[Transaction],
        output_path: Path,
        delimiter: str = ",",
    ) -> None:
        """
        Write transactions to CSV with all fields.

        Args:
            transactions: List of transactions
            output_path: Output file path
            delimiter: CSV delimiter
        """
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "date",
                    "description",
                    "amount",
                    "account",
                    "original_currency",
                    "original_amount",
                    "category",
                    "reference",
                ],
                delimiter=delimiter,
            )
            writer.writeheader()
            for tx in transactions:
                writer.writerow(tx.to_dict())
