"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest


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
