"""Base parser class and registry for bank parsers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from lunchsync_sg.models import Transaction


class BankParser(ABC):
    """Abstract base class for bank transaction parsers."""

    # Class attributes to be overridden by subclasses
    bank_name: ClassVar[str] = "Unknown"
    file_patterns: ClassVar[list[str]] = []  # Patterns to match in file content

    def __init__(self, account_name: str | None = None) -> None:
        """Initialize parser with optional account name override."""
        self._account_name = account_name

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

    def get_account_name(self, identifier: str) -> str:
        """Get account name, using override if set."""
        if self._account_name:
            return self._account_name

        from lunchsync_sg.config import get_account_name

        return get_account_name(identifier)


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
    def get_parser(cls, content: str, filepath: Path | None = None) -> BankParser | None:
        """
        Get appropriate parser for the given content.

        Args:
            content: File content as string
            filepath: Optional filepath for extension detection

        Returns:
            Parser instance if found, None otherwise
        """
        for parser_class in cls._parsers:
            if parser_class.can_parse(content, filepath):
                return parser_class()
        return None

    @classmethod
    def get_all_parsers(cls) -> list[type[BankParser]]:
        """Get all registered parser classes."""
        return cls._parsers.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered parsers (mainly for testing)."""
        cls._parsers = []
