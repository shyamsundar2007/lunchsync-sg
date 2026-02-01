"""Base parser class and registry for bank parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from lunchsync_sg.models import Transaction


@dataclass
class DetectedAccount:
    """Account information detected from a bank export file."""

    card_number: str
    bank: str
    account_type: str  # credit_card or savings
    display_hint: str  # e.g., "OCBC Credit Card" for display


class BankParser(ABC):
    """Abstract base class for bank transaction parsers."""

    # Class attributes to be overridden by subclasses
    bank_name: ClassVar[str] = "Unknown"
    account_type: ClassVar[str] = "credit_card"  # credit_card or savings
    file_patterns: ClassVar[list[str]] = []  # Patterns to match in file content

    def __init__(
        self,
        account_name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize parser with optional account name override and config."""
        self._account_name = account_name
        self._config = config

    @classmethod
    @abstractmethod
    def can_parse(cls, content: str, filepath: Path | None = None) -> bool:
        """
        Check if this parser can handle the given file content.

        Args:
            content: File content as string
            filepath: Optional path for extension checking

        Returns:
            True if this parser can handle the file
        """
        pass

    @abstractmethod
    def parse(self, content: str) -> list[Transaction]:
        """
        Parse file content and return list of transactions.

        Args:
            content: File content as string

        Returns:
            List of Transaction objects
        """
        pass

    @classmethod
    def detect_account(cls, content: str) -> DetectedAccount | None:
        """
        Detect account information from file content without full parsing.

        Override this in subclasses to extract the account identifier.
        Default implementation returns None.

        Args:
            content: File content as string

        Returns:
            DetectedAccount with card_number, bank, type, or None if not detected
        """
        return None

    def get_account_name(self, identifier: str) -> str:
        """Get account name, using override if set."""
        if self._account_name:
            return self._account_name

        from lunchsync_sg.config import get_account_name

        return get_account_name(identifier, config=self._config)


class ParserRegistry:
    """Registry for bank parsers with automatic detection."""

    _parsers: ClassVar[list[type[BankParser]]] = []

    @classmethod
    def register(cls, parser_class: type[BankParser]) -> type[BankParser]:
        """
        Register a parser class. Can be used as a decorator.

        Example:
            @ParserRegistry.register
            class MyBankParser(BankParser):
                ...
        """
        if parser_class not in cls._parsers:
            cls._parsers.append(parser_class)
        return parser_class

    @classmethod
    def get_parser(
        cls,
        content: str,
        filepath: Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> BankParser | None:
        """
        Get appropriate parser for the given content.

        Args:
            content: File content as string
            filepath: Optional filepath for extension detection
            config: Loaded JSON config for account mappings

        Returns:
            Parser instance if found, None otherwise
        """
        for parser_class in cls._parsers:
            if parser_class.can_parse(content, filepath):
                return parser_class(config=config)
        return None

    @classmethod
    def get_all_parsers(cls) -> list[type[BankParser]]:
        """Get all registered parser classes."""
        return cls._parsers.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered parsers (mainly for testing)."""
        cls._parsers = []
