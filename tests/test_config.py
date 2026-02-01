"""Tests for configuration management."""

import json
from pathlib import Path

import pytest

from lunchsync_sg.config import (
    config_exists,
    create_default_config,
    find_config_file,
    get_account_mappings,
    get_account_name,
    get_lunchmoney_account_mapping,
    get_lunchmoney_api_key,
    load_config,
    save_json_config,
)


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_config_in_current_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test finding config.json in current directory."""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.json"
        config_file.write_text('{"accounts": []}')

        result = find_config_file()

        assert result is not None
        assert result.resolve() == config_file.resolve()

    def test_finds_config_in_xdg_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test finding config in XDG config directory."""
        monkeypatch.chdir(tmp_path)
        xdg_config = tmp_path / "xdg_config"
        xdg_config.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

        config_dir = xdg_config / "lunchsync-sg"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text('{"accounts": []}')

        result = find_config_file()

        assert result == config_file

    def test_current_dir_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test current directory config takes precedence over XDG."""
        monkeypatch.chdir(tmp_path)

        # Create XDG config
        xdg_config = tmp_path / "xdg_config"
        xdg_config.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
        config_dir = xdg_config / "lunchsync-sg"
        config_dir.mkdir()
        (config_dir / "config.json").write_text('{"accounts": []}')

        # Create current directory config
        cwd_config = tmp_path / "config.json"
        cwd_config.write_text('{"accounts": []}')

        result = find_config_file()

        assert result is not None
        assert result.resolve() == cwd_config.resolve()

    def test_returns_none_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns None when no config file exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty_xdg"))

        result = find_config_file()

        assert result is None


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_explicit_path(self, tmp_path: Path) -> None:
        """Test loading from explicit path."""
        config_file = tmp_path / "config.json"
        config_data = {"accounts": [{"card_number": "1234", "name": "Test", "bank": "OCBC"}]}
        config_file.write_text(json.dumps(config_data))

        result = load_config(config_file)

        assert result == config_data

    def test_returns_none_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns None when no config exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))

        result = load_config()

        assert result is None


class TestSaveJsonConfig:
    """Tests for save_json_config function."""

    def test_saves_to_explicit_path(self, tmp_path: Path) -> None:
        """Test saving to explicit path."""
        config_file = tmp_path / "config.json"
        config_data = {"accounts": []}

        result = save_json_config(config_data, config_file)

        assert result == config_file
        assert config_file.exists()
        assert json.loads(config_file.read_text()) == config_data

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test creates parent directories if needed."""
        config_file = tmp_path / "subdir" / "config.json"
        config_data = {"accounts": []}

        save_json_config(config_data, config_file)

        assert config_file.exists()


class TestConfigExists:
    """Tests for config_exists function."""

    def test_returns_true_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns True when config exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").write_text('{"accounts": []}')

        assert config_exists() is True

    def test_returns_false_when_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns False when no config exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))

        assert config_exists() is False


class TestGetAccountMappings:
    """Tests for get_account_mappings function."""

    def test_returns_empty_list_when_no_config(self) -> None:
        """Test returns empty list when config is None."""
        mappings = get_account_mappings(None)

        assert mappings == []

    def test_returns_empty_list_when_no_accounts(self) -> None:
        """Test returns empty list when no accounts in config."""
        config = {"lunch_money": {}}

        mappings = get_account_mappings(config)

        assert mappings == []

    def test_parses_single_mapping(self) -> None:
        """Test parsing a single account mapping."""
        config = {
            "accounts": [
                {"card_number": "1234", "name": "My Card", "bank": "OCBC", "type": "credit_card"}
            ]
        }

        mappings = get_account_mappings(config)

        assert len(mappings) == 1
        assert mappings[0].identifier == "1234"
        assert mappings[0].name == "My Card"
        assert mappings[0].bank == "OCBC"
        assert mappings[0].account_type == "credit_card"

    def test_parses_multiple_mappings(self) -> None:
        """Test parsing multiple account mappings."""
        config = {
            "accounts": [
                {"card_number": "1234", "name": "OCBC Card", "bank": "OCBC", "type": "credit_card"},
                {"card_number": "5678", "name": "DBS Savings", "bank": "DBS", "type": "savings"},
            ]
        }

        mappings = get_account_mappings(config)

        assert len(mappings) == 2
        assert mappings[0].name == "OCBC Card"
        assert mappings[1].name == "DBS Savings"

    def test_defaults_account_type_to_credit_card(self) -> None:
        """Test that account_type defaults to credit_card if not specified."""
        config = {"accounts": [{"card_number": "1234", "name": "My Card", "bank": "OCBC"}]}

        mappings = get_account_mappings(config)

        assert len(mappings) == 1
        assert mappings[0].account_type == "credit_card"


