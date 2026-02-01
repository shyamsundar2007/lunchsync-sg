"""Pytest configuration and fixtures."""

from pathlib import Path
from typing import Any

import pytest

# Test account mappings that match our test fixtures
# These are fake account numbers used in test fixtures
TEST_CONFIG: dict[str, Any] = {
    "accounts": [
        {"card_number": "5400123456780001", "name": "OCBC Rewards Test", "bank": "OCBC", "type": "credit_card"},
        {"card_number": "5400999988880002", "name": "OCBC Rewards Test 2", "bank": "OCBC", "type": "credit_card"},
        {"card_number": "695012345001", "name": "OCBC 360 Test", "bank": "OCBC", "type": "savings"},
        {"card_number": "0201234567", "name": "DBS Savings Test", "bank": "DBS", "type": "savings"},
        {"card_number": "5420123456780002", "name": "DBS World MC Test", "bank": "DBS", "type": "credit_card"},
        {"card_number": "5522123456780003", "name": "UOB Lady's Solitaire Test", "bank": "UOB", "type": "credit_card"},
        {"card_number": "4265123456780004", "name": "UOB Platinum VISA Test", "bank": "UOB", "type": "credit_card"},
        {"card_number": "3363", "name": "HSBC Revolution Test", "bank": "HSBC", "type": "credit_card"},
        {"card_number": "5425123456780005", "name": "Citi Rewards Test", "bank": "Citi", "type": "credit_card"},
        {"card_number": "5425987654321098", "name": "Citi Prestige Test", "bank": "Citi", "type": "credit_card"},
    ],
    "lunch_money": {
        "api_key": None,
        "account_mapping": {},
    },
}


@pytest.fixture
def test_config() -> dict[str, Any]:
    """Return test configuration."""
    return TEST_CONFIG.copy()


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def ocbc_credit_file(fixtures_dir: Path) -> Path:
    """Return path to OCBC credit card fixture."""
    return fixtures_dir / "ocbc_credit_1.csv"


@pytest.fixture
def ocbc_credit_file_2(fixtures_dir: Path) -> Path:
    """Return path to second OCBC credit card fixture."""
    return fixtures_dir / "ocbc_credit_2.csv"


@pytest.fixture
def ocbc_360_file(fixtures_dir: Path) -> Path:
    """Return path to OCBC 360 account fixture."""
    return fixtures_dir / "ocbc_360.csv"


@pytest.fixture
def dbs_savings_file(fixtures_dir: Path) -> Path:
    """Return path to DBS savings fixture."""
    return fixtures_dir / "dbs_savings.csv"


@pytest.fixture
def dbs_credit_file(fixtures_dir: Path) -> Path:
    """Return path to DBS credit card fixture."""
    return fixtures_dir / "dbs_credit_2.csv"


@pytest.fixture
def uob_solitaire_file(fixtures_dir: Path) -> Path:
    """Return path to UOB Lady's Solitaire fixture."""
    return fixtures_dir / "uob_solitaire.xls"


@pytest.fixture
def uob_platinum_file(fixtures_dir: Path) -> Path:
    """Return path to UOB Platinum VISA fixture."""
    return fixtures_dir / "uob_platinum_1.xls"


@pytest.fixture
def hsbc_file(fixtures_dir: Path) -> Path:
    """Return path to HSBC Revolution fixture."""
    return fixtures_dir / "hsbc_revolution.csv"


@pytest.fixture
def citi_rewards_file(fixtures_dir: Path) -> Path:
    """Return path to Citi Rewards fixture."""
    return fixtures_dir / "citi_rewards.csv"


@pytest.fixture
def citi_prestige_file(fixtures_dir: Path) -> Path:
    """Return path to Citi Prestige fixture."""
    return fixtures_dir / "citi_prestige.csv"
