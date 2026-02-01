"""Tests for utility functions."""

from datetime import date
from decimal import Decimal

from lunchsync_sg.utils import clean_description, parse_amount, parse_date


class TestParseDate:
    """Tests for parse_date function."""

    def test_dd_mm_yyyy_slash(self) -> None:
        """Test DD/MM/YYYY format."""
        assert parse_date("30/01/2026") == date(2026, 1, 30)
        assert parse_date("01/12/2025") == date(2025, 12, 1)

    def test_dd_mmm_yyyy(self) -> None:
        """Test DD MMM YYYY format."""
        assert parse_date("30 Jan 2026") == date(2026, 1, 30)
        assert parse_date("1 Dec 2025") == date(2025, 12, 1)

    def test_dd_mm_yyyy_dash(self) -> None:
        """Test DD-MM-YYYY format."""
        assert parse_date("30-01-2026") == date(2026, 1, 30)

    def test_yyyy_mm_dd(self) -> None:
        """Test YYYY-MM-DD format."""
        assert parse_date("2026-01-30") == date(2026, 1, 30)

    def test_quoted_date(self) -> None:
        """Test date with quotes."""
        assert parse_date('"30/01/2026"') == date(2026, 1, 30)

    def test_empty_string(self) -> None:
        """Test empty string returns None."""
        assert parse_date("") is None
        assert parse_date("   ") is None

    def test_invalid_date(self) -> None:
        """Test invalid date returns None."""
        assert parse_date("not a date") is None
        assert parse_date("32/01/2026") is None


class TestParseAmount:
    """Tests for parse_amount function."""

    def test_simple_amount(self) -> None:
        """Test simple numeric amount."""
        assert parse_amount("123.45") == Decimal("123.45")
        assert parse_amount("100") == Decimal("100")

    def test_negative_amount(self) -> None:
        """Test negative amount."""
        assert parse_amount("-123.45") == Decimal("-123.45")

    def test_thousands_separator(self) -> None:
        """Test amount with thousands separator."""
        assert parse_amount("1,234.56") == Decimal("1234.56")
        assert parse_amount("1,234,567.89") == Decimal("1234567.89")

    def test_currency_symbol(self) -> None:
        """Test amount with currency symbol."""
        assert parse_amount("SGD 123.45") == Decimal("123.45")
        assert parse_amount("$123.45") == Decimal("123.45")

    def test_quoted_amount(self) -> None:
        """Test quoted amount."""
        assert parse_amount('"123.45"') == Decimal("123.45")
        assert parse_amount('"1,234.56"') == Decimal("1234.56")

    def test_parentheses_negative(self) -> None:
        """Test negative amount in parentheses."""
        assert parse_amount("(123.45)") == Decimal("-123.45")

    def test_empty_string(self) -> None:
        """Test empty string returns None."""
        assert parse_amount("") is None
        assert parse_amount("   ") is None

    def test_invalid_amount(self) -> None:
        """Test invalid amount returns None."""
        assert parse_amount("not a number") is None


class TestCleanDescription:
    """Tests for clean_description function."""

    def test_extra_whitespace(self) -> None:
        """Test removal of extra whitespace."""
        assert clean_description("SHOPEE   SINGAPORE") == "SHOPEE SINGAPORE"
        assert clean_description("  SHOPEE  ") == "SHOPEE"

    def test_newlines(self) -> None:
        """Test removal of newlines."""
        assert clean_description("FAST PAYMENT\nOTHR-Test") == "FAST PAYMENT OTHR-Test"

    def test_card_mask_removal(self) -> None:
        """Test removal of card number masks."""
        assert "XXXX" not in clean_description("LUNCH MONEY XXXX-XXXX-XXXX-3403")
        assert "••••" not in clean_description("•••• •••• •••• 3363")

    def test_ref_number_removal(self) -> None:
        """Test removal of reference numbers."""
        assert "Ref No:" not in clean_description("GRAB Ref No: 123456789")

    def test_trailing_country_codes(self) -> None:
        """Test removal of trailing country codes."""
        result = clean_description("SHOPEE SINGAPORE SG")
        assert result == "SHOPEE SINGAPORE"

    def test_empty_string(self) -> None:
        """Test empty string handling."""
        assert clean_description("") == ""
        assert clean_description("   ") == ""
