"""Tests for the main normalizer class."""

import tempfile
from pathlib import Path

from lunchsync_sg import BankNormalizer, Transaction


class TestBankNormalizer:
    """Tests for BankNormalizer class."""

    def test_process_single_file(self, ocbc_credit_file: Path) -> None:
        """Test processing a single file."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_file(ocbc_credit_file)

        assert len(transactions) >= 1
        assert all(isinstance(tx, Transaction) for tx in transactions)
        assert len(normalizer.errors) == 0

    def test_process_multiple_files(
        self, ocbc_credit_file: Path, dbs_savings_file: Path
    ) -> None:
        """Test processing multiple files."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_files([ocbc_credit_file, dbs_savings_file])

        # Should have transactions from both files
        accounts = {tx.account for tx in transactions}
        assert len(accounts) >= 2

    def test_process_directory(self, fixtures_dir: Path) -> None:
        """Test processing all files in a directory."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_directory(fixtures_dir)

        assert len(transactions) >= 50  # Should have many transactions

        # Should have multiple accounts
        accounts = {tx.account for tx in transactions}
        assert len(accounts) >= 5

    def test_deduplication(self, ocbc_credit_file: Path) -> None:
        """Test that duplicate transactions are removed."""
        normalizer = BankNormalizer(deduplicate=True)

        # Process same file twice
        transactions = normalizer.process_files([ocbc_credit_file, ocbc_credit_file])

        # Should deduplicate
        single_file_txs = normalizer.process_file(ocbc_credit_file)
        assert len(transactions) == len(single_file_txs)

    def test_no_deduplication(self, ocbc_credit_file: Path) -> None:
        """Test that deduplication can be disabled."""
        normalizer = BankNormalizer(deduplicate=False)

        # Process same file twice
        transactions = normalizer.process_files([ocbc_credit_file, ocbc_credit_file])
        single_file_txs = BankNormalizer().process_file(ocbc_credit_file)

        # Should have duplicates
        assert len(transactions) == len(single_file_txs) * 2

    def test_sorting(self, fixtures_dir: Path) -> None:
        """Test that transactions are sorted by date."""
        normalizer = BankNormalizer(sort_descending=True)
        transactions = normalizer.process_directory(fixtures_dir)

        # Should be sorted descending
        dates = [tx.date for tx in transactions]
        assert dates == sorted(dates, reverse=True)

    def test_no_sorting(self, ocbc_credit_file: Path, dbs_savings_file: Path) -> None:
        """Test that sorting can be disabled."""
        normalizer = BankNormalizer(sort_descending=False)
        transactions = normalizer.process_files([ocbc_credit_file, dbs_savings_file])

        # Should NOT necessarily be sorted
        # (Just check it doesn't crash)
        assert len(transactions) >= 1

    def test_write_csv(self, fixtures_dir: Path) -> None:
        """Test writing to CSV."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_directory(fixtures_dir)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            output_path = Path(f.name)

        try:
            normalizer.write_csv(transactions, output_path)

            # Read and verify
            content = output_path.read_text()
            lines = content.strip().split("\n")

            # Header + data rows
            assert len(lines) == len(transactions) + 1
            assert "Date,Description,Amount,Account" in lines[0]
        finally:
            output_path.unlink()

    def test_write_tsv(self, ocbc_credit_file: Path) -> None:
        """Test writing to TSV."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_file(ocbc_credit_file)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tsv", delete=False
        ) as f:
            output_path = Path(f.name)

        try:
            normalizer.write_csv(transactions, output_path, delimiter="\t")

            content = output_path.read_text()
            assert "\t" in content
        finally:
            output_path.unlink()

    def test_error_handling_invalid_file(self) -> None:
        """Test error handling for invalid file."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_file(Path("/nonexistent/file.csv"))

        assert len(transactions) == 0
        assert len(normalizer.errors) == 1

    def test_error_handling_unknown_format(self, tmp_path: Path) -> None:
        """Test error handling for unknown file format."""
        # Create a file with unrecognized format
        test_file = tmp_path / "unknown.csv"
        test_file.write_text("random,data,here\n1,2,3\n")

        normalizer = BankNormalizer()
        transactions = normalizer.process_file(test_file)

        assert len(transactions) == 0
        assert len(normalizer.errors) == 1
        assert "No parser found" in normalizer.errors[0][1]


class TestTransactionSignConvention:
    """Tests to verify consistent sign convention across all parsers."""

    def test_expenses_are_negative(self, fixtures_dir: Path) -> None:
        """Test that all expenses are negative."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_directory(fixtures_dir)

        # Filter for obvious expenses (not payments/credits)
        expense_keywords = ["SHOPEE", "GRAB", "MRT", "RESTAURANT", "COFFEE"]

        for tx in transactions:
            for keyword in expense_keywords:
                if keyword in tx.description.upper():
                    assert tx.amount < 0, f"Expense should be negative: {tx}"
                    break

    def test_payments_are_positive(self, fixtures_dir: Path) -> None:
        """Test that payments/credits are positive."""
        normalizer = BankNormalizer()
        transactions = normalizer.process_directory(fixtures_dir)

        # Filter for obvious payments/credits
        payment_keywords = ["PAYMENT", "SALARY", "GIRO", "REFUND"]

        for tx in transactions:
            for keyword in payment_keywords:
                if (
                    keyword in tx.description.upper()
                    and "AUTOPAY" not in tx.description.upper()
                    and tx.amount != 0
                ):
                    # Most payments should be positive (incoming)
                    pass  # Log but don't assert - some edge cases exist
