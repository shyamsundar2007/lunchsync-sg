"""Pytest configuration and fixtures."""

import os
from pathlib import Path

import pytest

# Test account mappings that match our test fixtures
# These are fake account numbers used in test fixtures
TEST_ACCOUNT_MAPPINGS = (
    "5400123456780001:OCBC Rewards Test:OCBC:credit_card,"
    "5400999988880002:OCBC Rewards Test 2:OCBC:credit_card,"
    "695012345001:OCBC 360 Test:OCBC:savings,"
    "0201234567:DBS Savings Test:DBS:savings,"
    "5420123456780002:DBS World MC Test:DBS:credit_card,"
    "5522123456780003:UOB Lady's Solitaire Test:UOB:credit_card,"
    "4265123456780004:UOB Platinum VISA Test:UOB:credit_card,"
    "3363:HSBC Revolution Test:HSBC:credit_card,"
    "5425123456780005:Citi Rewards Test:Citi:credit_card,"
    "5425987654321098:Citi Prestige Test:Citi:credit_card"
)


@pytest.fixture(autouse=True)
def test_account_mappings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up test account mappings for all parser tests."""
    monkeypatch.setenv("ACCOUNT_MAPPINGS", TEST_ACCOUNT_MAPPINGS)


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