class TestGetAccountName:
    """Tests for get_account_name function."""

    def test_returns_mapped_name(self) -> None:
        """Test returns friendly name for mapped account."""
        config = {
            "accounts": [
                {"card_number": "5400126102581483", "name": "OCBC Rewards", "bank": "OCBC"}
            ]
        }

        name = get_account_name("5400126102581483", config=config)

        assert name == "OCBC Rewards"

    def test_returns_unknown_with_last4_when_no_config(self) -> None:
        """Test returns Unknown (last4) when no config."""
        name = get_account_name("5400126102581483", config=None)

        assert name == "Unknown (1483)"

    def test_returns_unknown_with_last4_when_not_matched(self) -> None:
        """Test returns Unknown (last4) when account doesn't match any mapping."""
        config = {
            "accounts": [
                {"card_number": "9999999999999999", "name": "Other Card", "bank": "DBS"}
            ]
        }

        name = get_account_name("5400126102581483", config=config)

        assert name == "Unknown (1483)"

    def test_returns_identifier_when_too_short(self) -> None:
        """Test returns identifier as-is when less than 4 characters."""
        name = get_account_name("123", config=None)

        assert name == "123"


class TestGetLunchmoneyApiKey:
    """Tests for get_lunchmoney_api_key function."""

    def test_returns_override_if_provided(self) -> None:
        """Test returns override value if provided."""
        config = {"lunch_money": {"api_key": "config_key"}}

        key = get_lunchmoney_api_key(config, override="override_key")

        assert key == "override_key"

    def test_returns_config_key(self) -> None:
        """Test returns key from config."""
        config = {"lunch_money": {"api_key": "config_key"}}

        key = get_lunchmoney_api_key(config)

        assert key == "config_key"

    def test_returns_none_when_no_key(self) -> None:
        """Test returns None when no key configured."""
        config = {"lunch_money": {}}

        key = get_lunchmoney_api_key(config)

        assert key is None


class TestGetLunchmoneyAccountMapping:
    """Tests for get_lunchmoney_account_mapping function."""

    def test_returns_empty_dict_when_no_config(self) -> None:
        """Test returns empty dict when no config."""
        mapping = get_lunchmoney_account_mapping(None)

        assert mapping == {}

    def test_returns_mapping_from_config(self) -> None:
        """Test returns mapping from config."""
        config = {"lunch_money": {"account_mapping": {"OCBC Card": 12345, "DBS Savings": 67890}}}

        mapping = get_lunchmoney_account_mapping(config)

        assert mapping == {"OCBC Card": 12345, "DBS Savings": 67890}


class TestCreateDefaultConfig:
    """Tests for create_default_config function."""

    def test_creates_valid_structure(self) -> None:
        """Test creates valid config structure."""
        config = create_default_config()

        assert "accounts" in config
        assert config["accounts"] == []
        assert "lunch_money" in config
        assert config["lunch_money"]["api_key"] is None
        assert config["lunch_money"]["account_mapping"] == {}
