"""Tests for bank parsers."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from lunchsync_sg.parsers import (
    CitiParser,
    DBSCreditParser,
    DBSSavingsParser,
    HSBCRevolutionParser,
    OCBC360Parser,
    OCBCCreditParser,
    ParserRegistry,
    UOBCreditParser,
)
from lunchsync_sg.utils import read_file


class TestOCBCCreditParser:
    """Tests for OCBC Credit Card parser."""

    def test_can_parse(self, ocbc_credit_file: Path) -> None:
        """Test format detection."""
        content = read_file(ocbc_credit_file)
        assert OCBCCreditParser.can_parse(content) is True

    def test_parse_transactions(self, ocbc_credit_file: Path) -> None:
        """Test parsing transactions."""
        content = read_file(ocbc_credit_file)
        parser = OCBCCreditParser()
        transactions = parser.parse(content)

        assert len(transactions) == 2

        # Check first transaction
        tx = transactions[0]
        assert tx.date == date(2026, 1, 30)
        assert "GROCERY" in tx.description
        assert tx.amount == Decimal("-300.00")
        assert "OCBC Rewards Test" in tx.account

    def test_parse_multiple_files(
        self, ocbc_credit_file: Path, ocbc_credit_file_2: Path
    ) -> None:
        """Test parsing multiple OCBC files."""
        parser = OCBCCreditParser()

        content1 = read_file(ocbc_credit_file)
        content2 = read_file(ocbc_credit_file_2)

        tx1 = parser.parse(content1)
        tx2 = parser.parse(content2)

        assert len(tx1) == 2
        assert len(tx2) == 8


class TestOCBC360Parser:
    """Tests for OCBC 360 Account parser."""

    def test_can_parse(self, ocbc_360_file: Path) -> None:
        """Test format detection."""
        content = read_file(ocbc_360_file)
        assert OCBC360Parser.can_parse(content) is True
        assert OCBCCreditParser.can_parse(content) is False

    def test_parse_transactions(self, ocbc_360_file: Path) -> None:
        """Test parsing transactions."""
        content = read_file(ocbc_360_file)
        parser = OCBC360Parser()
        transactions = parser.parse(content)

        assert len(transactions) >= 40  # Has many transactions

        # Check for expected transactions
        descriptions = [tx.description for tx in transactions]
        assert any("Swimming lessons" in d for d in descriptions)
        assert any("EMPLOYER" in d or "SALARY" in d for d in descriptions)

    def test_multiline_descriptions(self, ocbc_360_file: Path) -> None:
        """Test that multiline descriptions are handled."""
        content = read_file(ocbc_360_file)
        parser = OCBC360Parser()
        transactions = parser.parse(content)

        # All descriptions should be single-line (no newlines)
        for tx in transactions:
            assert "\n" not in tx.description


class TestDBSSavingsParser:
    """Tests for DBS Savings Account parser."""

    def test_can_parse(self, dbs_savings_file: Path) -> None:
        """Test format detection."""
        content = read_file(dbs_savings_file)
        assert DBSSavingsParser.can_parse(content) is True

    def test_parse_transactions(self, dbs_savings_file: Path) -> None:
        """Test parsing transactions."""
        content = read_file(dbs_savings_file)
        parser = DBSSavingsParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 5

        # Check for salary credit
        salaries = [tx for tx in transactions if tx.amount > 0]
        assert len(salaries) > 0


class TestDBSCreditParser:
    """Tests for DBS Credit Card parser."""

    def test_can_parse(self, dbs_credit_file: Path) -> None:
        """Test format detection."""
        content = read_file(dbs_credit_file)
        assert DBSCreditParser.can_parse(content) is True
        assert DBSSavingsParser.can_parse(content) is False

    def test_parse_transactions(self, dbs_credit_file: Path) -> None:
        """Test parsing transactions."""
        content = read_file(dbs_credit_file)
        parser = DBSCreditParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 4


class TestUOBCreditParser:
    """Tests for UOB Credit Card parser."""

    def test_can_parse_solitaire(self, uob_solitaire_file: Path) -> None:
        """Test format detection for Solitaire card."""
        content = read_file(uob_solitaire_file)
        assert UOBCreditParser.can_parse(content) is True

    def test_can_parse_platinum(self, uob_platinum_file: Path) -> None:
        """Test format detection for Platinum card."""
        content = read_file(uob_platinum_file)
        assert UOBCreditParser.can_parse(content) is True

    def test_parse_solitaire(self, uob_solitaire_file: Path) -> None:
        """Test parsing Solitaire transactions."""
        content = read_file(uob_solitaire_file)
        parser = UOBCreditParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 1
        assert any("Solitaire" in tx.account or "UOB" in tx.account for tx in transactions)

    def test_parse_platinum(self, uob_platinum_file: Path) -> None:
        """Test parsing Platinum transactions."""
        content = read_file(uob_platinum_file)
        parser = UOBCreditParser()
        transactions = parser.parse(content)

        # PENDING transactions are skipped, only settled ones are included
        assert len(transactions) >= 1
        # Verify no PENDING transactions made it through
        for tx in transactions:
            assert tx.date is not None


class TestHSBCRevolutionParser:
    """Tests for HSBC Revolution parser."""

    def test_can_parse(self, hsbc_file: Path) -> None:
        """Test format detection."""
        content = read_file(hsbc_file)
        assert HSBCRevolutionParser.can_parse(content) is True

    def test_parse_transactions(self, hsbc_file: Path) -> None:
        """Test parsing transactions."""
        content = read_file(hsbc_file)
        parser = HSBCRevolutionParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 2
        assert all(tx.account == "HSBC Revolution" for tx in transactions)


class TestCitiParser:
    """Tests for Citibank parser."""

    def test_can_parse_rewards(self, citi_rewards_file: Path) -> None:
        """Test format detection for Rewards card."""
        content = read_file(citi_rewards_file)
        assert CitiParser.can_parse(content) is True

    def test_can_parse_prestige(self, citi_prestige_file: Path) -> None:
        """Test format detection for Prestige card."""
        content = read_file(citi_prestige_file)
        assert CitiParser.can_parse(content) is True

    def test_parse_rewards(self, citi_rewards_file: Path) -> None:
        """Test parsing Rewards transactions."""
        content = read_file(citi_rewards_file)
        parser = CitiParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 3
        assert any("Citi Rewards" in tx.account for tx in transactions)

    def test_parse_prestige(self, citi_prestige_file: Path) -> None:
        """Test parsing Prestige transactions."""
        content = read_file(citi_prestige_file)
        parser = CitiParser()
        transactions = parser.parse(content)

        assert len(transactions) >= 5
        assert any("Citi Prestige" in tx.account for tx in transactions)


class TestParserRegistry:
    """Tests for ParserRegistry."""

    def test_get_parser_ocbc_credit(self, ocbc_credit_file: Path) -> None:
        """Test getting parser for OCBC credit."""
        content = read_file(ocbc_credit_file)
        parser = ParserRegistry.get_parser(content)
        assert isinstance(parser, OCBCCreditParser)

    def test_get_parser_dbs(self, dbs_savings_file: Path) -> None:
        """Test getting parser for DBS."""
        content = read_file(dbs_savings_file)
        parser = ParserRegistry.get_parser(content)
        assert isinstance(parser, DBSSavingsParser)

    def test_get_parser_unknown(self) -> None:
        """Test getting parser for unknown format."""
        parser = ParserRegistry.get_parser("random content that matches nothing")
        assert parser is None

    def test_list_all_parsers(self) -> None:
        """Test listing all parsers."""
        parsers = ParserRegistry.get_all_parsers()
        assert len(parsers) >= 7  # At least 7 parsers registered
