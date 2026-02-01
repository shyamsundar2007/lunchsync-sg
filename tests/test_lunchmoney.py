"""Tests for Lunch Money integration."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from lunchsync_sg.lunchmoney import (
    LunchMoneyClient,
    UploadResult,
    format_account_mapping,
    generate_external_id,
    transaction_to_payload,
)
from lunchsync_sg.models import Transaction


class TestGenerateExternalId:
    """Tests for external ID generation."""

    def test_uses_reference_if_present(self) -> None:
        """Test that reference is used when available."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="Test transaction",
            amount=Decimal("-50.00"),
            account="Test Account",
            reference="REF123456",
        )
        assert generate_external_id(tx) == "REF123456"

    def test_truncates_long_reference(self) -> None:
        """Test that long references are truncated to 75 chars."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="Test transaction",
            amount=Decimal("-50.00"),
            account="Test Account",
            reference="X" * 100,
        )
        result = generate_external_id(tx)
        assert len(result) == 75
        assert result == "X" * 75

    def test_generates_hash_without_reference(self) -> None:
        """Test hash generation when no reference exists."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="Test transaction",
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        result = generate_external_id(tx)
        # SHA256 hex digest is 64 chars, which is under 75 char API limit
        assert len(result) == 64
        # Should be hex characters only
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_is_deterministic(self) -> None:
        """Test that same transaction generates same hash."""
        tx1 = Transaction(
            date=date(2024, 1, 15),
            description="Test transaction",
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        tx2 = Transaction(
            date=date(2024, 1, 15),
            description="Test transaction",
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        assert generate_external_id(tx1) == generate_external_id(tx2)

    def test_different_transactions_different_hash(self) -> None:
        """Test that different transactions generate different hashes."""
        tx1 = Transaction(
            date=date(2024, 1, 15),
            description="Transaction A",
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        tx2 = Transaction(
            date=date(2024, 1, 15),
            description="Transaction B",
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        assert generate_external_id(tx1) != generate_external_id(tx2)


class TestTransactionToPayload:
    """Tests for transaction to payload conversion."""

    def test_basic_conversion(self) -> None:
        """Test basic transaction conversion."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="Coffee Shop",
            amount=Decimal("-5.50"),
            account="OCBC Credit",
            original_currency="SGD",
        )
        payload = transaction_to_payload(tx, asset_id=12345)

        assert payload["date"] == "2024-01-15"
        assert payload["amount"] == -5.50
        assert payload["payee"] == "Coffee Shop"
        assert payload["currency"] == "sgd"
        assert payload["asset_id"] == 12345
        assert payload["status"] == "uncleared"
        assert "external_id" in payload

    def test_truncates_long_payee(self) -> None:
        """Test that long payee names are truncated to 140 chars."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="A" * 200,
            amount=Decimal("-50.00"),
            account="Test Account",
        )
        payload = transaction_to_payload(tx, asset_id=123)
        assert len(payload["payee"]) == 140

    def test_positive_amount(self) -> None:
        """Test income (positive amount) conversion."""
        tx = Transaction(
            date=date(2024, 1, 15),
            description="Salary",
            amount=Decimal("5000.00"),
            account="DBS Savings",
        )
        payload = transaction_to_payload(tx, asset_id=123)
        assert payload["amount"] == 5000.00


class TestFormatAccountMapping:
    """Tests for account mapping formatting."""

    def test_format_single_mapping(self) -> None:
        """Test formatting a single mapping."""
        mapping = {"OCBC Credit": 12345}
        result = format_account_mapping(mapping)
        assert result == "OCBC Credit=12345"

    def test_format_multiple_mappings(self) -> None:
        """Test formatting multiple mappings."""
        mapping = {"OCBC Credit": 12345, "DBS Savings": 67890}
        result = format_account_mapping(mapping)
        assert "OCBC Credit=12345" in result
        assert "DBS Savings=67890" in result
        assert "|" in result

    def test_format_empty_mapping(self) -> None:
        """Test formatting empty mapping."""
        mapping: dict[str, int] = {}
        result = format_account_mapping(mapping)
        assert result == ""


class TestLunchMoneyClient:
    """Tests for LunchMoneyClient."""

    def test_init(self) -> None:
        """Test client initialization."""
        client = LunchMoneyClient("test_api_key")
        assert client.api_key == "test_api_key"
        assert "Authorization" in client._session.headers
        assert client._session.headers["Authorization"] == "Bearer test_api_key"

    @patch("lunchsync_sg.lunchmoney.requests.Session")
    def test_get_assets(self, mock_session_class: MagicMock) -> None:
        """Test fetching assets."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "assets": [
                {"id": 123, "name": "Test Account"},
                {"id": 456, "name": "Another Account"},
            ]
        }
        mock_session.request.return_value = mock_response

        client = LunchMoneyClient("test_key")
        assets = client.get_assets()

        assert len(assets) == 2
        assert assets[0]["id"] == 123
        assert assets[1]["name"] == "Another Account"

    @patch("lunchsync_sg.lunchmoney.requests.Session")
    def test_upload_transactions_success(self, mock_session_class: MagicMock) -> None:
        """Test successful transaction upload."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {"ids": [1, 2, 3]}
        mock_session.request.return_value = mock_response

        client = LunchMoneyClient("test_key")
        transactions = [
            Transaction(
                date=date(2024, 1, i),
                description=f"Transaction {i}",
                amount=Decimal("-10.00"),
                account="OCBC Credit",
            )
            for i in range(1, 4)
        ]
        account_mapping = {"OCBC Credit": 12345}

        result = client.upload_transactions(transactions, account_mapping)

        assert result.uploaded == 3
        assert result.skipped == 0
        assert result.errors == []

    @patch("lunchsync_sg.lunchmoney.requests.Session")
    def test_upload_skips_unmapped_accounts(self, mock_session_class: MagicMock) -> None:
        """Test that transactions with unmapped accounts are skipped."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {"ids": [1]}
        mock_session.request.return_value = mock_response

        client = LunchMoneyClient("test_key")
        transactions = [
            Transaction(
                date=date(2024, 1, 1),
                description="Mapped",
                amount=Decimal("-10.00"),
                account="OCBC Credit",
            ),
            Transaction(
                date=date(2024, 1, 2),
                description="Unmapped",
                amount=Decimal("-20.00"),
                account="Unknown Account",
            ),
        ]
        account_mapping = {"OCBC Credit": 12345}

        result = client.upload_transactions(transactions, account_mapping)

        assert result.uploaded == 1
        assert result.skipped == 1  # One unmapped

    @patch("lunchsync_sg.lunchmoney.requests.Session")
    def test_upload_batches_large_sets(self, mock_session_class: MagicMock) -> None:
        """Test that large transaction sets are batched."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Return different IDs for each batch
        mock_response = MagicMock()
        mock_response.json.return_value = {"ids": list(range(500))}
        mock_session.request.return_value = mock_response

        client = LunchMoneyClient("test_key")

        # Create 750 transactions (should be split into 2 batches)
        transactions = [
            Transaction(
                date=date(2024, 1, 1),
                description=f"Transaction {i}",
                amount=Decimal("-10.00"),
                account="OCBC Credit",
            )
            for i in range(750)
        ]
        account_mapping = {"OCBC Credit": 12345}

        client.upload_transactions(transactions, account_mapping)

        # Should have made 2 API calls (500 + 250)
        assert mock_session.request.call_count == 2


class TestUploadResult:
    """Tests for UploadResult dataclass."""

    def test_total_property(self) -> None:
        """Test total property calculation."""
        result = UploadResult(uploaded=10, skipped=5, errors=[])
        assert result.total == 15

    def test_with_errors(self) -> None:
        """Test result with errors."""
        result = UploadResult(
            uploaded=5,
            skipped=2,
            errors=["Error 1", "Error 2"],
        )
        assert result.total == 7
        assert len(result.errors) == 2
