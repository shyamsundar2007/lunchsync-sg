"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lunchsync_sg.config import (
    get_account_mappings,
    get_account_name,
    load_config,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_explicit_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from explicit path."""
        monkeypatch.delenv("LUNCHSYNC_TEST_EXPLICIT", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("LUNCHSYNC_TEST_EXPLICIT=explicit_value")

        load_config(env_file)

        assert os.getenv("LUNCHSYNC_TEST_EXPLICIT") == "explicit_value"

    def test_current_dir_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from current directory .env."""
        monkeypatch.delenv("LUNCHSYNC_TEST_CWD", raising=False)
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("LUNCHSYNC_TEST_CWD=current_dir_value")

        load_config()

        assert os.getenv("LUNCHSYNC_TEST_CWD") == "current_dir_value"

    def test_xdg_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from XDG config directory."""
        monkeypatch.delenv("LUNCHSYNC_TEST_XDG", raising=False)
        monkeypatch.chdir(tmp_path)
        xdg_config = tmp_path / "xdg_config"
        xdg_config.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

        config_dir = xdg_config / "lunchsync-sg"
        config_dir.mkdir()
        env_file = config_dir / ".env"
        env_file.write_text("LUNCHSYNC_TEST_XDG=xdg_value")

        load_config()

        assert os.getenv("LUNCHSYNC_TEST_XDG") == "xdg_value"

    def test_current_dir_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test current directory .env takes precedence over XDG."""
        monkeypatch.delenv("LUNCHSYNC_TEST_PRECEDENCE", raising=False)
        monkeypatch.chdir(tmp_path)

        # Create XDG config
        xdg_config = tmp_path / "xdg_config"
        xdg_config.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
        config_dir = xdg_config / "lunchsync-sg"
        config_dir.mkdir()
        (config_dir / ".env").write_text("LUNCHSYNC_TEST_PRECEDENCE=xdg_value")

        # Create current directory .env
        (tmp_path / ".env").write_text("LUNCHSYNC_TEST_PRECEDENCE=current_value")

        load_config()

        assert os.getenv("LUNCHSYNC_TEST_PRECEDENCE") == "current_value"


class TestGetAccountMappings:
    """Tests for get_account_mappings function."""

    def test_returns_empty_list_when_no_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns empty list when ACCOUNT_MAPPINGS not set."""
        monkeypatch.delenv("ACCOUNT_MAPPINGS", raising=False)

        mappings = get_account_mappings()

        assert mappings == []

    def test_parses_single_mapping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test parsing a single account mapping."""
        monkeypatch.setenv("ACCOUNT_MAPPINGS", "1234:My Card:OCBC:credit_card")

        mappings = get_account_mappings()

        assert len(mappings) == 1
        assert mappings[0].identifier == "1234"
        assert mappings[0].name == "My Card"
        assert mappings[0].bank == "OCBC"
        assert mappings[0].account_type == "credit_card"

    def test_parses_multiple_mappings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test parsing multiple account mappings."""
        monkeypatch.setenv(
            "ACCOUNT_MAPPINGS",
            "1234:OCBC Card:OCBC:credit_card,5678:DBS Savings:DBS:savings",
        )

        mappings = get_account_mappings()

        assert len(mappings) == 2
        assert mappings[0].name == "OCBC Card"
        assert mappings[1].name == "DBS Savings"

    def test_defaults_account_type_to_credit_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that account_type defaults to credit_card if not specified."""
        monkeypatch.setenv("ACCOUNT_MAPPINGS", "1234:My Card:OCBC")

        mappings = get_account_mappings()

        assert len(mappings) == 1
        assert mappings[0].account_type == "credit_card"

    def test_ignores_malformed_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that malformed entries are skipped."""
        monkeypatch.setenv(
            "ACCOUNT_MAPPINGS",
            "valid:Card:OCBC:credit_card,invalid_entry,also:invalid",
        )

        mappings = get_account_mappings()

        assert len(mappings) == 1
        assert mappings[0].name == "Card"


class TestGetAccountName:
    """Tests for get_account_name function."""

    def test_returns_mapped_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns friendly name for mapped account."""
        monkeypatch.setenv("ACCOUNT_MAPPINGS", "5400126102581483:OCBC Rewards:OCBC:credit_card")

        name = get_account_name("5400126102581483")

        assert name == "OCBC Rewards"

    def test_returns_unknown_with_last4_when_no_mapping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns Unknown (last4) for unmapped account."""
        monkeypatch.delenv("ACCOUNT_MAPPINGS", raising=False)

        name = get_account_name("5400126102581483")

        assert name == "Unknown (1483)"

    def test_returns_unknown_with_last4_when_not_matched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns Unknown (last4) when account doesn't match any mapping."""
        monkeypatch.setenv("ACCOUNT_MAPPINGS", "9999999999999999:Other Card:DBS:credit_card")

        name = get_account_name("5400126102581483")

        assert name == "Unknown (1483)"

    def test_returns_identifier_when_too_short(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns identifier as-is when less than 4 characters."""
        monkeypatch.delenv("ACCOUNT_MAPPINGS", raising=False)

        name = get_account_name("123")

        assert name == "123"
